"""LAGOM backend entry point.

Run locally:  uvicorn app.main:app --reload
API docs:     http://localhost:8000/docs
"""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth, orders_public, public, settings, staff, tables
from app.config import get_settings
from app.db import SessionLocal, engine

log = logging.getLogger("lagom")


def _expire_once() -> int:
    from app.services.payments import expire_due_orders
    from app.services.payway import get_payway

    with SessionLocal() as db:
        return expire_due_orders(db, get_payway())


async def _expiry_loop() -> None:
    """Every minute: expire unpaid orders (after a last check with PayWay)."""
    while True:
        try:
            n = await asyncio.to_thread(_expire_once)
            if n:
                log.info("Expired %s unpaid orders", n)
        except Exception:
            log.exception("Expiry job failed")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.is_production:
        problems = s.validate_for_production()
        if problems:
            # Refuse to start a misconfigured production server (e.g. sandbox payments)
            raise RuntimeError("Production configuration problems: " + "; ".join(problems))
    if s.payway_simulator:
        log.warning("PAYWAY SIMULATOR IS ON - development only, no real money is involved")
    task = asyncio.create_task(_expiry_loop()) if s.environment != "test" else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="LAGOM API",
        version="0.2.0",
        description="JUST THE RIGHT AMOUNT. — Restaurant ordering, POS and management API",
        lifespan=lifespan,
        docs_url=None if s.is_production else "/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    @app.get("/api/health", tags=["system"])
    def health():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "environment": s.environment}

    for r in (auth.router, staff.router, settings.router, public.router, tables.router, orders_public.router):
        app.include_router(r)
    return app


app = create_app()
