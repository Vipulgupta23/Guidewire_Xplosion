"""
Trigger Engine — APScheduler-based polling for weather/AQI disruptions.
Checks all active worker zones every 15 minutes.
"""

from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.database import get_supabase
from app.redis_client import get_redis
from app.services import weather_service, aqi_service
from app.services.claim_service import create_claim_for_disruption
from app.services.notification_service import notify_admins
from app.services.policy_service import policy_covers_datetime
from app.services.pricing_feature_service import refresh_grid_features
from app.utils.microgrid_utils import get_city_by_name, reconcile_worker_grid

scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

TRIGGERS = [
    {
        "type": "heavy_rainfall",
        "param": "rain_6h",
        "threshold": 50,
        "unit": "mm",
        "payout_max": 500,
    },
    {
        "type": "extreme_heat",
        "param": "temp",
        "threshold": 44,
        "unit": "°C",
        "payout_max": 400,
    },
    {
        "type": "severe_aqi",
        "param": "aqi",
        "threshold": 400,
        "unit": "AQI",
        "payout_max": 350,
    },
    {
        "type": "flood_alert",
        "param": "flood_score",
        "threshold": 0.78,
        "unit": "score",
        "payout_max": 550,
    },
    {
        "type": "platform_outage",
        "param": "platform_outage_score",
        "threshold": 0.95,
        "unit": "score",
        "payout_max": 300,
        "manual_only": True,
    },
    {
        "type": "curfew_bandh",
        "param": "civic_shutdown_score",
        "threshold": 0.95,
        "unit": "score",
        "payout_max": 450,
        "manual_only": True,
    },
    {
        "type": "cyclone_storm",
        "param": "storm_score",
        "threshold": 0.92,
        "unit": "score",
        "payout_max": 700,
        "manual_only": True,
    },
]


def get_6h_window() -> str:
    """Get current 6-hour window key for deduplication."""
    now = datetime.now(timezone.utc)
    window = now.hour // 6
    return f"{now.strftime('%Y%m%d')}_{window}"


def start_scheduler():
    """Start the trigger polling scheduler."""
    interval = settings.TRIGGER_POLL_INTERVAL_MINUTES

    @scheduler.scheduled_job("interval", minutes=interval, id="poll_zones")
    async def poll_all_zones():
        await _poll_all_zones()

    @scheduler.scheduled_job("interval", minutes=interval, id="refresh_live_features")
    async def refresh_live_features_job():
        await _refresh_active_grid_features()

    if not scheduler.running:
        scheduler.start()
        print(f"⏰ Trigger scheduler started (every {interval} min)")


async def _poll_all_zones():
    """Check weather + AQI for all grids with active workers."""
    db = get_supabase()
    redis = get_redis()

    # Heal stale worker grid assignments before polling.
    workers_res = (
        db.table("workers")
        .select("*")
        .eq("is_active", True)
        .execute()
    )
    grid_ids = []
    for worker in workers_res.data or []:
        grid = reconcile_worker_grid(worker, persist=True)
        if grid:
            grid_ids.append(grid["id"])
    grid_ids = list(set(grid_ids))

    for grid_id in grid_ids:
        grid_res = (
            db.table("microgrids")
            .select("*")
            .eq("id", grid_id)
            .single()
            .execute()
        )
        grid = grid_res.data
        if not grid:
            continue

        weather = await weather_service.get_current(
            grid["center_lat"], grid["center_lng"]
        )
        aqi_val = await aqi_service.get_current(
            grid["center_lat"], grid["center_lng"]
        )

        measurements = {
            "rain_6h": weather.get("rain_6h", 0),
            "temp": weather.get("temp", 30),
            "aqi": aqi_val,
            "flood_score": max(
                grid.get("flood_risk", 0),
                min(1.0, weather.get("rain_6h", 0) / 60),
            ),
            "platform_outage_score": 0.0,
            "civic_shutdown_score": 0.0,
            "storm_score": min(
                1.0,
                max(float(weather.get("wind_speed", 0)) / 60.0, float(weather.get("rain_6h", 0)) / 90.0),
            ),
        }

        for trigger in TRIGGERS:
            if trigger.get("manual_only"):
                continue
            value = measurements.get(trigger["param"], 0)
            if value >= trigger["threshold"]:
                dedup_key = (
                    f"trigger:{grid_id}:{trigger['type']}:{get_6h_window()}"
                )
                if not redis.exists(dedup_key):
                    redis.set(dedup_key, "1", ex=21600)  # 6hr TTL
                    await create_disruption_and_claims(
                        grid, trigger, value, weather, trigger_origin="live_detected"
                    )


async def _refresh_active_grid_features():
    """Refresh live pricing features for active worker grids."""
    db = get_supabase()
    workers_res = (
        db.table("workers")
        .select("*")
        .eq("is_active", True)
        .execute()
    )
    grid_ids = []
    for worker in workers_res.data or []:
        grid = reconcile_worker_grid(worker, persist=True)
        if grid:
            grid_ids.append(grid["id"])
    grid_ids = list(set(grid_ids))
    for grid_id in grid_ids:
        grid_res = (
            db.table("microgrids")
            .select("*")
            .eq("id", grid_id)
            .single()
            .execute()
        )
        grid = grid_res.data
        if not grid:
            continue
        city_meta = get_city_by_name(grid.get("city", ""))
        if not city_meta:
            continue
        try:
            await refresh_grid_features(grid, city_meta, force=True)
        except Exception as e:
            print(f"⚠️  Feature refresh failed for {grid_id}: {e}")


