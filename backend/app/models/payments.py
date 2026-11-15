from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UTCDateTime, str_enum, utcnow
from app.models.enums import Currency, PaymentProvider, PaymentStatus


class Payment(TimestampMixin, Base):
    """One payment attempt for an order. An order may have several (retries)."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    provider: Mapped[PaymentProvider] = mapped_column(str_enum(PaymentProvider))
    # Our unique transaction id sent to ABA PayWay (max 20 chars per PayWay spec)
    tran_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    payment_option: Mapped[str] = mapped_column(String(40), default="")  # abapay_khqr, cards, cash…
    currency: Mapped[Currency] = mapped_column(str_enum(Currency))
    # Amount in the payment currency's smallest unit (USD cents or whole riel)
    amount_minor: Mapped[int] = mapped_column(Integer)
    status: Mapped[PaymentStatus] = mapped_column(str_enum(PaymentStatus), index=True)
    provider_reference: Mapped[str] = mapped_column(String(80), default="")  # e.g. PayWay APV code
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    refunded_minor: Mapped[int] = mapped_column(Integer, default=0)

    # Cash payments only
    cash_received_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    change_given_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    received_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    failure_reason: Mapped[str] = mapped_column(String(255), default="")

    order: Mapped["Order"] = relationship(back_populates="payments")  # noqa: F821
    events: Mapped[list["PaymentEvent"]] = relationship(back_populates="payment", order_by="PaymentEvent.id")


class PaymentEvent(Base):
    """Complete, append-only log of everything that happened with a payment."""

    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True, index=True)
    tran_id: Mapped[str] = mapped_column(String(40), index=True, default="")
    kind: Mapped[str] = mapped_column(String(40))  # CREATE, CALLBACK, CHECK, REFUND, EXPIRE, CASH
    # Request/response bodies with secrets removed
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    payment: Mapped[Payment | None] = relationship(back_populates="events")


class Refund(TimestampMixin, Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[Currency] = mapped_column(str_enum(Currency))
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20))  # PENDING, COMPLETED, FAILED
    provider_reference: Mapped[str] = mapped_column(String(80), default="")
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
