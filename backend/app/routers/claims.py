"""
Claims Router — Worker claims, detail view, fallback submission, and admin review actions.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.database import get_supabase
from app.services.claim_service import (
    approve_claim_review,
    build_fraud_report,
    get_claim_detail as get_claim_detail_service,
    get_claims_for_worker,
    get_worker_fallback_eligibility,
    reject_claim_review,
    submit_fallback_claim,
)

router = APIRouter(prefix="/claims", tags=["claims"])


class ReviewClaimRequest(BaseModel):
    reviewer: str = "admin"
    reason: str | None = None
    note: str | None = None


class FallbackClaimRequest(BaseModel):
    worker_id: str
    disruption_id: str
    reason: str | None = None


@router.get("/worker/{worker_id}")
async def get_worker_claims(worker_id: str, limit: int = 10):
    """Get worker claims with fallback eligibility summary."""
    return {
        "claims": get_claims_for_worker(worker_id, limit=limit),
        "eligibility": get_worker_fallback_eligibility(worker_id),
    }


@router.get("/eligibility/{worker_id}")
async def get_claim_eligibility(worker_id: str):
    """Get fallback eligibility windows for missed disruptions."""
    return get_worker_fallback_eligibility(worker_id)


@router.post("/fallback")
async def create_fallback_claim(req: FallbackClaimRequest):
    """Create a controlled fallback claim for a missed automated disruption."""
    claim = submit_fallback_claim(req.worker_id, req.disruption_id, req.reason)
    return {
        "message": "Fallback claim submitted for review",
        "claim": claim,
    }


@router.get("/{claim_id}")
async def get_claim_detail(claim_id: str):
    """Get full claim detail including payouts, events, and fraud summary."""
    return get_claim_detail_service(claim_id)


@router.get("/{claim_id}/fraud-report")
async def get_claim_fraud_report(claim_id: str):
    """Get canonical fraud report for this claim."""
    claim = get_claim_detail_service(claim_id)
    return build_fraud_report(claim)


@router.get("/payouts/{worker_id}")
async def get_worker_payouts(worker_id: str):
    """Get payout history for a worker."""
    db = get_supabase()
    result = (
        db.table("payouts")
        .select("*, claims(*)")
        .eq("worker_id", worker_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    return result.data or []


@router.put("/{claim_id}/approve")
async def approve_claim(claim_id: str, req: ReviewClaimRequest | None = None):
    """Approve a flagged or manual-review claim."""
    payload = req or ReviewClaimRequest()
    claim = approve_claim_review(
        claim_id,
        reviewer=payload.reviewer,
        reason=payload.reason,
        note=payload.note,
    )
    return {"message": "Claim approved after review", "claim": claim}


@router.put("/{claim_id}/reject")
async def reject_claim(claim_id: str, req: ReviewClaimRequest | None = None):
    """Reject a flagged or manual-review claim."""
    payload = req or ReviewClaimRequest()
    claim = reject_claim_review(
        claim_id,
        reviewer=payload.reviewer,
        reason=payload.reason,
        note=payload.note,
    )
    return {"message": "Claim rejected", "claim": claim}
