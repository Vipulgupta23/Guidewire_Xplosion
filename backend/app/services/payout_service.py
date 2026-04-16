from __future__ import annotations

from datetime import datetime, timezone
import uuid


def build_upi_receipt(
    claim_id: str,
    amount: float,
    status: str,
    provider_ref: str | None = None,
) -> dict:
    provider_ref = provider_ref or f"UPI_SIM_{claim_id[:8]}_{uuid.uuid4().hex[:6].upper()}"
    return {
        "channel": "upi_simulated",
        "status": status,
        "amount": round(float(amount), 2),
        "currency": "INR",
        "provider": "Incometrix UPI Sandbox",
        "provider_ref": provider_ref,
        "settled_at": datetime.now(timezone.utc).isoformat() if status == "paid" else None,
        "status_label": {
            "paid": "Instantly paid to worker UPI",
            "held_for_review": "Held for fraud review",
            "cancelled": "Cancelled after review",
        }.get(status, status.replace("_", " ").title()),
    }


def build_mock_payout_id(prefix: str, claim_id: str) -> str:
    return f"{prefix}_{claim_id[:8]}_{uuid.uuid4().hex[:4].upper()}"
