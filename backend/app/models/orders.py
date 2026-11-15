from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UTCDateTime, str_enum
from app.models.enums import Currency, ItemStatus, OrderChannel, OrderStatus, Station


class DailyCounter(Base):
    """Gives each day's orders short numbers: 001, 002, … (reset every day)."""

    __tablename__ = "daily_counters"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, default=0)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("business_date", "number", name="uq_order_number_per_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    number: Mapped[int] = mapped_column(Integer)  # short daily number shown to staff and customer
    # Public reference used in URLs and payment descriptions (not guessable)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    channel: Mapped[OrderChannel] = mapped_column(str_enum(OrderChannel))
    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus), index=True)

    table_id: Mapped[int | None] = mapped_column(ForeignKey("dining_tables.id"), nullable=True, index=True)
    table_label: Mapped[str] = mapped_column(String(40), default="")  # snapshot
    table_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("table_sessions.id"), nullable=True, index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # The same key always returns the same order: protects against double taps / retries
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)

    # --- Amounts (locked at creation; never recalculated afterwards) ---
    subtotal_usd_cents: Mapped[int] = mapped_column(Integer)
    discount_usd_cents: Mapped[int] = mapped_column(Integer, default=0)
    discount_reason: Mapped[str] = mapped_column(String(160), default="")
    total_usd_cents: Mapped[int] = mapped_column(Integer)
    khr_per_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # exchange-rate snapshot
    total_khr: Mapped[int] = mapped_column(Integer)
    payment_currency: Mapped[Currency] = mapped_column(str_enum(Currency), default=Currency.USD)

    customer_note: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(5), default="en")
    estimated_ready_minutes: Mapped[int] = mapped_column(Integer, default=10)

    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    served_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    cancel_reason: Mapped[str] = mapped_column(String(255), default="")
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    inventory_deducted: Mapped[bool] = mapped_column(Boolean, default=False)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )
    payments: Mapped[list["Payment"]] = relationship(  # noqa: F821
        back_populates="order", order_by="Payment.id"
    )

    @property
    def display_number(self) -> str:
        return f"{self.number:03d}"


class OrderItem(Base):
    """One line of an order. Everything shown to staff is copied here (snapshot)."""

    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    name_en: Mapped[str] = mapped_column(String(160))
    name_km: Mapped[str] = mapped_column(String(160), default="")
    name_zh: Mapped[str] = mapped_column(String(160), default="")
    # [{"group": "Size", "option": "Large", "option_id": 3, "price_delta_usd_cents": 50, ...}]
    options: Mapped[list] = mapped_column(JSON, default=list)
    special_instructions: Mapped[str] = mapped_column(String(255), default="")
    unit_price_usd_cents: Mapped[int] = mapped_column(Integer)  # base + options
    quantity: Mapped[int] = mapped_column(Integer)
    line_total_usd_cents: Mapped[int] = mapped_column(Integer)
    station: Mapped[Station] = mapped_column(str_enum(Station), index=True)
    status: Mapped[ItemStatus] = mapped_column(str_enum(ItemStatus), default=ItemStatus.QUEUED)
    prep_minutes: Mapped[int] = mapped_column(Integer, default=10)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    order: Mapped[Order] = relationship(back_populates="items")
