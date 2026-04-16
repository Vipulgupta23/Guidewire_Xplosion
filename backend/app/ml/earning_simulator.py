"""
Earning Simulator — Hour-by-hour breakdown of what worker
WOULD have earned vs what they actually earned during disruption.
"""

from collections import defaultdict

from app.database import get_supabase


def _peer_multiplier(worker: dict, disruption: dict) -> float:
    db = get_supabase()
    try:
        peers = (
            db.table("workers")
            .select("avg_hourly_earnings, peak_hour_ratio")
            .eq("grid_id", worker.get("grid_id"))
            .limit(20)
            .execute()
        ).data or []
    except Exception:
        peers = []
    if not peers:
        return 1.0
    peer_avg = sum(float(peer.get("avg_hourly_earnings", 90)) for peer in peers) / len(peers)
    worker_avg = float(worker.get("avg_hourly_earnings", 90))
    return max(0.85, min(peer_avg / max(worker_avg, 1.0), 1.2))


def _historical_hour_profile(worker_id: str) -> dict[int, float]:
    db = get_supabase()
    try:
        rows = (
            db.table("earning_records")
            .select("record_hour, earnings")
            .eq("worker_id", worker_id)
            .order("record_date", desc=True)
            .limit(240)
            .execute()
        ).data or []
    except Exception:
        rows = []
    buckets: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        hour = int(row.get("record_hour", 0))
        earnings = float(row.get("earnings", 0))
        if 0 <= hour <= 23 and earnings > 0:
            buckets[hour].append(earnings)
    return {
        hour: (sum(values) / len(values))
        for hour, values in buckets.items()
        if values
    }


def calculate(worker: dict, disruption: dict) -> dict:
    """Build hour-by-hour earning simulation."""

    started_at = disruption.get("started_at")
    if isinstance(started_at, str):
        from datetime import datetime

        try:
            started_at = datetime.fromisoformat(
                started_at.replace("Z", "+00:00")
            )
        except Exception:
            started_at = datetime.now()

    start_hour = started_at.hour if started_at else 12
    disruption_hours = 4  # assume 4-hour disruption
    end_hour = min(start_hour + disruption_hours, 22)

    PEAK_HOURS = [11, 12, 13, 19, 20, 21, 22]
    avg_hourly = worker.get("avg_hourly_earnings", 90)
    avg_delivery_value = max(avg_hourly / max(avg_hourly / 45, 1), 30)
    peak_hour_ratio = float(worker.get("peak_hour_ratio", 0.5))
    persona = str(worker.get("persona", "stabilizer"))
    historical_profile = _historical_hour_profile(worker.get("id"))
    peer_factor = _peer_multiplier(worker, disruption)

    # Disruption severity factor
    severity = disruption.get("severity", 50)
    threshold = disruption.get("threshold", 50)
    severity_ratio = severity / max(threshold, 1)
    disruption_factor = max(0.05, 1 - (severity_ratio - 1) * 0.6)
    if disruption.get("trigger_type") == "platform_outage":
        disruption_factor = 0.0
    elif disruption.get("trigger_type") in {"cyclone_storm", "flood_alert"}:
        disruption_factor = max(0.03, disruption_factor * 0.7)

    hourly_breakdown = []
    simulated_total = 0
    actual_total = 0

    for hour in range(start_hour, end_hour + 1):
        is_peak = hour in PEAK_HOURS
        surge = 1.20 + peak_hour_ratio * 0.25 if is_peak else 0.95 + (1 - peak_hour_ratio) * 0.1
        if persona == "hustler" and is_peak:
            surge += 0.1
        elif persona == "opportunist" and not is_peak:
            surge -= 0.08

        # Expected (without disruption)
        historical_hourly = historical_profile.get(hour, avg_hourly)
        expected_hourly = max(historical_hourly, avg_hourly * 0.75) * peer_factor
        deliveries_expected = round(expected_hourly * surge / max(avg_delivery_value, 1))
        earnings_expected = round(
            max(deliveries_expected, 1) * avg_delivery_value * surge, 2
        )

        # Actual (with disruption)
        deliveries_actual = round(deliveries_expected * disruption_factor)
        earnings_actual = round(earnings_expected * disruption_factor, 2)

        heavily_disrupted = disruption_factor < 0.20

        hourly_breakdown.append(
            {
                "hour_label": f"{hour}:00 – {hour + 1}:00",
                "is_peak": is_peak,
                "deliveries_expected": deliveries_expected,
                "earnings_expected": earnings_expected,
                "deliveries_actual": deliveries_actual,
                "earnings_actual": earnings_actual,
                "disrupted": heavily_disrupted,
                "surge_label": "🔥 Surge" if is_peak else "",
            }
        )

        simulated_total += earnings_expected
        actual_total += earnings_actual

    return {
        "simulated_earnings": round(simulated_total, 2),
        "actual_earnings": round(actual_total, 2),
        "income_gap": round(simulated_total - actual_total, 2),
        "disruption_hours": disruption_hours,
        "hourly_breakdown": hourly_breakdown,
        "disruption_factor": round(disruption_factor, 3),
        "peer_factor": round(peer_factor, 3),
        "persona": persona,
    }
