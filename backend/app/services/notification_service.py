from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from postgrest.exceptions import APIError

from app.config import settings
from app.database import get_supabase

CHANNEL_TELEGRAM = "telegram"
DEFAULT_ADMIN_ENTITY_ID = "default_admin"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_available(exc: Exception, table_name: str) -> bool:
    return table_name not in str(exc)


def get_channel_link(entity_type: str, entity_id: str, channel: str = CHANNEL_TELEGRAM) -> dict | None:
    db = get_supabase()
    try:
        result = (
            db.table("notification_links")
            .select("*")
            .eq("entity_type", entity_type)
            .eq("entity_id", entity_id)
            .eq("channel", channel)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
    except APIError as exc:
        if _table_available(exc, "notification_links"):
            raise
        return None
    return result.data[0] if result.data else None


def upsert_telegram_link(
    entity_type: str,
    entity_id: str,
    chat_id: str,
    username: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    db = get_supabase()
    row = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "channel": CHANNEL_TELEGRAM,
        "target_id": chat_id,
        "display_name": username or "",
        "is_verified": True,
        "is_active": True,
        "metadata": metadata or {},
        "updated_at": _now_iso(),
    }
    try:
        result = (
            db.table("notification_links")
            .upsert(row, on_conflict="entity_type,entity_id,channel")
            .execute()
        )
    except APIError as exc:
        if _table_available(exc, "notification_links"):
            raise
        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "channel": CHANNEL_TELEGRAM,
            "target_id": chat_id,
            "display_name": username or "",
            "is_verified": True,
            "is_active": True,
            "metadata": metadata or {},
            "simulated": True,
        }
    return result.data[0] if result.data else row


async def _send_telegram(chat_id: str, text: str) -> dict[str, Any]:
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        return {"sent": False, "reason": "telegram_not_configured"}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload)
        if response.is_success:
            data = response.json()
            return {
                "sent": True,
                "provider": "telegram",
                "provider_message_id": (((data.get("result") or {}).get("message_id"))),
            }
        return {
            "sent": False,
            "reason": f"telegram_error_{response.status_code}",
        }


async def send_telegram_notification(
    entity_type: str,
    entity_id: str,
    title: str,
    body: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    link = get_channel_link(entity_type, entity_id, CHANNEL_TELEGRAM)
    if not link:
        return {"sent": False, "reason": "telegram_not_linked"}

    text = f"*{title}*\n{body}"
    result = await _send_telegram(str(link.get("target_id")), text)
    _record_notification_event(
        entity_type=entity_type,
        entity_id=entity_id,
        channel=CHANNEL_TELEGRAM,
        title=title,
        body=body,
        sent=result.get("sent", False),
        metadata={**(metadata or {}), **result},
    )
    return result


async def notify_worker(
    worker_id: str,
    title: str,
    body: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return await send_telegram_notification("worker", worker_id, title, body, metadata)


async def notify_admins(
    title: str,
    body: str,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    db = get_supabase()
    try:
        result = (
            db.table("notification_links")
            .select("*")
            .eq("entity_type", "admin")
            .eq("channel", CHANNEL_TELEGRAM)
            .eq("is_active", True)
            .execute()
        )
        links = result.data or []
    except APIError as exc:
        if _table_available(exc, "notification_links"):
            raise
        links = []

    if not links:
        fallback = get_channel_link("admin", DEFAULT_ADMIN_ENTITY_ID, CHANNEL_TELEGRAM)
        links = [fallback] if fallback else []

    results = []
    for link in links:
        if not link:
            continue
        send_result = await _send_telegram(str(link.get("target_id")), f"*{title}*\n{body}")
        _record_notification_event(
            entity_type="admin",
            entity_id=str(link.get("entity_id") or DEFAULT_ADMIN_ENTITY_ID),
            channel=CHANNEL_TELEGRAM,
            title=title,
            body=body,
            sent=send_result.get("sent", False),
            metadata={**(metadata or {}), **send_result},
        )
        results.append(send_result)
    return results


async def send_test_notification(
    entity_type: str,
    entity_id: str,
    message: str | None = None,
) -> dict[str, Any]:
    return await send_telegram_notification(
        entity_type,
        entity_id,
        "Incometrix AI Test",
        message or "Telegram alerts are connected and ready for live disruptions.",
        {"kind": "test"},
    )


def get_notification_status(entity_type: str, entity_id: str) -> dict[str, Any]:
    link = get_channel_link(entity_type, entity_id, CHANNEL_TELEGRAM)
    return {
        "channel": CHANNEL_TELEGRAM,
        "linked": bool(link),
        "display_name": (link or {}).get("display_name"),
        "target_id": (link or {}).get("target_id"),
        "bot_configured": bool(settings.TELEGRAM_BOT_TOKEN),
    }


def _record_notification_event(
    entity_type: str,
    entity_id: str,
    channel: str,
    title: str,
    body: str,
    sent: bool,
    metadata: dict[str, Any] | None = None,
) -> None:
    db = get_supabase()
    row = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "channel": channel,
        "title": title,
        "body": body,
        "delivery_status": "sent" if sent else "skipped",
        "metadata": metadata or {},
        "created_at": _now_iso(),
    }
    try:
        db.table("notification_events").insert(row).execute()
    except APIError as exc:
        if _table_available(exc, "notification_events"):
            raise
