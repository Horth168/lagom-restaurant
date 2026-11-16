"""How a table order gets paid.

KHQR  -> LAGOM makes a one-order KHQR (exact amount + order reference) from the
         shop's ABA QR. ABA's Telegram notice confirms it (aba_notices.py).
CASH  -> the customer pays at the counter; a cashier confirms it in the POS.

Nothing reaches the kitchen until one of those confirmations happens.
"""
import logging
import secrets
import string
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Order, Payment
from app.models.base import utcnow
from app.models.enums import Currency, OrderStatus, PaymentProvider, PaymentStatus
from app.services import khqr
from app.services.orders import amount_due_minor, expire_order, log_event, mark_order_paid, run_paid_listeners

log = logging.getLogger("lagom.payments")

METHODS = {"khqr": PaymentProvider.ABA_KHQR, "cash": PaymentProvider.CASH}


class PaymentProblem(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def new_reference(order: Order) -> str:
    """e.g. LG261116-001-7Q: date, order number, 2 random characters (fits KHQR's 25-char bill number)."""
    tail = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(2))
    return f"LG{order.business_date:%y%m%d}-{order.number:03d}-{tail}"


def start_payment(db: Session, order: Order, method: str, currency: Currency) -> Payment:
    s = get_settings()
    if method not in METHODS:
        raise PaymentProblem("Unknown payment method.", 422)
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise PaymentProblem("This order is no longer waiting for payment.", 409)
    now = utcnow()
    if order.expires_at and order.expires_at <= now:
        expire_order(db, order)
        db.commit()
        raise PaymentProblem("The payment time for this order has ended. Please order again.", 410)
    provider = METHODS[method]
    if provider == PaymentProvider.ABA_KHQR and not s.khqr_enabled:
        raise PaymentProblem("KHQR payment is not available right now. Please pay at the counter.", 503)

    # Same choice again (page reload): keep the same QR / cash request
    for p in order.payments:
        if p.status == PaymentStatus.PENDING and p.provider == provider and p.currency == currency:
            return p

    # A different choice: the older request is cancelled. (If an old QR is paid anyway, ABA's notice
    # will not match automatically and staff are told on Telegram, so money is never lost silently.)
    for p in order.payments:
        if p.status == PaymentStatus.PENDING:
            p.status = PaymentStatus.CANCELLED
            log_event(db, p, "CANCEL", note=f"Customer switched to {method}")

    if provider == PaymentProvider.CASH:
        # Give the customer time to walk to the counter
        order.expires_at = max(order.expires_at or now, now + timedelta(minutes=s.cash_lifetime_minutes))
    minutes_left = max(3, int(((order.expires_at or now) - now).total_seconds() // 60))
    payment = Payment(
        order_id=order.id, provider=provider, tran_id=new_reference(order), payment_option=method,
        currency=currency, amount_minor=amount_due_minor(order, currency), status=PaymentStatus.PENDING,
        expires_at=order.expires_at,
    )
    if provider == PaymentProvider.ABA_KHQR:
        try:
            payment.qr_string = khqr.build(s.khqr_template, amount_minor=payment.amount_minor, currency=currency.value,
                                           reference=payment.tran_id, store_label=s.khqr_store_label,
                                           expiry_minutes=minutes_left)
        except khqr.KhqrError as e:
            log.error("KHQR template problem: %s", e)
            raise PaymentProblem("KHQR payment is not available right now. Please pay at the counter.", 503)
    db.add(payment)
    db.flush()
    log_event(db, payment, "CREATE", {"method": method, "currency": currency.value, "amount_minor": payment.amount_minor})
    db.commit()
    return payment


def confirm_cash(db: Session, order: Order, *, received_minor: int, currency: Currency, user_id: int) -> Payment:
    """A cashier took the money at the counter."""
    if order.status not in (OrderStatus.PENDING_PAYMENT, OrderStatus.EXPIRED):
        raise PaymentProblem("This order is not waiting for payment.", 409)
    due = amount_due_minor(order, currency)
    if received_minor < due:
        raise PaymentProblem("The cash received is less than the amount due.", 422)
    payment = next((p for p in order.payments if p.provider == PaymentProvider.CASH and p.status == PaymentStatus.PENDING
                    and p.currency == currency), None)
    for p in order.payments:
        if p.status == PaymentStatus.PENDING and p is not payment:
            p.status = PaymentStatus.CANCELLED
    if payment is None:
        payment = Payment(order_id=order.id, provider=PaymentProvider.CASH, tran_id=new_reference(order),
                          payment_option="cash", currency=currency, amount_minor=due, status=PaymentStatus.PENDING)
        db.add(payment)
        db.flush()
    payment.amount_minor = due
    payment.cash_received_minor = received_minor
    payment.change_given_minor = received_minor - due
    payment.received_by_user_id = user_id
    payment.status = PaymentStatus.APPROVED
    payment.approved_at = utcnow()
    log_event(db, payment, "CASH", {"received_minor": received_minor, "change_minor": received_minor - due},
              verified=True, note=f"Cash taken by staff #{user_id}")
    if not mark_order_paid(db, order, payment):
        raise PaymentProblem("This order was already paid.", 409)
    run_paid_listeners(db, order)
    db.commit()
    return payment


def expire_due_orders(db: Session) -> int:
    """Unpaid orders whose time ran out become EXPIRED (a late KHQR payment can still revive them)."""
    now = utcnow()
    due = db.scalars(
        select(Order).where(Order.status == OrderStatus.PENDING_PAYMENT, Order.expires_at <= now).limit(200)
    ).all()
    from app.services import notifications

    for order in due:
        chose_khqr = any(p.payment_option == "khqr" and p.status == PaymentStatus.PENDING for p in order.payments)
        expire_order(db, order)
        if chose_khqr:
            notifications.khqr_not_paid(db, order)
    db.commit()
    return len(due)
