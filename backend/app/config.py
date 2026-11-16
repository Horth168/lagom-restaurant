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

    # --- ABA PayWay ---
    aba_payway_merchant_id: str = ""
    aba_payway_api_key: str = ""
    # Sandbox: https://checkout-sandbox.payway.com.kh   Production: https://checkout.payway.com.kh
    aba_payway_base_url: str = "https://checkout-sandbox.payway.com.kh"
    # RSA public key from ABA, only needed for refunds through the API (PEM text)
    aba_payway_rsa_public_key: str = ""
    # DEVELOPMENT ONLY: use the built-in PayWay simulator instead of the real sandbox.
    # The server refuses to start with this switched on in production.
    payway_simulator: bool = False
    # Minutes a customer has to pay before an unpaid order expires
    payment_lifetime_minutes: int = 15

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
    def payway_enabled(self) -> bool:
        return bool(self.aba_payway_merchant_id and self.aba_payway_api_key) or self.payway_simulator

    @property
    def payway_is_sandbox(self) -> bool:
        return "sandbox" in self.aba_payway_base_url

    def validate_for_production(self) -> list[str]:
        """Return a list of configuration problems that must be fixed before going live."""
        problems = []
        if self.secret_key.startswith("dev-only") or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be a long random value")
        if self.database_url.startswith("sqlite"):
            problems.append("DATABASE_URL must point to PostgreSQL in production")
        if self.payway_simulator:
            problems.append("PAYWAY_SIMULATOR must be off in production")
        if not (self.aba_payway_merchant_id and self.aba_payway_api_key):
            problems.append("ABA PayWay credentials are missing")
        elif self.payway_is_sandbox:
            problems.append("ABA_PAYWAY_BASE_URL still points to the sandbox")
        if not self.backend_url.startswith("https://"):
            problems.append("BACKEND_URL must use https")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
