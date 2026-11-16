"""Customer checkout, payment and order status (QR table ordering)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.public import current_table_session
from app.config import get_settings
from app.core.rate_limit import rate_limit
from app.db import get_db
from app.models import Order, TableSession
from app.models.base import utcnow
from app.models.enums import Currency, OrderChannel, OrderStatus, PaymentStatus
from app.services import app_settings
from app.services.orders import create_order, expire_order
from app.services import aba_notices
from app.services.payments import PaymentProblem, start_payment
from app.services.pricing import CartIn, CartLineIn, PricingError, price_cart

router = APIRouter(tags=["customer orders"])

STEPS = ["PAID", "PREPARING", "READY", "SERVED"]


class CheckoutIn(BaseModel):
    items: list[CartLineIn] = Field(min_length=1, max_length=40)
    customer_note: str = Field("", max_length=500)
    # A random id made by the phone for this checkout; resubmitting returns the same order
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    language: str = Field("en", pattern="^(en|km|zh)$")


class PayIn(BaseModel):
    method: str = Field(pattern="^(khqr|cash)$")
    currency: Currency = Currency.USD


def order_out(order: Order, include_payment: bool = True) -> dict:
    approved = next((p for p in order.payments if p.status == PaymentStatus.APPROVED), None)
    pending = next((p for p in reversed(order.payments) if p.status == PaymentStatus.PENDING), None)
    out = {
        "public_id": order.public_id,
        "number": order.display_number,
        "status": order.status,
        "table": order.table_label,
        "channel": order.channel,
        "created_at": order.created_at,
        "paid_at": order.paid_at,
        "accepted_at": order.accepted_at,
        "ready_at": order.ready_at,
        "served_at": order.served_at,
        "expires_at": order.expires_at,
        "estimated_ready_minutes": order.estimated_ready_minutes,
        "subtotal_usd_cents": order.subtotal_usd_cents,
        "discount_usd_cents": order.discount_usd_cents,
        "total_usd_cents": order.total_usd_cents,
        "total_khr": order.total_khr,
        "khr_per_usd": str(order.khr_per_usd),
        "customer_note": order.customer_note,
        "items": [
            {
                "name": {"en": i.name_en, "km": i.name_km or i.name_en, "zh": i.name_zh or i.name_en},
                "options": [{"en": o["name_en"], "km": o.get("name_km") or o["name_en"], "zh": o.get("name_zh") or o["name_en"]}
                            for o in i.options],
                "special_instructions": i.special_instructions,
                "quantity": i.quantity,
                "line_total_usd_cents": i.line_total_usd_cents,
                "status": i.status,
            }
            for i in order.items
        ],
        "payment": None,
    }
    if approved:
        out["payment"] = {"status": "APPROVED", "reference": approved.provider_reference or approved.tran_id,
                          "currency": approved.currency,
                          "amount_minor": approved.amount_minor, "method": approved.payment_option}
    elif include_payment and pending and order.status == OrderStatus.PENDING_PAYMENT:
        out["payment"] = {"status": "PENDING", "reference": pending.tran_id, "currency": pending.currency,
                          "amount_minor": pending.amount_minor, "method": pending.payment_option,
                          "qr_string": pending.qr_string, "expires_at": pending.expires_at}
    return out


def _own_order(db: Session, session: TableSession, public_id: str) -> Order:
    order = db.scalar(select(Order).where(Order.public_id == public_id))
    # Another phone's order looks exactly like a missing one
    if not order or order.table_session_id != session.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    return order


@router.get("/api/public/payment-options")
def payment_options(db: Session = Depends(get_db)):
    s = get_settings()
    return {
        "khqr_available": s.khqr_enabled,
        "cash_available": True,
        "test_mode": s.khqr_test_mode and not s.is_production,
        "currencies": app_settings.get_setting(db, "accepted_payment_currencies"),
    }


@router.post("/api/public/orders", status_code=201, dependencies=[Depends(rate_limit("checkout", 20))])
def checkout(body: CheckoutIn, db: Session = Depends(get_db), session: TableSession = Depends(current_table_session)):
    """Create the order with prices locked by the server. It is not sent to the kitchen until paid."""
    existing = db.scalar(select(Order).where(Order.idempotency_key == body.idempotency_key))
    if existing:
        if existing.table_session_id != session.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Please try again.")
        return order_out(existing)
    try:
        priced = price_cart(db, CartIn(items=body.items))
    except PricingError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"message": e.message, "line": e.line, "code": e.code})
    channel = OrderChannel.QR if session.table_id else OrderChannel.TELEGRAM  # Telegram Mini App = pickup
    order = create_order(db, priced, channel=channel, session=session, idempotency_key=body.idempotency_key,
                         customer_note=body.customer_note, language=body.language)
    session.last_seen_at = utcnow()
    db.commit()
    return order_out(order)


@router.post("/api/public/orders/{public_id}/pay", dependencies=[Depends(rate_limit("pay", 20))])
def pay(public_id: str, body: PayIn, db: Session = Depends(get_db),
        session: TableSession = Depends(current_table_session)):
    """Choose KHQR (pay now with any Cambodian bank app) or cash at the counter."""
    order = _own_order(db, session, public_id)
    if body.currency.value not in app_settings.get_setting(db, "accepted_payment_currencies"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This currency is not accepted.")
    try:
        start_payment(db, order, body.method, body.currency)
    except PaymentProblem as e:
        raise HTTPException(e.status_code, e.message)
    db.refresh(order)
    return order_out(order)


@router.get("/api/public/orders")
def my_orders(db: Session = Depends(get_db), session: TableSession = Depends(current_table_session)):
    orders = db.scalars(
        select(Order).where(Order.table_session_id == session.id).order_by(Order.id.desc()).limit(30)
    ).all()
    return [order_out(o, include_payment=False) for o in orders]


@router.get("/api/public/orders/{public_id}", dependencies=[Depends(rate_limit("order-status", 120))])
def order_status(public_id: str, db: Session = Depends(get_db), session: TableSession = Depends(current_table_session)):
    """The phone checks this while waiting. Payment is confirmed by ABA's notice or a cashier, never by the phone."""
    order = _own_order(db, session, public_id)
    if order.status == OrderStatus.PENDING_PAYMENT and order.expires_at and order.expires_at <= utcnow():
        expire_order(db, order)
        db.commit()
    return order_out(order)


# ---------------------------------------------------------------- development test mode
class SimulateIn(BaseModel):
    public_id: str


@router.post("/api/dev/khqr/simulate-payment", include_in_schema=False)
def simulate_payment(body: SimulateIn, db: Session = Depends(get_db),
                     session: TableSession = Depends(current_table_session)):
    """DEVELOPMENT ONLY (KHQR_TEST_MODE): pretends ABA posted "$X paid by …" for this order.
    The text goes through the exact same matcher as a real ABA notice."""
    s = get_settings()
    if s.is_production or not s.khqr_test_mode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    order = _own_order(db, session, body.public_id)
    payment = next((p for p in order.payments if p.status == PaymentStatus.PENDING and p.payment_option == "khqr"), None)
    if not payment:
        raise HTTPException(status.HTTP_409_CONFLICT, "No KHQR payment is waiting for this order.")
    outcome = aba_notices.process(db, aba_notices.simulated_text(payment), utcnow())
    return {"outcome": outcome}
