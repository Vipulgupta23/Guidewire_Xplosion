"""
Auth Router — Supabase Email + Password authentication.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.database import get_supabase, get_supabase_anon

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_worker_by_email(email: str):
    db = get_supabase()
    try:
        worker_res = (
            db.table("workers")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        return worker_res.data[0] if worker_res.data else None
    except Exception:
        # Schema may not be initialized yet in local development.
        return None


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
async def login(req: LoginRequest):
    """Sign in with email and password."""
    email = req.email.strip().lower()
    auth_client = get_supabase_anon()

    try:
        result = auth_client.auth.sign_in_with_password(
            {"email": email, "password": req.password}
        )

        session = result.session
        user = result.user

        if not session:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        worker = _get_worker_by_email(email)

        return {
            "success": True,
            "access_token": session.access_token,
            "user_id": user.id if user else None,
            "worker": worker,
            "is_new": worker is None,
        }
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "invalid" in error_msg.lower() or "credentials" in error_msg.lower():
            raise HTTPException(status_code=401, detail="Invalid email or password")
        raise HTTPException(status_code=400, detail=error_msg)


@router.post("/signup")
async def signup(req: SignupRequest):
    """Create a new account with email and password."""
    email = req.email.strip().lower()
    auth_client = get_supabase_anon()

    try:
        result = auth_client.auth.sign_up(
            {"email": email, "password": req.password}
        )

        user = result.user

        # Supabase may require email confirmation — handle gracefully
        if not user:
            raise HTTPException(
                status_code=400,
                detail="Signup failed. Please try again.",
            )

        # Try to immediately sign in so we get a session token
        try:
            login_result = auth_client.auth.sign_in_with_password(
                {"email": email, "password": req.password}
            )
            session = login_result.session
        except Exception:
            session = None

        worker = _get_worker_by_email(email)

        return {
            "success": True,
            "access_token": session.access_token if session else f"pending-{user.id}",
            "user_id": user.id,
            "worker": worker,
            "is_new": worker is None,
            "confirmation_required": session is None,
        }
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "already registered" in error_msg.lower() or "already exists" in error_msg.lower():
            raise HTTPException(
                status_code=409, detail="An account with this email already exists. Please log in."
            )
        raise HTTPException(status_code=400, detail=error_msg)


@router.get("/profile/{worker_id}")
async def get_profile(worker_id: str):
    """Get worker profile."""
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
    return result.data