async def create_disruption_and_claims(
    grid: dict,
    trigger: dict,
    measured_value: float,
    raw_weather: dict,
    trigger_origin: str = "live_detected",
):
    """Create a disruption event and process claims for all affected workers."""
    db = get_supabase()
    started_at = datetime.now(timezone.utc).isoformat()
    since = datetime.now(timezone.utc).timestamp() - 21600
    since_iso = datetime.fromtimestamp(since, timezone.utc).isoformat()

    existing_res = (
        db.table("disruption_events")
        .select("*")
        .eq("grid_id", grid["id"])
        .eq("trigger_type", trigger["type"])
        .gte("started_at", since_iso)
        .order("started_at", desc=True)
        .limit(10)
        .execute()
    )
    recent_same_type = []
    for row in existing_res.data or []:
        row_started = row.get("started_at")
        if not row_started:
            continue
        try:
            row_dt = datetime.fromisoformat(row_started.replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - row_dt).total_seconds() <= 21600:
                recent_same_type.append(row)
        except Exception:
            continue
    if recent_same_type:
        existing = recent_same_type[0]
        return {
            "disruption": existing,
            "trigger_origin": ((existing.get("raw_data") or {}).get("trigger_origin") or trigger_origin),
            "duplicate": True,
            "affected_worker_count": 0,
            "claims_created": 0,
            "auto_paid_claims": 0,
            "flagged_claims": 0,
            "manual_review_claims": 0,
            "paid_payouts": 0,
            "held_payouts": 0,
        }

    # 1. Create disruption event
    disruption_data = {
        "trigger_type": trigger["type"],
        "grid_id": grid["id"],
        "city": grid.get("city", "Bengaluru"),
        "severity": measured_value,
        "threshold": trigger["threshold"],
        "weather_description": raw_weather.get("description", ""),
        "is_active": True,
        "raw_data": {
            **raw_weather,
            "trigger_origin": trigger_origin,
            "source_status": "manual" if trigger_origin == "admin_manual" else "live",
        },
        "started_at": started_at,
    }
    disruption_res = (
        db.table("disruption_events").insert(disruption_data).execute()
    )
    disruption = disruption_res.data[0] if disruption_res.data else None
    if not disruption:
        print(f"❌ Failed to create disruption: {trigger['type']}")
        return None

    # 2. Get all insured workers in this grid
    city_workers_res = (
        db.table("workers")
        .select("*")
        .eq("city", grid.get("city", ""))
        .eq("is_active", True)
        .execute()
    )
    workers = []
    for worker in city_workers_res.data or []:
        resolved_grid = reconcile_worker_grid(worker, persist=True)
        if resolved_grid and resolved_grid.get("id") == grid["id"]:
            workers.append(worker)

    affected_worker_count = 0
    claims_created = 0
    auto_paid_claims = 0
    flagged_claims = 0
    manual_review_claims = 0
    paid_payouts = 0
    held_payouts = 0

    for worker in workers:
        # Check worker has active policy
        policy_res = (
            db.table("policies")
            .select("*, plans(*)")
            .eq("worker_id", worker["id"])
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        policy = next(
            (
                row
                for row in (policy_res.data or [])
                if policy_covers_datetime(row, datetime.fromisoformat(started_at.replace("Z", "+00:00")))
            ),
            None,
        )
        if not policy:
            continue

        affected_worker_count += 1
        plan = policy.get("plans", {})
        claim = await _process_claim(worker, disruption, trigger, policy, plan)
        if not claim:
            continue
        claims_created += 1
        if claim.get("status") == "paid":
            auto_paid_claims += 1
            paid_payouts += 1
        elif claim.get("status") in {"soft_flagged", "hard_flagged"}:
            flagged_claims += 1
            if claim.get("latest_payout_status") == "held_for_review":
                held_payouts += 1
        elif claim.get("status") in {"manual_submitted", "manual_under_review"}:
            manual_review_claims += 1

    await notify_admins(
        "Grid disruption triggered",
        (
            f"{trigger['type'].replace('_', ' ').title()} in {grid.get('city')} {grid['id']}.\n"
            f"Affected riders: {affected_worker_count} | Claims: {claims_created} | Paid: {paid_payouts} | Held: {held_payouts}"
        ),
        {
            "grid_id": grid["id"],
            "city": grid.get("city"),
            "trigger_type": trigger["type"],
            "trigger_origin": trigger_origin,
            "claims_created": claims_created,
        },
    )

    return {
        "disruption": disruption,
        "trigger_origin": trigger_origin,
        "duplicate": False,
        "affected_worker_count": affected_worker_count,
        "claims_created": claims_created,
        "auto_paid_claims": auto_paid_claims,
        "flagged_claims": flagged_claims,
        "manual_review_claims": manual_review_claims,
        "paid_payouts": paid_payouts,
        "held_payouts": held_payouts,
    }


async def _process_claim(
    worker: dict,
    disruption: dict,
    trigger: dict,
    policy: dict,
    plan: dict,
):
    """Full Zero-Touch pipeline — no worker action needed."""
    claim = create_claim_for_disruption(
        worker,
        disruption,
        policy,
        plan,
        claim_origin="auto",
    )
    if not claim:
        return
    print(
        f"  ✅ Claim {claim.get('status', 'processing')} for {worker.get('name', 'worker')}: ₹{claim.get('payout_amount', 0)}"
    )
