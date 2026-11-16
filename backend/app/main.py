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

from app.api import (auth, finance, inventory, kds, menu_admin, orders_admin, orders_public, payments_admin, pos,
                     public, settings, staff, tables)
from app.services import inventory as _inventory_hooks  # noqa: F401  (deducts stock when orders are paid)
from app.config import get_settings
from app.db import SessionLocal, engine

log = logging.getLogger("lagom")


def _expire_once() -> int:
    from app.services.payments import expire_due_orders

    with SessionLocal() as db:
        return expire_due_orders(db)


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
    from app.services.realtime import hub

    hub.bind_loop(asyncio.get_running_loop())  # live updates are sent from this event loop
    if s.khqr_test_mode:
        log.warning("KHQR TEST MODE IS ON - development only, payments can be faked")
    task = None
    if s.environment != "test":
        task = asyncio.create_task(_expiry_loop())
        from app.services import tg_listener

        tg_listener.start()  # reads ABA's payment notices (only if configured)
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

    for r in (auth.router, staff.router, settings.router, public.router, tables.router, orders_public.router,
              payments_admin.router, kds.router, menu_admin.router, orders_admin.router, pos.router,
              inventory.router, finance.router):
        app.include_router(r)
    # Product photos saved on this server (when Cloudflare R2 is not configured)
    from fastapi.staticfiles import StaticFiles

    from app.services.storage import LOCAL_DIR

    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=LOCAL_DIR), name="uploads")
    return app


app = create_app()
