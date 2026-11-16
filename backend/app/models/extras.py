"""Shift reports, table service requests, reviews, timed deals and Telegram loyalty cards."""
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import UTCDateTime, utcnow


class CashShift(Base):
    """One cashier shift on the cash drawer: money at the start, money counted at the end.

    LAGOM works out how much cash *should* be in the drawer (start money + cash sales
    - cash refunds) so a difference is visible at closing time. Kept per currency.
    """

    __tablename__ = "cash_shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    opened_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    opening_usd_cents: Mapped[int] = mapped_column(Integer, default=0)
    opening_khr: Mapped[int] = mapped_column(Integer, default=0)
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    # Filled at closing time (snapshot, never recalculated)
    expected_usd_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_khr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counted_usd_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counted_khr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cash_orders: Mapped[int] = mapped_column(Integer, default=0)
    khqr_usd_cents: Mapped[int] = mapped_column(Integer, default=0)  # for information
    note: Mapped[str] = mapped_column(Text, default="")


class ServiceRequest(Base):
    """A customer at a table pressed "Call waiter" or "Request the bill"."""

    __tablename__ = "service_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_session_id: Mapped[int] = mapped_column(ForeignKey("table_sessions.id"), index=True)
    table_label: Mapped[str] = mapped_column(String(40), default="")
    kind: Mapped[str] = mapped_column(String(10))  # waiter | bill
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    resolved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class OrderReview(Base):
    """A customer's rating of one order (once per order)."""

    __tablename__ = "order_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    stars: Mapped[int] = mapped_column(Integer)  # 1–5
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class ItemRating(Base):
    """Stars for one dish inside a reviewed order (optional per dish)."""

    __tablename__ = "item_ratings"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("order_items.id"), unique=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    name_en: Mapped[str] = mapped_column(String(160))  # snapshot: the dish may be renamed later
    stars: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Deal(Base):
    """A timed discount, e.g. "Happy hour: coffee 20% off, Mon–Fri 14:00–17:00".

    Applies to one product, one category, or (both empty) the whole menu. The server
    applies it while pricing, so the price a customer pays is always the server's.
    """

    __tablename__ = "deals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    percent: Mapped[int] = mapped_column(Integer)  # 1–90
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=True)
    weekdays: Mapped[str] = mapped_column(String(7), default="0123456")  # 0 = Monday … 6 = Sunday
    start_time: Mapped[str] = mapped_column(String(5), default="00:00")  # restaurant time, HH:MM
    end_time: Mapped[str] = mapped_column(String(5), default="23:59")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class LoyaltyCard(Base):
    """Stamp card of one Telegram customer (Telegram Mini App orders only)."""

    __tablename__ = "loyalty_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[str] = mapped_column(String(32), unique=True)
    stamps: Mapped[int] = mapped_column(Integer, default=0)
    rewards: Mapped[int] = mapped_column(Integer, default=0)  # free items ready to use
    rewards_used: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
