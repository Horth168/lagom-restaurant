"""Order lifecycle: create (prices locked), confirm payment, expire, cancel."""
import logging
import secrets
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import DailyCounter, Order, OrderItem, Payment, PaymentEvent, TableSession
from app.models.base import utcnow
from app.models.enums import Currency, ItemStatus, OrderChannel, OrderStatus, PaymentStatus
from app.services import app_settings
from app.services.app_settings import usd_cents_to_khr
from app.services.pricing import PricedCart

log = logging.getLogger("lagom.orders")

# Called after an order becomes PAID (kitchen screens, notifications, inventory hook in later milestones)
paid_listeners: list = []


def business_date(db: Session, when: datetime | None = None) -> date:
    tz = ZoneInfo(app_settings.get_setting(db, "timezone"))
    return (when or utcnow()).astimezone(tz).date()


def next_order_number(db: Session, day: date) -> int:
    """Short daily number (001, 002…). Safe with concurrent checkouts."""
    for _ in range(5):
        row = db.execute(
            select(DailyCounter).where(DailyCounter.day == day).with_for_update()
        ).scalar_one_or_none()
        if row is None:
            try:
                with db.begin_nested():
                    db.add(DailyCounter(day=day, last_number=1))
                return 1
            except IntegrityError:
                continue  # someone else created today's counter first; retry
        row.last_number += 1
        db.flush()
        return row.last_number
    raise RuntimeError("Could not allocate an order number")


def create_order(
    db: Session,
    priced: PricedCart,
    *,
    channel: OrderChannel,
    session: TableSession | None = None,
    table_id: int | None = None,
    table_label: str = "",
    idempotency_key: str | None = None,
    customer_note: str = "",
    language: str = "en",
    created_by_user_id: int | None = None,
    discount_usd_cents: int = 0,
    discount_reason: str = "",
    payment_currency: Currency = Currency.USD,
    status: OrderStatus = OrderStatus.PENDING_PAYMENT,
) -> Order:
    if idempotency_key:
        existing = db.scalar(select(Order).where(Order.idempotency_key == idempotency_key))
        if existing:
            return existing

    s = get_settings()
    now = utcnow()
    day = business_date(db, now)
    discount = max(0, min(discount_usd_cents, priced.subtotal_usd_cents))
    total = priced.subtotal_usd_cents - discount
    rate = priced.khr_per_usd
    order = Order(
        business_date=day,
        number=next_order_number(db, day),
        public_id=secrets.token_urlsafe(12),
        channel=channel,
        status=status,
        table_id=session.table_id if session else table_id,
        table_label=session.table.label if session else table_label,
        table_session_id=session.id if session else None,
        created_by_user_id=created_by_user_id,
        idempotency_key=idempotency_key,
        subtotal_usd_cents=priced.subtotal_usd_cents,
        discount_usd_cents=discount,
        discount_reason=discount_reason,
        total_usd_cents=total,
        khr_per_usd=rate,
        total_khr=usd_cents_to_khr(total, rate),
        payment_currency=payment_currency,
        customer_note=customer_note.strip()[:500],
        language=language,
        estimated_ready_minutes=priced.estimated_minutes,
        expires_at=now + timedelta(minutes=s.payment_lifetime_minutes) if status == OrderStatus.PENDING_PAYMENT else None,
    )
    for line in priced.lines:
        p = line.product
        order.items.append(OrderItem(
            product_id=p.id, name_en=p.name_en, name_km=p.name_km, name_zh=p.name_zh,
            options=line.option_snapshot, special_instructions=line.special_instructions,
            unit_price_usd_cents=line.unit_price_usd_cents, quantity=line.quantity,
            line_total_usd_cents=line.line_total_usd_cents, station=line.station, prep_minutes=line.prep_minutes,
        ))
    db.add(order)
    try:
        db.flush()
    except IntegrityError:
        # Same idempotency key submitted twice at the same moment: return the first order
        db.rollback()
        if idempotency_key:
            existing = db.scalar(select(Order).where(Order.idempotency_key == idempotency_key))
            if existing:
                return existing
        raise
    return order


def amount_due_minor(order: Order, currency: Currency) -> int:
    return order.total_khr if currency == Currency.KHR else order.total_usd_cents


def log_event(db: Session, payment: Payment | None, kind: str, payload: dict | None = None,
              verified: bool | None = None, note: str = "", tran_id: str = "") -> None:
    db.add(PaymentEvent(payment_id=payment.id if payment else None, tran_id=tran_id or (payment.tran_id if payment else ""),
                        kind=kind, payload=payload or {}, verified=verified, note=note[:2000]))


def mark_order_paid(db: Session, order: Order, payment: Payment) -> bool:
    """Move an order to PAID exactly once. Returns True if this call did it.

    Uses a conditional UPDATE so two simultaneous confirmations (callback + phone
    polling) can never both "win".
    """
    now = utcnow()
    res = db.execute(
        update(Order)
        .where(Order.id == order.id, Order.status.in_([OrderStatus.PENDING_PAYMENT, OrderStatus.EXPIRED]))
        .values(status=OrderStatus.PAID, paid_at=now, expires_at=None, payment_currency=payment.currency)
        .execution_options(synchronize_session=False)
    )
    if res.rowcount != 1:
        return False
    db.refresh(order)
    for item in order.items:
        item.status = ItemStatus.QUEUED
    return True


def apply_verified_payment(db: Session, payment: Payment, *, approved: bool, paid_minor: int | None,
                           paid_currency: str, provider_reference: str, source: str) -> str:
    """Apply a result that came from PayWay's Check Transaction API (never from the phone).

    Returns one of: "paid", "already_paid", "duplicate", "mismatch", "pending".
    """
    order = payment.order
    if not approved:
        return "pending"

    expected = payment.amount_minor
    if paid_minor is None or paid_minor != expected or paid_currency != payment.currency.value:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = f"Amount mismatch: expected {expected} {payment.currency}, got {paid_minor} {paid_currency}"
        log_event(db, payment, "VERIFY", verified=False, note=payment.failure_reason)
        log.error("Payment %s amount mismatch", payment.tran_id)
        return "mismatch"

    if payment.status == PaymentStatus.APPROVED:
        return "already_paid"
    payment.status = PaymentStatus.APPROVED
    payment.approved_at = utcnow()
    payment.provider_reference = provider_reference[:80]
    log_event(db, payment, "VERIFY", verified=True, note=f"Approved via {source}")

    if mark_order_paid(db, order, payment):
        for fn in paid_listeners:
            try:
                fn(db, order)
            except Exception:  # a notification problem must never undo a payment
                log.exception("paid listener failed")
        return "paid"
    # The order was already paid by another payment → the customer paid twice
    payment.failure_reason = "DUPLICATE_PAYMENT_REFUND_REQUIRED"
    log_event(db, payment, "DUPLICATE", verified=True,
              note="Order was already paid by another transaction. Refund this payment.")
    log.error("Duplicate payment %s for order %s", payment.tran_id, order.id)
    return "duplicate"


def expire_order(db: Session, order: Order) -> None:
    if order.status != OrderStatus.PENDING_PAYMENT:
        return
    order.status = OrderStatus.EXPIRED
    for p in order.payments:
        if p.status == PaymentStatus.PENDING:
            p.status = PaymentStatus.EXPIRED
            log_event(db, p, "EXPIRE", note="Order payment time ran out")
