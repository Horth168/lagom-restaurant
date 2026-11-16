"""Payment flow on top of the PayWay client.

    start_qr_payment  -> creates a Payment row + asks PayWay for a KHQR / WeChat / Alipay QR
    verify_payment    -> asks PayWay (Check Transaction) and applies the verified result
    handle_callback   -> PayWay's notification: logged, then verified with Check Transaction
    expire_due_orders -> background job: final check, close the QR at PayWay, mark EXPIRED
"""
import logging
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Order, Payment
from app.models.base import utcnow
from app.models.enums import Currency, OrderStatus, PaymentProvider, PaymentStatus
from app.services.orders import amount_due_minor, apply_verified_payment, expire_order, log_event
from app.services.payway import PayWayClient, PayWayError, minor_units

log = logging.getLogger("lagom.payments")

MIN_RECHECK_SECONDS = 4  # don't ask PayWay about the same payment more often than this


class PaymentProblem(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def new_tran_id() -> str:
    # 20 characters max (PayWay rule). Digits only, date first for easy reading in the PayWay portal.
    return utcnow().strftime("%y%m%d%H%M") + f"{secrets.randbelow(10**8):08d}"


def _items_for_payway(order: Order) -> list[dict]:
    return [{"name": i.name_en[:50], "quantity": i.quantity, "price": round(i.unit_price_usd_cents / 100, 2)}
            for i in order.items[:50]]


def start_qr_payment(db: Session, client: PayWayClient, order: Order, payment_option: str,
                     currency: Currency) -> Payment:
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise PaymentProblem("This order is no longer waiting for payment.", 409)
    now = utcnow()
    if order.expires_at and order.expires_at <= now:
        expire_order(db, order)
        db.commit()
        raise PaymentProblem("The payment time for this order has ended. Please order again.", 410)

    # Reuse the current QR if the customer just reloads the page (same option and currency)
    for p in order.payments:
        if (p.status == PaymentStatus.PENDING and p.payment_option == payment_option and p.currency == currency
                and p.expires_at and p.expires_at > now + timedelta(seconds=30)):
            return p

    # A different option was chosen: close the older QR codes so they can never be paid too
    for p in order.payments:
        if p.status == PaymentStatus.PENDING and p.provider == PaymentProvider.ABA_PAYWAY:
            try:
                # last check first: if it was paid meanwhile, keep it
                if verify_payment(db, client, p, source="switch", force=True) in ("paid", "already_paid"):
                    raise PaymentProblem("This order has already been paid.", 409)
                log_event(db, p, "CLOSE", client.close_transaction(p.tran_id), note="Customer switched payment method")
                p.status = PaymentStatus.CANCELLED
            except PayWayError as e:
                log_event(db, p, "CLOSE", e.payload, note=f"Close failed: {e}")
                raise PaymentProblem("We couldn't switch the payment method. Please try again.", 502)

    remaining_minutes = max(3, int((order.expires_at - now).total_seconds() // 60)) if order.expires_at else 15
    payment = Payment(
        order_id=order.id, provider=PaymentProvider.ABA_PAYWAY, tran_id=new_tran_id(), payment_option=payment_option,
        currency=currency, amount_minor=amount_due_minor(order, currency), status=PaymentStatus.PENDING,
        expires_at=now + timedelta(minutes=remaining_minutes),
    )
    db.add(payment)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise PaymentProblem("Please try again.", 409)

    callback = f"{get_settings().backend_url.rstrip('/')}/api/payments/payway/callback"
    try:
        qr, sent = client.generate_qr(
            tran_id=payment.tran_id, amount_minor=payment.amount_minor, currency=currency.value,
            payment_option=payment_option, items=_items_for_payway(order), callback_url=callback,
            lifetime_minutes=remaining_minutes,
        )
    except PayWayError as e:
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = f"{e} (code {e.code})"[:255]
        log_event(db, payment, "CREATE", e.payload, verified=False, note=str(e))
        db.commit()
        log.warning("PayWay QR failed for %s: %s %s", payment.tran_id, e.code, e)
        raise PaymentProblem("Payment could not be started. Please try again or ask our staff.", 502)

    log_event(db, payment, "CREATE", {"request": sent, "response": {k: v for k, v in qr.raw.items() if k != "qrImage"}})
    # The QR content is what the customer scans; storing it lets a reload show the same QR
    payment.qr_string = qr.qr_string
    payment.deeplink = qr.abapay_deeplink[:1000]
    db.commit()
    return payment


def verify_payment(db: Session, client: PayWayClient, payment: Payment, *, source: str, force: bool = False) -> str:
    """Ask PayWay for the real status of a payment and apply it. Safe to call repeatedly."""
    if payment.status not in (PaymentStatus.PENDING, PaymentStatus.EXPIRED):
        return "already_paid" if payment.status == PaymentStatus.APPROVED else "final"
    last_check = next((e.created_at for e in reversed(payment.events) if e.kind == "CHECK"), None)
    if not force and last_check and (utcnow() - last_check).total_seconds() < MIN_RECHECK_SECONDS:
        return "pending"
    try:
        result = client.check_transaction(payment.tran_id)
    except PayWayError as e:
        log_event(db, payment, "CHECK", e.payload, note=f"Check failed: {e} (code {e.code})")
        return "pending"
    log_event(db, payment, "CHECK", result.raw, note=f"{source}: {result.status}")

    if result.status in ("APPROVED", "PRE-AUTH"):
        # PayWay amounts are in the transaction's original currency (the one we requested).
        # The payer may have paid from an account in another currency; that is still a valid payment.
        paid_minor = (minor_units(result.total_amount, payment.currency.value)
                      if result.total_amount is not None else None)
        return apply_verified_payment(db, payment, approved=True, paid_minor=paid_minor,
                                      paid_currency=payment.currency.value,
                                      provider_reference=result.apv, source=source)
    if result.status == "DECLINED":
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "Declined"
        return "failed"
    if result.status == "CANCELLED":
        payment.status = PaymentStatus.CANCELLED
        return "failed"
    return "pending"


def handle_callback(db: Session, client: PayWayClient | None, payload: dict) -> str:
    tran_id = str(payload.get("tran_id") or "")[:40]
    payment = db.scalar(select(Payment).where(Payment.tran_id == tran_id)) if tran_id else None
    # Log everything PayWay sent (minus personal details), even for unknown transactions
    safe = {k: v for k, v in payload.items() if k not in ("payer_account", "email", "phone", "first_name", "last_name")}
    log_event(db, payment, "CALLBACK", safe, tran_id=tran_id, note="unverified notification")
    if not payment or client is None:
        db.commit()
        return "ignored"
    outcome = verify_payment(db, client, payment, source="callback", force=True)
    db.commit()
    return outcome


def expire_due_orders(db: Session, client: PayWayClient | None) -> int:
    """Expire unpaid orders whose time ran out. A last check catches last-second payments."""
    now = utcnow()
    due = db.scalars(
        select(Order).where(Order.status == OrderStatus.PENDING_PAYMENT, Order.expires_at <= now).limit(100)
    ).all()
    count = 0
    for order in due:
        paid = False
        for p in order.payments:
            if p.status == PaymentStatus.PENDING and p.provider == PaymentProvider.ABA_PAYWAY and client:
                if verify_payment(db, client, p, source="expiry", force=True) in ("paid", "already_paid"):
                    paid = True
                    break
                try:
                    log_event(db, p, "CLOSE", client.close_transaction(p.tran_id), note="Order expired")
                except PayWayError as e:
                    log_event(db, p, "CLOSE", e.payload, note=f"Close failed: {e}")
        if not paid:
            expire_order(db, order)
            count += 1
        db.commit()
    return count
