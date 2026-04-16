"""
Workers Router — Registration, onboarding, platform linking.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.database import get_supabase
from app.services.live_grid_service import get_live_grid_detail
from app.services.notification_service import get_notification_status
from app.services.prediction_service import get_worker_predictions
from app.services import weather_service
from app.services.pricing_feature_service import get_grid_features
from app.services.pricing_config_service import get_active_pricing_config
from app.services.pricing_quote_service import build_pricing_quote
from app.utils.microgrid_utils import (
    find_grid_by_coordinates,
    infer_city_from_coords,
    is_supported_city,
    get_city_by_name,
    reconcile_worker_grid,
)
from app.ml.iss_calculator import calculate_iss
from app.ml.persona_classifier import classify_persona

router = APIRouter(prefix="/workers", tags=["workers"])


class RegisterRequest(BaseModel):
    email: str
    name: str
    phone: Optional[str] = None
    platform: str  # zomato, swiggy, zepto, amazon
    zone_lat: float = 12.9352
    zone_lng: float = 77.6245
    city: Optional[str] = None


class LinkPlatformRequest(BaseModel):
    worker_id: str
    platform_worker_id: str


@router.post("/register")
async def register_worker(req: RegisterRequest):
    """Register a new worker during onboarding."""
    db = get_supabase()

    # Check if worker already exists
    existing = (
        db.table("workers")
        .select("id")
        .eq("email", req.email)
        .limit(1)
        .execute()
    )
    if existing.data:
        return {"worker": existing.data[0], "message": "Worker already exists"}

    # Find microgrid via PostGIS
    grid = find_grid_by_coordinates(req.zone_lat, req.zone_lng)
    grid_id = grid["id"] if grid else None
    detected_city = (
        grid.get("city")
        if grid
        else infer_city_from_coords(req.zone_lat, req.zone_lng)
    )

    # Classify initial persona (defaults for new worker)
    persona = classify_persona(
        avg_hours_per_day=8.0,
        peak_hour_ratio=0.5,
        consistency=0.5,
    )

    worker_data = {
        "email": req.email,
        "name": req.name,
        "phone": req.phone,
        "platform": req.platform,
        "zone_lat": req.zone_lat,
        "zone_lng": req.zone_lng,
        "grid_id": grid_id,
        "city": detected_city if is_supported_city(detected_city) else (req.city or detected_city),
        "persona": persona,
        "iss_score": 50.0,
        "is_verified": False,
        "is_active": True,
        "avg_daily_earnings": 900.0,
        "avg_hourly_earnings": 90.0,
        "active_days_per_week": 5.0,
        "peak_hour_ratio": 0.5,
    }

    result = db.table("workers").insert(worker_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create worker")

    worker = result.data[0]

    # Create initial ISS history entry
    db.table("iss_history").insert(
        {
            "worker_id": worker["id"],
            "iss_score": 50.0,
            "consistency_score": 50.0,
            "regularity_score": 50.0,
            "zone_score": 60.0,
            "fraud_score_component": 100.0,
            "delta": 0,
        }
    ).execute()

    return {
        "worker": worker,
        "grid": grid,
        "message": "Worker registered successfully",
    }


@router.post("/link-platform")
async def link_platform(req: LinkPlatformRequest):
    """Mock platform linking — simulates Zomato/Swiggy verification."""
    db = get_supabase()

    # Simulate verification (mock — always succeeds)
    import random

    deliveries = random.randint(200, 1500)
    rating = round(random.uniform(3.8, 4.9), 1)

    db.table("workers").update(
        {
            "platform_worker_id": req.platform_worker_id,
            "is_verified": True,
        }
    ).eq("id", req.worker_id).execute()

    return {
        "verified": True,
        "deliveries_on_record": deliveries,
        "platform_rating": rating,
        "message": f"Verified ✅ — {deliveries} deliveries on record",
    }


@router.get("/{worker_id}")
async def get_worker(worker_id: str):
    """Get worker details."""
    db = get_supabase()
    result = (
        db.table("workers")
        .select("*")
        .eq("id", worker_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Worker not found")
    worker = result.data
    reconcile_worker_grid(worker, persist=True)
    return worker


@router.get("/{worker_id}/iss-history")
async def get_iss_history(worker_id: str):
    """Get ISS score history."""
    db = get_supabase()
    result = (
        db.table("iss_history")
        .select("*")
        .eq("worker_id", worker_id)
        .order("calculated_at", desc=True)
        .limit(30)
        .execute()
    )
    return result.data or []


@router.get("/{worker_id}/protection-status")
async def get_protection_status(worker_id: str):
    """Worker-safe summary for the dashboard."""
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
    reconcile_worker_grid(worker, persist=True)

    policy_res = (
        db.table("policies")
        .select("*, plans(*)")
        .eq("worker_id", worker_id)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    policy = policy_res.data[0] if policy_res.data else None

    disruption = None
    if worker.get("grid_id"):
        disruption_res = (
            db.table("disruption_events")
            .select("*")
            .eq("grid_id", worker["grid_id"])
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        disruption = disruption_res.data[0] if disruption_res.data else None

    latest_claim_res = (
        db.table("claims")
        .select("*, payouts(*)")
        .eq("worker_id", worker_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    latest_claim = latest_claim_res.data[0] if latest_claim_res.data else None
    latest_payout = None
    payout_summary = {
        "paid_amount": 0,
        "held_amount": 0,
        "latest_status": None,
    }
    if latest_claim:
        payouts = latest_claim.get("payouts") or []
        latest_payout = payouts[0] if payouts else None
        payout_summary = {
            "paid_amount": round(
                sum(float(p.get("amount", 0)) for p in payouts if p.get("status") == "paid"),
                2,
            ),
            "held_amount": round(
                sum(float(p.get("amount", 0)) for p in payouts if p.get("status") == "held_for_review"),
                2,
            ),
            "latest_status": latest_payout.get("status") if latest_payout else None,
        }

    weather = await weather_service.get_current(
        worker.get("zone_lat", 12.9352),
        worker.get("zone_lng", 77.6245),
    )
    next_hours_label = (
        f"Next 6h outlook · {weather.get('description', 'clear').title()}"
    )

    banner = {
        "is_active": False,
        "title": "No active disruption in your zone",
        "description": next_hours_label,
        "earning_drop": "₹0–₹0",
        "risk_percent": 20,
        "coverage_active": bool(policy),
    }

    if disruption:
        estimated_gap = 0
        if latest_claim and latest_claim.get("disruption_id") == disruption.get("id"):
            estimated_gap = int(latest_claim.get("income_gap", 0))
        else:
            estimated_gap = int(worker.get("avg_daily_earnings", 900) * 0.35)
        banner = {
            "is_active": True,
            "title": disruption.get("trigger_type", "disruption").replace("_", " ").title(),
            "description": disruption.get("weather_description") or "Automation detected a disruption in your insured zone.",
            "earning_drop": f"₹{max(estimated_gap - 120, 0)}–₹{estimated_gap + 120}",
            "risk_percent": min(95, int((disruption.get("severity", 0) / max(disruption.get("threshold", 1), 1)) * 70) + 25),
            "coverage_active": bool(policy),
        }

    grid_live_status = (
        get_live_grid_detail(worker["grid_id"])
        if worker.get("grid_id")
        else None
    )
    disruption_origin = (
        ((disruption or {}).get("raw_data") or {}).get("trigger_origin")
        if disruption
        else None
    )

    claim_status_label = None
    if latest_claim:
        claim_status_label = latest_claim.get("status", "processing").replace("_", " ")
    predictions = get_worker_predictions(worker_id)
    notification_status = get_notification_status("worker", worker_id)
    earnings_protected = round(
        payout_summary["paid_amount"] + payout_summary["held_amount"],
        2,
    )

    return {
        "worker": {
            "id": worker["id"],
            "name": worker.get("name"),
            "city": worker.get("city"),
            "grid_id": worker.get("grid_id"),
            "iss_score": worker.get("iss_score", 50),
            "persona": worker.get("persona"),
        },
        "coverage": {
            "is_supported_city": is_supported_city(worker.get("city", "")),
            "policy_active": bool(policy),
            "policy": policy,
        },
        "grid_live_status": grid_live_status,
        "active_disruption": disruption,
        "disruption_origin": disruption_origin,
        "latest_claim": latest_claim,
        "latest_payout": latest_payout,
        "payout_summary": payout_summary,
        "claim_status_label": claim_status_label,
        "banner": banner,
        "earnings_protected": earnings_protected,
        "notification_status": notification_status,
        "predictions": predictions.get("alerts", []),
    }


@router.get("/{worker_id}/pricing-context")
async def get_pricing_context(worker_id: str):
    """Expose live pricing inputs and freshness for the worker's current grid."""
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

    if not worker.get("grid_id"):
        raise HTTPException(status_code=400, detail="Worker has no supported pricing grid")

    from app.utils.microgrid_utils import get_grid_by_id

    grid = get_grid_by_id(worker["grid_id"])
    if not grid:
        raise HTTPException(status_code=404, detail="Pricing grid not found")
    city_meta = get_city_by_name(grid["city"])
    if not city_meta:
        raise HTTPException(status_code=404, detail="Supported city metadata missing")

    try:
        feature_row = await get_grid_features(grid, city_meta)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    config = get_active_pricing_config()
    plan_res = db.table("plans").select("*").eq("id", "plus").single().execute()
    try:
        quote = await build_pricing_quote(worker, plan_res.data)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return {
        "worker_id": worker_id,
        "city": city_meta["name"],
        "grid_id": grid["id"],
        "pricing_version": config["version"],
        "feature_snapshot": feature_row["feature_snapshot"],
        "feature_freshness": {
            "status": feature_row.get("source_status", "fresh"),
            "observed_at": feature_row.get("observed_at"),
            "expires_at": feature_row.get("expires_at"),
        },
        "sample_quote": quote["breakdown"],
    }


@router.get("/{worker_id}/predictions")
async def get_predictions(worker_id: str):
    """Get predictive disruption alerts for the worker's current grid."""
    return get_worker_predictions(worker_id)


@router.get("/{worker_id}/iss-breakdown")
async def get_iss_breakdown(worker_id: str):
    """Get live ISS factor breakdown and persona impact."""
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
    breakdown = calculate_iss(worker_id)
    return {
        "worker_id": worker_id,
        "iss_score": breakdown["iss_score"],
        "persona": worker.get("persona"),
        "factor_breakdown": {
            "consistency": breakdown["consistency"],
            "regularity": breakdown["regularity"],
            "zone_safety": breakdown["zone"],
            "trust": breakdown["trust"],
        },
        "impact_summary": (
            "Higher ISS unlocks lower weekly premiums and stronger auto-approval confidence."
            if breakdown["iss_score"] >= 70
            else "Keep your activity steady to improve premium discounts and payout confidence."
        ),
        "notification_status": get_notification_status("worker", worker_id),
    }
