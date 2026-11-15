from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import TimestampMixin, UTCDateTime, str_enum, utcnow
from app.models.enums import Role


class User(TimestampMixin, Base):
    """A staff account (owner, admin, cashier, kitchen…). Customers do not need accounts."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(str_enum(Role))
    # Extra permissions on top of the role, e.g. ["orders.refund"]
    extra_permissions: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Bumped on password change / deactivation to invalidate old tokens
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en")
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AuditLog(Base):
    """Who did what, and when. Never edited or deleted by the app."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class AppSetting(Base):
    """Owner-editable settings stored as key/value (exchange rate, display currency…)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
