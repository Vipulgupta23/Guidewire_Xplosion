"""
Policies Router — Plan listing, subscription, renewal, history.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone
import uuid

from app.database import get_supabase
from app.services.policy_service import expire_stale_policies, is_policy_current
from app.services.pricing_quote_service import build_pricing_quote

router = APIRouter(prefix="/policies", tags=["policies"])


class SubscribeRequest(BaseModel):
    worker_id: str
    plan_id: str  # basic, plus, pro
    mock_payment_id: Optional[str] = None


@router.get("/plans/{worker_id}")
async def get_plans_for_worker(worker_id: str):
    """Get all 3 plans with dynamic premium calculated for this worker."""
    db = get_supabase()

    worker_res = (
        db.table("workers")
        .select("*")
        .eq("id", worker_id)
        .single()
        .execute()
    )
    if not worker_res.data:
        raise HTTPException(status_code=404, detail="Worker not found")
    worker = worker_res.data

    plans_res = db.table("plans").select("*").execute()
    plans = plans_res.data or []

    result = []
    for plan in plans:
        try:
            quote = await build_pricing_quote(worker, plan)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        premium = quote["breakdown"]
        result.append(
            {
                **plan,
                "premium_details": premium,
                "dynamic_premium": premium["final_premium"],
            }
        )

    return {
        "plans": result,
        "worker": worker,
        "grid_label": worker.get("city", "Coverage Pending"),
    }


@router.post("/subscribe")
async def subscribe_to_plan(req: SubscribeRequest):
    """Subscribe to a plan — creates policy with dynamic premium."""
    db = get_supabase()

    worker_res = (
        db.table("workers")
        .select("*")
        .eq("id", req.worker_id)
        .single()
        .execute()
    )
    if not worker_res.data:
        raise HTTPException(status_code=404, detail="Worker not found")
    worker = worker_res.data

    plan_res = (
        db.table("plans")
        .select("*")
        .eq("id", req.plan_id)
        .single()
        .execute()
    )
    if not plan_res.data:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = plan_res.data

    try:
        quote = await build_pricing_quote(worker, plan)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    premium = quote["breakdown"]
    resolved_grid = quote["resolved_grid"]
    quote_row = quote["quote"]

    now = datetime.now(timezone.utc)
    policy_data = {
        "worker_id": req.worker_id,
        "plan_id": req.plan_id,
        "status": "active",
        "weekly_premium_actual": premium["final_premium"],
        "premium_base": plan["weekly_premium_base"],
        "zone_risk_multiplier": premium["zone_multiplier"],
        "seasonal_factor": premium["seasonal_factor"],
        "iss_discount": premium["iss_discount"],
        "persona_factor": premium["persona_factor"],
        "start_date": now.date().isoformat(),
        "end_date": (now + timedelta(days=7)).date().isoformat(),
        "total_paid_this_week": 0,
        "quote_id": quote_row["id"] if quote_row else None,
        "pricing_version": premium.get("pricing_version"),
        "resolved_grid_id": resolved_grid["id"],
        "resolved_city": resolved_grid["city"],
        "feature_snapshot": quote_row["feature_snapshot"] if quote_row else None,
        "feature_freshness": quote_row["feature_freshness"] if quote_row else None,
        "mock_payment_id": req.mock_payment_id
        or f"MOCK_{uuid.uuid4().hex[:12]}",
    }

    # Deactivate any existing active policy
    db.table("policies").update({"status": "expired"}).eq(
        "worker_id", req.worker_id
    ).eq("status", "active").execute()

    result = db.table("policies").insert(policy_data).execute()
    if not result.data:
        raise HTTPException(
            status_code=500, detail="Failed to create policy"
        )

    return {
        "policy": result.data[0],
        "premium_breakdown": premium,
        "message": "Policy activated! You're now covered.",
    }


@router.get("/active/{worker_id}")
async def get_active_policy(worker_id: str):
    """Get current active policy for worker."""
    db = get_supabase()
    expire_stale_policies(worker_id)
    result = (
        db.table("policies")
        .select("*, plans(*)")
        .eq("worker_id", worker_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return {"policy": None, "message": "No active policy"}
    current = next((policy for policy in (result.data or []) if is_policy_current(policy)), None)
    if not current:
        return {"policy": None, "message": "No active policy"}
    return {"policy": current}


@router.put("/renew/{policy_id}")
async def renew_policy(policy_id: str):
    """Renew policy for next week with recalculated premium."""
    db = get_supabase()

    policy_res = (
        db.table("policies")
        .select("*, plans(*)")
        .eq("id", policy_id)
        .single()
        .execute()
    )
    if not policy_res.data:
        raise HTTPException(status_code=404, detail="Policy not found")

    old = policy_res.data
    plan = old.get("plans", {})
    worker_res = (
        db.table("workers")
        .select("*")
        .eq("id", old["worker_id"])
        .single()
        .execute()
    )
    worker = worker_res.data

    try:
        quote = await build_pricing_quote(worker, plan)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    premium = quote["breakdown"]
    resolved_grid = quote["resolved_grid"]
    quote_row = quote["quote"]

    now = datetime.now(timezone.utc)
    # Expire old
    db.table("policies").update({"status": "expired"}).eq(
        "id", policy_id
    ).execute()

    # Create new
    new_policy = {
        "worker_id": old["worker_id"],
        "plan_id": old["plan_id"],
        "status": "active",
        "weekly_premium_actual": premium["final_premium"],
        "premium_base": plan["weekly_premium_base"],
        "zone_risk_multiplier": premium["zone_multiplier"],
        "seasonal_factor": premium["seasonal_factor"],
        "iss_discount": premium["iss_discount"],
        "persona_factor": premium["persona_factor"],
        "start_date": now.date().isoformat(),
        "end_date": (now + timedelta(days=7)).date().isoformat(),
        "quote_id": quote_row["id"] if quote_row else None,
        "pricing_version": premium.get("pricing_version"),
        "resolved_grid_id": resolved_grid["id"],
        "resolved_city": resolved_grid["city"],
        "feature_snapshot": quote_row["feature_snapshot"] if quote_row else None,
        "feature_freshness": quote_row["feature_freshness"] if quote_row else None,
        "mock_payment_id": f"MOCK_{uuid.uuid4().hex[:12]}",
    }
    result = db.table("policies").insert(new_policy).execute()

    return {
        "policy": result.data[0] if result.data else None,
        "premium_breakdown": premium,
        "previous_premium": old["weekly_premium_actual"],
    }


@router.get("/history/{worker_id}")
async def get_policy_history(worker_id: str):
    """Get all past policies."""
    db = get_supabase()
    result = (
        db.table("policies")
        .select("*, plans(*)")
        .eq("worker_id", worker_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return result.data or []
