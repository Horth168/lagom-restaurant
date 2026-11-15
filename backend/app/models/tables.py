import secrets
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UTCDateTime, utcnow


def new_table_token() -> str:
    # 32 random bytes → 43 URL-safe characters. Impossible to guess.
    return secrets.token_urlsafe(32)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


class DiningTable(TimestampMixin, Base):
    __tablename__ = "dining_tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(40), unique=True)  # "Table 01"
    seats: Mapped[int] = mapped_column(Integer, default=4)
    area: Mapped[str] = mapped_column(String(60), default="")  # "Indoor", "Terrace"
    # The secret printed inside the QR code. Rotating it invalidates old printed QR cards.
    qr_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=new_table_token)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    sessions: Mapped[list["TableSession"]] = relationship(back_populates="table")


class TableSession(Base):
    """One customer device at one table.

    When a phone scans the table QR code it receives a private session token.
    Orders are linked to this session, so another person scanning the same table
    cannot see this phone's orders. Scanning again on the same phone recovers the
    session (the token is kept in the phone's local storage).
    """

    __tablename__ = "table_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("dining_tables.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=new_session_token)
    language: Mapped[str] = mapped_column(String(5), default="en")
    telegram_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    table: Mapped[DiningTable] = relationship(back_populates="sessions")
