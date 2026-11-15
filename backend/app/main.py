"""LAGOM backend entry point.

Run locally:  uvicorn app.main:app --reload
API docs:     http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import auth, settings, staff
from app.config import get_settings
from app.db import engine

log = logging.getLogger("lagom")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.is_production:
        problems = s.validate_for_production()
        if problems:
            # Refuse to start a misconfigured production server (e.g. sandbox payments)
            raise RuntimeError("Production configuration problems: " + "; ".join(problems))
    yield


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

    for r in (auth.router, staff.router, settings.router):
        app.include_router(r)
    return app


app = create_app()
