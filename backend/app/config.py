"""Application settings.

Every value comes from environment variables (or a local `.env` file that is
never committed). See `backend/.env.example` for the full list with comments.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    environment: Literal["development", "test", "staging", "production"] = "development"
    app_name: str = "LAGOM"
    # Public URL of the frontend (used in QR codes and payment return links)
    frontend_url: str = "http://localhost:5173"
    # Public URL of this backend (used for the ABA PayWay callback)
    backend_url: str = "http://localhost:8000"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Database ---
    database_url: str = "sqlite:///./lagom.db"

    # --- Security ---
    secret_key: str = "dev-only-change-me-dev-only-change-me"
    access_token_minutes: int = 60 * 12  # one staff shift
    login_rate_limit_per_minute: int = 10

    # --- Payments: ABA KHQR confirmed from ABA's Telegram notifications ---
    # Text inside the shop's own ABA KHQR (scan your printed ABA QR with any QR reader and copy the text)
    khqr_template: str = ""
    khqr_store_label: str = "LAGOM"
    # The Telegram group where ABA's PayWay bot posts "$X paid by …" (a negative number like -100…)
    payway_chat_id: str = ""
    payway_bot_username: str = "PayWayByABA_bot"
    # A normal Telegram account that reads that group (bots cannot see other bots' messages).
    # Create with: python -m scripts.telegram_login
    tg_listener_api_id: str = ""
    tg_listener_api_hash: str = ""
    tg_listener_session: str = ""
    # Minutes a customer has to pay by KHQR / at the counter before an unpaid order expires
    payment_lifetime_minutes: int = 15
    cash_lifetime_minutes: int = 60
    # DEVELOPMENT ONLY: adds a button that fakes ABA's Telegram notice. Refused in production.
    khqr_test_mode: bool = False

    # --- Telegram (optional) ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- File storage (Cloudflare R2, S3-compatible). Empty = save to local disk ---
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_public_base_url: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def khqr_enabled(self) -> bool:
        return bool(self.khqr_template.strip())

    @property
    def listener_enabled(self) -> bool:
        return bool(self.tg_listener_api_id and self.tg_listener_api_hash and self.tg_listener_session
                    and self.payway_chat_id.strip())

    def validate_for_production(self) -> list[str]:
        """Return a list of configuration problems that must be fixed before going live."""
        problems = []
        if self.secret_key.startswith("dev-only") or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be a long random value")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point to PostgreSQL in production")
        if self.khqr_test_mode:
            problems.append("KHQR_TEST_MODE must be off in production")
        if not self.backend_url.startswith("https://"):
            problems.append("BACKEND_URL must use https")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
