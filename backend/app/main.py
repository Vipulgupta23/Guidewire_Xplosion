"""
Incometrix AI — FastAPI Backend
Main application with CORS, routers, scheduler, and health check.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, workers, policies, premium, claims, microgrids, admin, notifications


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    print("🚀 Incometrix AI Backend starting...")

    # Start trigger scheduler
    try:
        from app.services.trigger_engine import start_scheduler
        start_scheduler()
    except Exception as e:
        print(f"⚠️  Scheduler start failed (non-critical): {e}")

    yield

    # Shutdown
    try:
        from app.services.trigger_engine import scheduler
        if scheduler.running:
            scheduler.shutdown()
    except Exception:
        pass
    print("👋 Incometrix AI Backend shutdown")


app = FastAPI(
    title="Incometrix AI",
    description="AI-Powered Income Protection for Delivery Workers",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL.rstrip("/") if settings.FRONTEND_URL else "",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3010",
        "http://127.0.0.1:3010",
        "https://incometrix.vercel.app",
        "https://gw-xp.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(workers.router)
app.include_router(policies.router)
app.include_router(premium.router)
app.include_router(claims.router)
app.include_router(microgrids.router)
app.include_router(admin.router)
app.include_router(notifications.router)


@app.get("/")
async def root():
    return {
        "name": "Incometrix AI",
        "version": "2.0.0",
        "status": "running",
        "description": "AI-Powered Income Protection for Delivery Workers",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "environment": settings.ENVIRONMENT}
