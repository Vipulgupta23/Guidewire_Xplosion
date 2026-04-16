from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.database import get_supabase
from app.services.live_grid_service import get_live_grids
from app.utils.microgrid_utils import get_city_by_name, get_grid_by_id
from app.services.pricing_feature_service import get_grid_history_context


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_grid_prediction(grid_live_status: dict) -> dict:
    snapshot = grid_live_status.get("feature_snapshot") or {}
    risk = max(
        _safe_float(snapshot.get("flood_risk")),
        _safe_float(snapshot.get("aqi_norm")),
        _safe_float(snapshot.get("heat_index_norm")),
        _safe_float(snapshot.get("traffic_risk")),
    )
    predictive_hours = int(_safe_float(snapshot.get("predictive_risk_hours")))
    expected_claims = round(grid_live_status.get("insured_worker_count", 0) * max(risk, 0.05), 2)
    expected_payout_liability = round(
        expected_claims * (220 + predictive_hours * 18),
        2,
    )
    confidence = min(0.98, 0.55 + risk * 0.4)
    if risk >= 0.72:
        severity_label = "High"
    elif risk >= 0.38:
        severity_label = "Moderate"
    else:
        severity_label = "Low"
    return {
        "grid_id": grid_live_status.get("id"),
        "city": grid_live_status.get("city"),
        "severity_label": severity_label,
        "risk_score": round(risk, 4),
        "confidence": round(confidence, 2),
        "predictive_risk_hours": predictive_hours,
        "expected_claims": expected_claims,
        "expected_payout_liability": expected_payout_liability,
        "recommended_message": (
            "Pre-alert workers and keep payout reserves warm."
            if risk >= 0.72
            else "Monitor closely for disruption escalation."
            if risk >= 0.38
            else "No immediate action required."
        ),
    }


def get_worker_predictions(worker_id: str) -> dict:
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
        return {"worker_id": worker_id, "alerts": []}

    grid_id = worker.get("grid_id")
    if not grid_id:
        return {"worker_id": worker_id, "alerts": []}

    live_grid = next((row for row in get_live_grids(worker.get("city")) if row.get("id") == grid_id), None)
    if not live_grid:
        return {"worker_id": worker_id, "alerts": []}

    grid = get_grid_by_id(grid_id)
    city_meta = get_city_by_name(worker.get("city", ""))
    history_context = {}
    if grid and city_meta:
        history_context = get_grid_history_context(grid_id, city_meta["slug"], live_grid.get("feature_snapshot") or {})

    prediction = build_grid_prediction(live_grid)
    alert = {
        "type": "next_disruption_watch",
        "title": f"{prediction['severity_label']} disruption watch for {worker.get('city')}",
        "description": (
            f"Your zone may face {prediction['predictive_risk_hours']}h of disruption pressure. "
            f"Expected claimable risk is ₹{int(prediction['expected_payout_liability'])} across the protected cohort."
        ),
        "risk_score": prediction["risk_score"],
        "confidence": prediction["confidence"],
        "predictive_risk_hours": prediction["predictive_risk_hours"],
        "flood_delta": history_context.get("flood_delta"),
        "waterlogging_label": history_context.get("waterlogging_label"),
    }
    return {
        "worker_id": worker_id,
        "grid_id": grid_id,
        "alerts": [alert],
    }


def get_admin_predictive_analytics() -> dict:
    grids = get_live_grids()
    predictions = [build_grid_prediction(grid) for grid in grids]
    city_rollup: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "city": "",
        "grid_count": 0,
        "high_risk_grids": 0,
        "expected_claims": 0.0,
        "expected_payout_liability": 0.0,
    })

    for prediction in predictions:
        city = prediction["city"] or "Unknown"
        rollup = city_rollup[city]
        rollup["city"] = city
        rollup["grid_count"] += 1
        rollup["high_risk_grids"] += 1 if prediction["severity_label"] == "High" else 0
        rollup["expected_claims"] += prediction["expected_claims"]
        rollup["expected_payout_liability"] += prediction["expected_payout_liability"]

    hotspots = sorted(predictions, key=lambda item: item["expected_payout_liability"], reverse=True)[:8]
    cities = sorted(
        [
            {
                **value,
                "expected_claims": round(value["expected_claims"], 2),
                "expected_payout_liability": round(value["expected_payout_liability"], 2),
            }
            for value in city_rollup.values()
        ],
        key=lambda item: item["expected_payout_liability"],
        reverse=True,
    )
    return {
        "hotspots": hotspots,
        "cities": cities,
        "summary": {
            "next_week_expected_claims": round(sum(item["expected_claims"] for item in predictions), 2),
            "next_week_expected_payout_liability": round(sum(item["expected_payout_liability"] for item in predictions), 2),
            "high_risk_grid_count": sum(1 for item in predictions if item["severity_label"] == "High"),
        },
    }
