from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.notification_service import (
    DEFAULT_ADMIN_ENTITY_ID,
    get_notification_status,
    send_test_notification,
    upsert_telegram_link,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


class TelegramLinkRequest(BaseModel):
    entity_type: str
    entity_id: str
    chat_id: str
    username: str | None = None


class TelegramTestRequest(BaseModel):
    entity_type: str
    entity_id: str | None = None
    message: str | None = None


@router.post("/telegram/link")
async def link_telegram(req: TelegramLinkRequest):
    if req.entity_type not in {"worker", "admin"}:
        raise HTTPException(status_code=400, detail="entity_type must be worker or admin")
    row = upsert_telegram_link(
        entity_type=req.entity_type,
        entity_id=req.entity_id or DEFAULT_ADMIN_ENTITY_ID,
        chat_id=req.chat_id,
        username=req.username,
    )
    return {
        "message": "Telegram linked successfully",
        "link": row,
        "status": get_notification_status(req.entity_type, req.entity_id or DEFAULT_ADMIN_ENTITY_ID),
    }


@router.post("/telegram/test")
async def telegram_test(req: TelegramTestRequest):
    entity_id = req.entity_id or DEFAULT_ADMIN_ENTITY_ID
    result = await send_test_notification(req.entity_type, entity_id, req.message)
    return {
        "message": "Telegram test sent" if result.get("sent") else "Telegram test skipped",
        "result": result,
    }


@router.get("/telegram/status/{entity_type}/{entity_id}")
async def telegram_status(entity_type: str, entity_id: str):
    return get_notification_status(entity_type, entity_id)
