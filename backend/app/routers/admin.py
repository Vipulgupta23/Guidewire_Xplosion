"""
Admin Router — Stats, claims queue, fraud list, simulate disruption.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta

from app.database import get_supabase
from app.services.claim_service import get_claim_detail as get_claim_detail_service
from app.services.notification_service import get_notification_status
from app.services.policy_service import is_policy_current
from app.services.prediction_service import get_admin_predictive_analytics
from app.services.pricing_feature_service import feature_health_summary
from app.services.trigger_engine import (
    create_disruption_and_claims,
    TRIGGERS,
)

router = APIRouter(prefix="/admin", tags=["admin"])


class SimulateTriggerRequest(BaseModel):
    trigger_type: str
    grid_id: str
    severity: float
    description: Optional[str] = None


@router.get("/stats")
async def get_admin_stats():
    """Get overview statistics for admin dashboard."""
    db = get_supabase()

    # Total active workers
    workers_res = (
        db.table("workers")
        .select("id", count="exact")
        .eq("is_active", True)
        .execute()
    )
    total_workers = workers_res.count or 0

    # Active disruptions
    disruptions_res = (
        db.table("disruption_events")
        .select("id", count="exact")
        .eq("is_active", True)
        .execute()
    )
    active_disruptions = disruptions_res.count or 0

    # Claims today
    today = datetime.now(timezone.utc).date().isoformat()
    claims_res = (
        db.table("claims")
        .select("id, payout_amount")
        .gte("created_at", today)
        .execute()
    )
    claims_today = len(claims_res.data) if claims_res.data else 0
    total_payout_today = sum(
        c.get("payout_amount", 0) for c in (claims_res.data or [])
    )

    # Fraud alerts pending
    fraud_res = (
        db.table("claims")
        .select("id", count="exact")
        .in_("status", ["hard_flagged", "soft_flagged"])
        .execute()
    )
    fraud_alerts = fraud_res.count or 0

    # Active policies
    policies_res = (
        db.table("policies")
        .select("id, weekly_premium_actual, start_date, end_date", count="exact")
        .eq("status", "active")
        .execute()
    )
    current_policies = [policy for policy in (policies_res.data or []) if is_policy_current(policy)]
    active_policies = len(current_policies)
    current_week_premium_total = round(
        sum(float(policy.get("weekly_premium_actual", 0)) for policy in current_policies),
        2,
    )
    projected_next_week_loss_ratio = round(
        (total_payout_today / max(current_week_premium_total, 1)) * 100,
        1,
    )

    return {
        "total_workers": total_workers,
        "active_disruptions": active_disruptions,
        "claims_today": claims_today,
        "total_payout_today": round(total_payout_today, 2),
        "fraud_alerts": fraud_alerts,
        "active_policies": active_policies,
        "current_week_premium_total": current_week_premium_total,
        "loss_ratio_percent": round(
            (total_payout_today / max(current_week_premium_total, 1)) * 100,
            1,
        ),
        "projected_next_week_loss_ratio": projected_next_week_loss_ratio,
        "telegram_status": get_notification_status("admin", "default_admin"),
    }


@router.get("/claims-queue")
async def get_claims_queue(
    limit: int = 50,
    status: Optional[str] = None,
    claim_origin: Optional[str] = None,
    reviewable_only: bool = False,
):
    """Get recent claims for admin review."""
    db = get_supabase()
    query = (
        db.table("claims")
        .select("id")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        query = query.eq("status", status)
    if claim_origin:
        query = query.eq("claim_origin", claim_origin)
    if reviewable_only:
        query = query.in_(
            "status",
            ["soft_flagged", "hard_flagged", "manual_submitted", "manual_under_review"],
        )
    result = query.execute()
    return [get_claim_detail_service(row["id"]) for row in (result.data or [])]


@router.get("/fraud-list")
async def get_fraud_list():
    """Get all flagged claims requiring review."""
    db = get_supabase()
    result = (
        db.table("claims")
        .select("id")
        .in_("status", ["hard_flagged", "soft_flagged", "manual_under_review"])
        .order("created_at", desc=True)
        .execute()
    )
    return [get_claim_detail_service(row["id"]) for row in (result.data or [])]


@router.get("/disruptions")
async def get_active_disruptions():
    """Get all active disruption events."""
    db = get_supabase()
    result = (
        db.table("disruption_events")
        .select("*")
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.get("/disruptions/history")
async def get_disruption_history(days: int = 7):
    """Get disruption history."""
    db = get_supabase()
    since = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).isoformat()
    result = (
        db.table("disruption_events")
        .select("*")
        .gte("created_at", since)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@router.get("/daily-stats")
async def get_daily_stats(days: int = 7):
    """Get daily claims and payout stats for charts."""
    db = get_supabase()
    since = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).isoformat()

    claims_res = (
        db.table("claims")
        .select("created_at, payout_amount, status")
        .gte("created_at", since)
        .order("created_at")
        .execute()
    )

    # Group by date
    daily = {}
    for claim in claims_res.data or []:
        date = claim["created_at"][:10]
        if date not in daily:
            daily[date] = {"date": date, "claims": 0, "payout": 0}
        daily[date]["claims"] += 1
        daily[date]["payout"] += claim.get("payout_amount", 0)

    return list(daily.values())


@router.get("/feature-health")
async def get_feature_health():
    """Live pricing feature freshness by city."""
    return feature_health_summary()


@router.get("/payouts-summary")
async def get_payouts_summary(days: int = 7):
    """Get payout audit totals and recent payout activity."""
    db = get_supabase()
    since = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).isoformat()
    payouts = (
        db.table("payouts")
        .select("*")
        .gte("created_at", since)
        .order("created_at", desc=True)
        .execute()
    ).data or []
    return {
        "window_days": days,
        "paid_total": round(sum(float(p.get("amount", 0)) for p in payouts if p.get("status") == "paid"), 2),
        "held_total": round(sum(float(p.get("amount", 0)) for p in payouts if p.get("status") == "held_for_review"), 2),
        "cancelled_total": round(sum(float(p.get("amount", 0)) for p in payouts if p.get("status") == "cancelled"), 2),
        "paid_count": sum(1 for p in payouts if p.get("status") == "paid"),
        "held_count": sum(1 for p in payouts if p.get("status") == "held_for_review"),
        "recent_payouts": payouts[:12],
    }


@router.get("/predictive-analytics")
async def get_predictive_analytics():
    """Get city and grid level disruption and payout forecasts."""
    return get_admin_predictive_analytics()


@router.post("/simulate-trigger")
async def simulate_trigger(req: SimulateTriggerRequest):
    """🔴 Demo-only: Manually fire a disruption trigger."""
    db = get_supabase()

    # Get grid
    grid_res = (
        db.table("microgrids")
        .select("*")
        .eq("id", req.grid_id)
        .single()
        .execute()
    )
    if not grid_res.data:
        raise HTTPException(status_code=404, detail=f"Grid {req.grid_id} not found")
    grid = grid_res.data

    # Find matching trigger
    trigger = None
    for t in TRIGGERS:
        if t["type"] == req.trigger_type:
            trigger = t
            break
    if not trigger:
        # Allow custom trigger types for demo
        trigger = {
            "type": req.trigger_type,
            "param": "custom",
            "threshold": req.severity * 0.8,
            "unit": "",
            "payout_max": 500,
        }

    raw_weather = {
        "simulated": True,
        "description": req.description or f"Simulated {req.trigger_type}",
        "temp": 35,
        "rain_6h": req.severity if "rain" in req.trigger_type else 0,
    }

    summary = await create_disruption_and_claims(
        grid,
        trigger,
        req.severity,
        raw_weather,
        trigger_origin="admin_manual",
    )

    demo_note = None
    if trigger.get("manual_only"):
        demo_note = "This trigger is demo-simulated only and is not auto-detected by the scheduler."

    return {
        "message": f"🔴 Trigger {req.trigger_type} fired for grid {req.grid_id}",
        "severity": req.severity,
        "grid": grid["id"],
        "disruption_id": (summary or {}).get("disruption", {}).get("id"),
        "trigger_origin": (summary or {}).get("trigger_origin", "admin_manual"),
        "duplicate": (summary or {}).get("duplicate", False),
        "affected_worker_count": (summary or {}).get("affected_worker_count", 0),
        "claims_created": (summary or {}).get("claims_created", 0),
        "auto_paid_claims": (summary or {}).get("auto_paid_claims", 0),
        "flagged_claims": (summary or {}).get("flagged_claims", 0),
        "manual_review_claims": (summary or {}).get("manual_review_claims", 0),
        "paid_payouts": (summary or {}).get("paid_payouts", 0),
        "held_payouts": (summary or {}).get("held_payouts", 0),
        "demo_note": demo_note,
    }
