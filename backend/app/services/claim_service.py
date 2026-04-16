from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from postgrest.exceptions import APIError

from app.database import get_supabase
from app.ml import earning_simulator, fraud_engine
from app.services.notification_service import notify_admins, notify_worker
from app.services.policy_service import is_policy_current, policy_covers_datetime
from app.services.payout_service import build_mock_payout_id, build_upi_receipt
from app.utils.explanation_generator import generate_explanation

FALLBACK_WINDOW_HOURS = 48
REVIEWABLE_STATUSES = {
    "soft_flagged",
    "hard_flagged",
    "manual_submitted",
    "manual_under_review",
}

OPTIONAL_CLAIM_COLUMNS = {
    "claim_origin",
    "eligible_payout_amount",
    "held_payout_amount",
    "review_reason",
    "reviewed_by",
    "reviewed_at",
    "resolution_note",
    "batch_id",
    "is_batch_paused",
    "ring_review_flag",
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def record_claim_event(
    claim_id: str,
    event_type: str,
    actor_type: str = "system",
    actor_id: str | None = None,
    note: str | None = None,
    metadata: dict | None = None,
) -> None:
    db = get_supabase()
    try:
        db.table("claim_events").insert(
            {
                "claim_id": claim_id,
                "event_type": event_type,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "note": note,
                "metadata": metadata or {},
            }
        ).execute()
    except APIError as exc:
        if "claim_events" not in str(exc):
            raise


def _get_policy_for_disruption(worker_id: str, disruption_started_at: str | None) -> dict | None:
    db = get_supabase()
    policies = (
        db.table("policies")
        .select("*, plans(*)")
        .eq("worker_id", worker_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    ).data or []

    disruption_dt = _parse_dt(disruption_started_at)
    for policy in policies:
        if policy_covers_datetime(policy, disruption_dt):
            return policy
    if disruption_dt is None:
        return next((policy for policy in policies if is_policy_current(policy)), None)
    return None


def _compute_review_approved_payout(claim: dict) -> float:
    eligible = _safe_float(claim.get("eligible_payout_amount"))
    if eligible > 0:
        return round(eligible, 2)

    db = get_supabase()
    policy_res = (
        db.table("policies")
        .select("*, plans(*)")
        .eq("id", claim["policy_id"])
        .single()
        .execute()
    )
    policy = policy_res.data if policy_res.data else {}
    plan = policy.get("plans", {}) if isinstance(policy, dict) else {}
    max_weekly = _safe_float(plan.get("max_weekly_payout"), _safe_float(claim.get("income_gap")))
    coverage_pct = _safe_float(claim.get("coverage_pct") or plan.get("coverage_pct"), 0.70)
    income_gap = _safe_float(claim.get("income_gap"))
    return round(min(income_gap * coverage_pct, max_weekly), 2)


def _review_metadata(reason: str | None, note: str | None) -> dict:
    return {
        "review_reason": reason or "operator_review",
        "resolution_note": note or "",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }


def _canonical_claim(claim: dict) -> dict:
    payouts = claim.get("payouts") or []
    claim_events = claim.get("claim_events") or []
    disruption = claim.get("disruption_events")
    worker = claim.get("workers")

    paid_amount = round(
        sum(
            _safe_float(payout.get("amount"))
            for payout in payouts
            if payout.get("status") == "paid"
        ),
        2,
    )
    held_amount = round(
        sum(
            _safe_float(payout.get("amount"))
            for payout in payouts
            if payout.get("status") == "held_for_review"
        ),
        2,
    )
    latest_payout_status = payouts[0]["status"] if payouts else None
    claim_origin = claim.get("claim_origin", "auto")
    claim_status = claim.get("status", "processing")
    latest_receipt = None
    if payouts:
        latest = payouts[0]
        latest_receipt = build_upi_receipt(
            claim["id"],
            _safe_float(latest.get("amount")),
            latest.get("status", "paid"),
            latest.get("mock_payout_id"),
        )

    return {
        **claim,
        "claim_origin": claim_origin,
        "recommended_payout": _safe_float(
            claim.get("eligible_payout_amount"),
            _safe_float(claim.get("payout_amount")),
        ),
        "paid_amount": paid_amount,
        "held_amount": held_amount,
        "latest_payout_status": latest_payout_status,
        "upi_receipt": latest_receipt,
        "payout_timeline": [
            {
                "id": payout.get("id"),
                "amount": _safe_float(payout.get("amount")),
                "status": payout.get("status"),
                "provider_ref": payout.get("mock_payout_id"),
                "paid_at": payout.get("paid_at"),
                "created_at": payout.get("created_at"),
            }
            for payout in payouts
        ],
        "review_required": claim_status in REVIEWABLE_STATUSES,
        "can_worker_fallback": False,
        "fraud_report": build_fraud_report({**claim, "payouts": payouts, "claim_events": claim_events}),
        "lifecycle_summary": {
            "status": claim_status,
            "origin": claim_origin,
            "disruption_label": (
                disruption.get("trigger_type", "").replace("_", " ").title()
                if disruption
                else claim.get("trigger_type", "").replace("_", " ").title()
            ),
            "worker_name": worker.get("name") if worker else None,
        },
        "audit_trail": {
            "events": claim_events,
            "payouts": payouts,
            "reviewed_by": claim.get("reviewed_by"),
            "reviewed_at": claim.get("reviewed_at"),
            "review_reason": claim.get("review_reason"),
            "resolution_note": claim.get("resolution_note"),
        },
    }


def _enrich_claim_row(claim: dict) -> dict:
    db = get_supabase()
    claim_id = claim["id"]
    payouts = (
        db.table("payouts")
        .select("*")
        .eq("claim_id", claim_id)
        .order("created_at", desc=True)
        .execute()
    ).data or []
    claim_events = []
    try:
        claim_events = (
            db.table("claim_events")
            .select("*")
            .eq("claim_id", claim_id)
            .order("created_at", desc=False)
            .execute()
        ).data or []
    except Exception:
        claim_events = []

    disruption = None
    if claim.get("disruption_id"):
        disruption_res = (
            db.table("disruption_events")
            .select("*")
            .eq("id", claim["disruption_id"])
            .limit(1)
            .execute()
        )
        disruption = disruption_res.data[0] if disruption_res.data else None

    worker = None
    if claim.get("worker_id"):
        worker_res = (
            db.table("workers")
            .select("name, platform, grid_id, iss_score")
            .eq("id", claim["worker_id"])
            .limit(1)
            .execute()
        )
        worker = worker_res.data[0] if worker_res.data else None

    return _canonical_claim(
        {
            **claim,
            "payouts": payouts,
            "claim_events": claim_events,
            "disruption_events": disruption,
            "workers": worker,
        }
    )


def build_fraud_report(claim: dict) -> dict:
    flags = claim.get("fraud_flags") or []
    recommendation = "auto_pay"
    if not claim.get("fraud_layer1_pass", True):
        recommendation = "deny_or_review"
    elif not claim.get("fraud_layer2_pass", True) or not claim.get("fraud_layer3_pass", True):
        recommendation = "review"

    return {
        "claim_id": claim.get("id"),
        "fraud_score": _safe_float(claim.get("fraud_score")),
        "risk_level": (
            "high"
            if _safe_float(claim.get("fraud_score")) >= 0.75
            else "medium"
            if _safe_float(claim.get("fraud_score")) >= 0.25
            else "low"
        ),
        "recommendation": recommendation,
        "review_required": claim.get("status") in REVIEWABLE_STATUSES,
        "flags": flags,
        "delivery_specific_flags": [
            flag for flag in flags
            if flag.get("type") in {
                "gps_spoofing_suspected",
                "weak_weather_signal",
                "claim_burst_pattern",
                "zone_mismatch",
            }
        ],
        "layers": [
            {
                "layer": 1,
                "name": "Rule-based validation",
                "pass": claim.get("fraud_layer1_pass", True),
                "explanation": "Verifies zone match, duplicate claims, recent activity, and policy timing.",
            },
            {
                "layer": 2,
                "name": "Behavioral analysis",
                "pass": claim.get("fraud_layer2_pass", True),
                "explanation": "Checks worker age, ISS health, and claim size versus expected income behavior.",
            },
            {
                "layer": 3,
                "name": "ML anomaly detection",
                "pass": claim.get("fraud_layer3_pass", True),
                "explanation": "Isolation Forest flags outlier claim patterns for operator review.",
            },
        ],
        "operator_summary": (
            "Claim is clear for automation."
            if recommendation == "auto_pay"
            else "Claim needs operator review before full payout."
        ),
    }


def get_claims_for_worker(worker_id: str, limit: int = 10) -> list[dict]:
    db = get_supabase()
    result = (
        db.table("claims")
        .select("*")
        .eq("worker_id", worker_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [_enrich_claim_row(row) for row in (result.data or [])]


def get_claim_detail(claim_id: str) -> dict:
    db = get_supabase()
    result = (
        db.table("claims")
        .select("*")
        .eq("id", claim_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Claim not found")
    return _enrich_claim_row(result.data)


def get_worker_fallback_eligibility(worker_id: str) -> dict:
    db = get_supabase()
    worker_res = (
        db.table("workers")
        .select("*")
        .eq("id", worker_id)
        .single()
        .execute()
    )
    worker = worker_res.data
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    if not worker.get("grid_id"):
        return {"worker_id": worker_id, "eligible_windows": []}

    since = (datetime.now(timezone.utc) - timedelta(hours=FALLBACK_WINDOW_HOURS)).isoformat()
    disruptions = (
        db.table("disruption_events")
        .select("*")
        .eq("grid_id", worker["grid_id"])
        .gte("started_at", since)
        .order("started_at", desc=True)
        .limit(20)
        .execute()
    ).data or []

    claims = (
        db.table("claims")
        .select("disruption_id")
        .eq("worker_id", worker_id)
        .gte("created_at", since)
        .execute()
    ).data or []
    claimed_ids = {claim.get("disruption_id") for claim in claims if claim.get("disruption_id")}

    eligible_windows = []
    for disruption in disruptions:
        if disruption["id"] in claimed_ids:
            continue
        policy = _get_policy_for_disruption(worker_id, disruption.get("started_at"))
        if not policy:
            continue
        eligible_windows.append(
            {
                "disruption_id": disruption["id"],
                "trigger_type": disruption["trigger_type"],
                "started_at": disruption["started_at"],
                "city": disruption.get("city"),
                "grid_id": disruption.get("grid_id"),
                "description": disruption.get("weather_description")
                or "Automation detected a disruption, but no claim was created.",
                "policy_id": policy["id"],
                "window_expires_at": (
                    _parse_dt(disruption["started_at"]) + timedelta(hours=FALLBACK_WINDOW_HOURS)
                ).isoformat()
                if _parse_dt(disruption["started_at"])
                else None,
            }
        )

    return {"worker_id": worker_id, "eligible_windows": eligible_windows}


def create_claim_for_disruption(
    worker: dict,
    disruption: dict,
    policy: dict,
    plan: dict,
    claim_origin: str = "auto",
    fallback_reason: str | None = None,
) -> dict | None:
    db = get_supabase()

    existing_claim_res = (
        db.table("claims")
        .select("id")
        .eq("worker_id", worker["id"])
        .eq("disruption_id", disruption["id"])
        .limit(1)
        .execute()
    )
    if existing_claim_res.data:
        return None

    has_duplicate_claim = False
    policy_after_event = False
    try:
        policy_start = _parse_dt(f"{policy['start_date']}T00:00:00+00:00")
        disruption_started = _parse_dt(disruption["started_at"])
        policy_after_event = bool(policy_start and disruption_started and policy_start > disruption_started)
    except Exception:
        policy_after_event = False

    l1 = fraud_engine.run_fraud_layer1(
        worker,
        disruption,
        has_duplicate_claim=has_duplicate_claim,
        policy_after_event=policy_after_event,
    )
    sim = earning_simulator.calculate(worker, disruption)
    coverage_pct = _safe_float(plan.get("coverage_pct"), 0.70)
    max_weekly = _safe_float(plan.get("max_weekly_payout"), 2500)
    income_gap = _safe_float(sim["income_gap"])
    eligible_payout = round(min(income_gap * coverage_pct, max_weekly), 2)

    l2 = fraud_engine.run_fraud_layer2(worker, sim, income_gap)
    l3 = fraud_engine.run_fraud_layer3(
        eligible_payout,
        income_gap,
        sim["disruption_hours"],
        worker,
    )

    all_flags = l1["flags"] + l2["flags"] + l3["flags"]
    fraud_score = min(len(all_flags) * 0.25, 1.0)

    if claim_origin == "manual":
        status = "manual_under_review"
        payout_amount = 0
        held_payout_amount = 0
    elif not l1["pass"]:
        status = "hard_flagged"
        payout_amount = 0
        held_payout_amount = 0
    elif not l2["pass"] or not l3["pass"]:
        status = "soft_flagged"
        payout_amount = round(eligible_payout * 0.70, 2)
        held_payout_amount = payout_amount
    else:
        status = "auto_approved"
        payout_amount = eligible_payout
        held_payout_amount = 0

    worker_for_explain = {**worker, "coverage_pct": coverage_pct}
    explanation = generate_explanation(
        worker_for_explain,
        sim,
        payout_amount if payout_amount > 0 else eligible_payout,
        disruption["trigger_type"],
    )

    claim_data = {
        "worker_id": worker["id"],
        "policy_id": policy["id"],
        "disruption_id": disruption["id"],
        "trigger_type": disruption["trigger_type"],
        "status": status,
        "claim_origin": claim_origin,
        "actual_earnings": sim["actual_earnings"],
        "simulated_earnings": sim["simulated_earnings"],
        "income_gap": income_gap,
        "eligible_payout_amount": eligible_payout,
        "held_payout_amount": held_payout_amount,
        "payout_amount": payout_amount,
        "coverage_pct": coverage_pct,
        "fraud_score": fraud_score,
        "fraud_layer1_pass": l1["pass"],
        "fraud_layer2_pass": l2["pass"],
        "fraud_layer3_pass": l3["pass"],
        "fraud_flags": all_flags,
        "earning_simulation": sim,
        "hinglish_explanation": explanation,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "review_reason": fallback_reason if claim_origin == "manual" else None,
        "batch_id": disruption["id"],
        "is_batch_paused": False,
        "ring_review_flag": len(all_flags) >= 3,
    }
    try:
        claim_res = db.table("claims").insert(claim_data).execute()
    except APIError as exc:
        message = str(exc)
        fallback_data = {k: v for k, v in claim_data.items() if k not in OPTIONAL_CLAIM_COLUMNS}
        if any(column in message for column in OPTIONAL_CLAIM_COLUMNS):
            claim_res = db.table("claims").insert(fallback_data).execute()
        else:
            raise
    claim = claim_res.data[0] if claim_res.data else None
    if not claim:
        return None

    creation_note = (
        "Worker submitted a fallback claim for a missed disruption."
        if claim_origin == "manual"
        else "Claim created by zero-touch automation."
    )
    record_claim_event(
        claim["id"],
        "manual_fallback_submitted" if claim_origin == "manual" else "claim_created",
        note=creation_note,
        metadata={"trigger_type": disruption["trigger_type"], "status": status},
    )
    record_claim_event(
        claim["id"],
        "fraud_checks_completed",
        note="Fraud layers evaluated for claim eligibility.",
        metadata={
            "fraud_score": fraud_score,
            "layer1_pass": l1["pass"],
            "layer2_pass": l2["pass"],
            "layer3_pass": l3["pass"],
            "flags": all_flags,
        },
    )

    if status == "auto_approved" and payout_amount > 0:
        record_claim_event(
            claim["id"],
            "claim_auto_approved",
            note="Claim passed all automation checks.",
            metadata={"eligible_payout": eligible_payout},
        )
        payout_data = {
            "claim_id": claim["id"],
            "worker_id": worker["id"],
            "amount": payout_amount,
            "upi_id": "worker@upi",
            "status": "paid",
            "mock_payout_id": build_mock_payout_id("MOCK_PAY", claim["id"]),
            "paid_at": datetime.now(timezone.utc).isoformat(),
            "whatsapp_shown": False,
        }
        payout_res = db.table("payouts").insert(payout_data).execute()
        payout = payout_res.data[0] if payout_res.data else None
        db.table("claims").update({"status": "paid"}).eq("id", claim["id"]).execute()
        record_claim_event(
            claim["id"],
            "payout_paid",
            note="Payout sent automatically.",
            metadata={"amount": payout_amount, "payout_id": payout["id"] if payout else None},
        )
        claim["status"] = "paid"
    elif status == "soft_flagged" and payout_amount > 0:
        payout_res = db.table("payouts").insert(
            {
                "claim_id": claim["id"],
                "worker_id": worker["id"],
                "amount": payout_amount,
                "upi_id": "worker@upi",
                "status": "held_for_review",
                "mock_payout_id": build_mock_payout_id("MOCK_HOLD", claim["id"]),
                "paid_at": None,
                "whatsapp_shown": False,
            }
        ).execute()
        payout = payout_res.data[0] if payout_res.data else None
        record_claim_event(
            claim["id"],
            "payout_held",
            note="Partial payout held pending operator review.",
            metadata={"amount": payout_amount, "payout_id": payout["id"] if payout else None},
        )
    else:
        review_note = (
            "Fallback claim submitted and queued for operator review."
            if claim_origin == "manual"
            else "Claim requires operator review before payout."
        )
        record_claim_event(
            claim["id"],
            "claim_review_required",
            note=review_note,
            metadata={"status": status, "eligible_payout": eligible_payout},
        )

    claim_detail = get_claim_detail(claim["id"])
    try:
        if claim_detail["status"] == "paid":
            notify_text = (
                f"{disruption['trigger_type'].replace('_', ' ').title()} detected in your insured grid.\n"
                f"₹{int(claim_detail['paid_amount'])} has been protected and marked as paid."
            )
        else:
            notify_text = (
                f"{disruption['trigger_type'].replace('_', ' ').title()} detected in your insured grid.\n"
                f"Claim status: {claim_detail['status'].replace('_', ' ')} | Eligible payout: ₹{int(eligible_payout)}"
            )
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(
                notify_worker(
                    worker["id"],
                    "Incometrix protection update",
                    notify_text,
                    {"claim_id": claim["id"], "disruption_id": disruption["id"]},
                )
            )
        except RuntimeError:
            pass
    except Exception:
        pass

    return claim_detail


def submit_fallback_claim(worker_id: str, disruption_id: str, reason: str | None = None) -> dict:
    db = get_supabase()
    worker_res = (
        db.table("workers")
        .select("*")
        .eq("id", worker_id)
        .single()
        .execute()
    )
    worker = worker_res.data
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    disruption_res = (
        db.table("disruption_events")
        .select("*")
        .eq("id", disruption_id)
        .single()
        .execute()
    )
    disruption = disruption_res.data
    if not disruption:
        raise HTTPException(status_code=404, detail="Disruption not found")

    if disruption.get("grid_id") != worker.get("grid_id"):
        raise HTTPException(status_code=400, detail="Fallback claim is only allowed for disruptions in your insured grid.")

    started_at = _parse_dt(disruption.get("started_at"))
    if not started_at or started_at < datetime.now(timezone.utc) - timedelta(hours=FALLBACK_WINDOW_HOURS):
        raise HTTPException(status_code=400, detail="Fallback claim window has expired.")

    existing = (
        db.table("claims")
        .select("id")
        .eq("worker_id", worker_id)
        .eq("disruption_id", disruption_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=409, detail="A claim already exists for this disruption.")

    policy = _get_policy_for_disruption(worker_id, disruption.get("started_at"))
    if not policy:
        raise HTTPException(status_code=400, detail="No eligible policy covered this disruption window.")

    plan = policy.get("plans", {})
    claim = create_claim_for_disruption(
        worker,
        disruption,
        policy,
        plan,
        claim_origin="manual",
        fallback_reason=reason or "Worker reported that zero-touch claim was missed.",
    )
    if not claim:
        raise HTTPException(status_code=500, detail="Failed to create fallback claim.")
    return claim


def approve_claim_review(
    claim_id: str,
    reviewer: str = "admin",
    reason: str | None = None,
    note: str | None = None,
) -> dict:
    db = get_supabase()
    claim = get_claim_detail(claim_id)
    current_status = claim["status"]
    if current_status not in REVIEWABLE_STATUSES:
        raise HTTPException(status_code=400, detail="Claim is not reviewable.")

    approved_total = _compute_review_approved_payout(claim)
    review_meta = _review_metadata(reason, note)
    update_payload = {
        "status": "approved_after_review",
        "payout_amount": approved_total,
        "reviewed_by": reviewer,
        "reviewed_at": review_meta["reviewed_at"],
        "review_reason": review_meta["review_reason"],
        "resolution_note": review_meta["resolution_note"],
    }
    try:
        db.table("claims").update(update_payload).eq("id", claim_id).execute()
    except APIError as exc:
        message = str(exc)
        fallback_payload = {k: v for k, v in update_payload.items() if k not in OPTIONAL_CLAIM_COLUMNS}
        if any(column in message for column in OPTIONAL_CLAIM_COLUMNS):
            db.table("claims").update(fallback_payload).eq("id", claim_id).execute()
        else:
            raise

    payouts = claim.get("audit_trail", {}).get("payouts", [])
    held_payout = next((p for p in payouts if p.get("status") == "held_for_review"), None)
    paid_so_far = 0.0
    if held_payout:
        paid_so_far = _safe_float(held_payout.get("amount"))
        db.table("payouts").update(
            {
                "status": "paid",
                "paid_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", held_payout["id"]).execute()
        record_claim_event(
            claim_id,
            "payout_released",
            actor_type="admin",
            actor_id=reviewer,
            note="Held payout released after review.",
            metadata={"amount": paid_so_far, "payout_id": held_payout["id"]},
        )

    remaining = round(max(approved_total - paid_so_far, 0), 2)
    if remaining > 0:
        payout_res = db.table("payouts").insert(
            {
                "claim_id": claim_id,
                "worker_id": claim["worker_id"],
                "amount": remaining,
                "status": "paid",
                "upi_id": "worker@upi",
                "mock_payout_id": build_mock_payout_id("REVIEW_PAY", claim_id),
                "paid_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()
        payout = payout_res.data[0] if payout_res.data else None
        record_claim_event(
            claim_id,
            "payout_paid",
            actor_type="admin",
            actor_id=reviewer,
            note="Payout issued after operator approval.",
            metadata={"amount": remaining, "payout_id": payout["id"] if payout else None},
        )

    record_claim_event(
        claim_id,
        "admin_approved",
        actor_type="admin",
        actor_id=reviewer,
        note=note or "Claim approved after review.",
        metadata={"reason": review_meta["review_reason"], "approved_total": approved_total},
    )

    worker_res = (
        db.table("workers")
        .select("iss_score")
        .eq("id", claim["worker_id"])
        .single()
        .execute()
    )
    if worker_res.data:
        db.table("workers").update(
            {"iss_score": min(_safe_float(worker_res.data.get("iss_score"), 50) + 3, 100)}
        ).eq("id", claim["worker_id"]).execute()

    claim_detail = get_claim_detail(claim_id)
    try:
        import asyncio
        loop = asyncio.get_running_loop()
        loop.create_task(
            notify_worker(
                claim["worker_id"],
                "Claim approved and payout released",
                f"Your claim was approved after review and ₹{int(approved_total)} has been released.",
                {"claim_id": claim_id, "status": "approved_after_review"},
            )
        )
        loop.create_task(
            notify_admins(
                "Fraud review resolved",
                f"Claim {claim_id[:8]} was approved and ₹{int(approved_total)} was released.",
                {"claim_id": claim_id, "reviewer": reviewer},
            )
        )
    except RuntimeError:
        pass

    return claim_detail


def reject_claim_review(
    claim_id: str,
    reviewer: str = "admin",
    reason: str | None = None,
    note: str | None = None,
) -> dict:
    db = get_supabase()
    claim = get_claim_detail(claim_id)
    current_status = claim["status"]
    if current_status not in REVIEWABLE_STATUSES:
        raise HTTPException(status_code=400, detail="Claim is not reviewable.")

    review_meta = _review_metadata(reason, note)
    update_payload = {
        "status": "rejected",
        "payout_amount": 0,
        "held_payout_amount": 0,
        "reviewed_by": reviewer,
        "reviewed_at": review_meta["reviewed_at"],
        "review_reason": review_meta["review_reason"],
        "resolution_note": review_meta["resolution_note"],
    }
    try:
        db.table("claims").update(update_payload).eq("id", claim_id).execute()
    except APIError as exc:
        message = str(exc)
        fallback_payload = {k: v for k, v in update_payload.items() if k not in OPTIONAL_CLAIM_COLUMNS}
        if any(column in message for column in OPTIONAL_CLAIM_COLUMNS):
            db.table("claims").update(fallback_payload).eq("id", claim_id).execute()
        else:
            raise
    db.table("payouts").update({"status": "cancelled"}).eq("claim_id", claim_id).eq(
        "status", "held_for_review"
    ).execute()
    record_claim_event(
        claim_id,
        "admin_rejected",
        actor_type="admin",
        actor_id=reviewer,
        note=note or "Claim rejected after review.",
        metadata={"reason": review_meta["review_reason"]},
    )

    worker_res = (
        db.table("workers")
        .select("iss_score")
        .eq("id", claim["worker_id"])
        .single()
        .execute()
    )
    if worker_res.data:
        db.table("workers").update(
            {"iss_score": max(_safe_float(worker_res.data.get("iss_score"), 50) - 10, 0)}
        ).eq("id", claim["worker_id"]).execute()

    claim_detail = get_claim_detail(claim_id)
    try:
        import asyncio
        loop = asyncio.get_running_loop()
        loop.create_task(
            notify_worker(
                claim["worker_id"],
                "Claim rejected after review",
                "Your payout is cancelled after review. Please check the app for the resolution note.",
                {"claim_id": claim_id, "status": "rejected"},
            )
        )
        loop.create_task(
            notify_admins(
                "Fraud review rejected a claim",
                f"Claim {claim_id[:8]} was rejected by {reviewer}.",
                {"claim_id": claim_id, "reviewer": reviewer},
            )
        )
    except RuntimeError:
        pass

    return claim_detail
