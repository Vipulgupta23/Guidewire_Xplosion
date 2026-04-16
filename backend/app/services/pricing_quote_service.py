from datetime import datetime, timezone

from app.database import get_supabase
from app.ml.premium_engine import calculate_premium
from app.services.pricing_config_service import get_active_pricing_config
from app.services.pricing_feature_service import (
    get_grid_features,
    get_grid_history_context,
)
from app.utils.microgrid_utils import (
    get_city_by_name,
    reconcile_worker_grid,
)


async def build_pricing_quote(worker: dict, plan: dict) -> dict:
    db = get_supabase()
    config = get_active_pricing_config()
    grid = reconcile_worker_grid(worker, persist=True)
    if not grid:
        raise RuntimeError("Worker does not have a supported microgrid for live pricing.")

    city_meta = get_city_by_name(grid["city"])
    if not city_meta or not city_meta.get("pricing_enabled", True):
        raise RuntimeError("Worker city is not enabled for live pricing.")

    feature_row = await get_grid_features(grid, city_meta)
    features = feature_row["feature_snapshot"]
    history_context = get_grid_history_context(grid["id"], city_meta["slug"], features)
    premium_breakdown = calculate_premium(
        worker=worker,
        plan=plan,
        feature_snapshot=features,
        history_context=history_context,
        pricing_config=config,
        city_label=grid["city"],
    )
    expires_at = feature_row.get("expires_at")
    freshness_status = feature_row.get("source_status", "fresh")
    quote_status = "fresh" if freshness_status == "fresh" else "stale"
    premium_breakdown["feature_freshness"] = {
        "status": freshness_status,
        "observed_at": feature_row.get("observed_at"),
        "expires_at": expires_at,
    }

    quote_row = {
        "worker_id": worker["id"],
        "plan_id": plan["id"],
        "resolved_grid_id": grid["id"],
        "resolved_city": grid["city"],
        "pricing_version": config["version"],
        "feature_snapshot": features,
        "feature_freshness": premium_breakdown["feature_freshness"],
        "premium_breakdown": premium_breakdown,
        "final_premium": premium_breakdown["final_premium"],
        "quote_status": quote_status,
    }
    quote_res = db.table("pricing_quotes").insert(quote_row).execute()
    quote = quote_res.data[0] if quote_res.data else None

    return {
        "quote": quote,
        "breakdown": premium_breakdown,
        "resolved_grid": grid,
        "feature_row": feature_row,
        "pricing_version": config["version"],
    }
