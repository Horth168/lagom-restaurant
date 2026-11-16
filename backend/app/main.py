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

from app.api import (audit_log, auth, extras, finance, inventory, kds, menu_admin, orders_admin, orders_public,
                     payments_admin, pos, public, settings, staff, tables)
from app.services import inventory as _inventory_hooks  # noqa: F401  (deducts stock when orders are paid)
from app.services import notifications as _notification_hooks  # noqa: F401  (Telegram alerts)
from app.services import loyalty as _loyalty_hooks  # noqa: F401  (Telegram stamp card)
from app.config import get_settings
from app.db import SessionLocal, engine

log = logging.getLogger("lagom")
# LAGOM's own messages (payment listener connected, orders expired, …) appear in the server logs
if not log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
    log.propagate = False


def _expire_once() -> int:
    from app.services.notifications import maybe_send_backup_reminder, maybe_send_daily_summary
    from app.services.payments import expire_due_orders

    with SessionLocal() as db:
        n = expire_due_orders(db)
        maybe_send_daily_summary(db)  # once a day, after closing time (Settings)
        maybe_send_backup_reminder(db)  # once a week (Monday morning)
        return n


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
    if s.is_production and not (s.r2_bucket and s.r2_access_key_id) and s.photo_storage == "disk":
        log.warning("Uploaded menu photos are saved on this server's disk and are LOST on every redeploy. "
                    "Set PHOTO_STORAGE=database or set up Cloudflare R2 (docs/DEPLOYMENT.md).")
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
        if s.is_production:  # browsers must always use https for this site
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    # Error messages in the user's language (see app/i18n.py)
    from fastapi import HTTPException as _HTTPException
    from fastapi.exception_handlers import http_exception_handler
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from app.i18n import pick_language, translate

    @app.exception_handler(StarletteHTTPException)
    async def translated_http_error(request, exc):
        lang = pick_language(request.headers.get("accept-language"))
        detail = exc.detail
        if isinstance(detail, str):
            detail = translate(detail, lang)
        elif isinstance(detail, dict) and isinstance(detail.get("message"), str):
            detail = {**detail, "message": translate(detail["message"], lang)}
        return await http_exception_handler(request, _HTTPException(exc.status_code, detail, getattr(exc, "headers", None)))

    @app.get("/api/health", tags=["system"])
    def health():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "environment": s.environment}

    for r in (auth.router, staff.router, settings.router, public.router, tables.router, orders_public.router,
              payments_admin.router, kds.router, menu_admin.router, orders_admin.router, pos.router,
              inventory.router, finance.router, audit_log.router, extras.router):
        app.include_router(r)
    # Product photos saved on this server (when Cloudflare R2 is not configured)
    from fastapi.staticfiles import StaticFiles

    from app.services.storage import LOCAL_DIR

    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=LOCAL_DIR), name="uploads")
    return app


app = create_app()
