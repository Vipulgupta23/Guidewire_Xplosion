from __future__ import annotations

from datetime import datetime, timezone

from app.database import get_supabase


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _policy_window(policy: dict) -> tuple[datetime | None, datetime | None]:
    start_dt = _parse_dt(f"{policy.get('start_date')}T00:00:00+00:00")
    end_dt = _parse_dt(f"{policy.get('end_date')}T23:59:59+00:00")
    return start_dt, end_dt


def policy_covers_datetime(policy: dict, event_dt: datetime | None) -> bool:
    if not event_dt:
        return False
    start_dt, end_dt = _policy_window(policy)
    if not start_dt or not end_dt:
        return False
    return start_dt <= event_dt <= end_dt


def is_policy_current(policy: dict, now_dt: datetime | None = None) -> bool:
    now_dt = now_dt or datetime.now(timezone.utc)
    return policy_covers_datetime(policy, now_dt)


def expire_stale_policies(worker_id: str) -> None:
    db = get_supabase()
    policies = (
        db.table("policies")
        .select("id, start_date, end_date, status")
        .eq("worker_id", worker_id)
        .eq("status", "active")
        .execute()
    ).data or []
    stale_ids = [policy["id"] for policy in policies if not is_policy_current(policy)]
    if not stale_ids:
        return
    for policy_id in stale_ids:
        db.table("policies").update({"status": "expired"}).eq("id", policy_id).execute()

