"""Customer checkout, payment and order status (QR table ordering)."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.public import current_table_session
from app.config import get_settings
from app.core.rate_limit import rate_limit
from app.db import get_db
from app.models import Order, Payment, TableSession
from app.models.base import utcnow
from app.models.enums import Currency, OrderChannel, OrderStatus, PaymentStatus
from app.services import app_settings
from app.services.orders import create_order, expire_order
from app.services.payments import PaymentProblem, handle_callback, start_qr_payment, verify_payment
from app.services.payway import QR_OPTIONS, USD_ONLY_OPTIONS, get_payway
from app.services.pricing import CartLineIn, PricingError, price_cart, CartIn

router = APIRouter(tags=["customer orders"])

STEPS = ["PAID", "PREPARING", "READY", "SERVED"]


class CheckoutIn(BaseModel):
    items: list[CartLineIn] = Field(min_length=1, max_length=40)
    customer_note: str = Field("", max_length=500)
    # A random id made by the phone for this checkout; resubmitting returns the same order
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    language: str = Field("en", pattern="^(en|km|zh)$")


class PayIn(BaseModel):
    payment_option: str = Field(pattern="^(abapay_khqr|wechat|alipay)$")
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
                          "tran_id": approved.tran_id, "currency": approved.currency,
                          "amount_minor": approved.amount_minor, "method": approved.payment_option}
    elif include_payment and pending and order.status == OrderStatus.PENDING_PAYMENT:
        out["payment"] = {"status": "PENDING", "tran_id": pending.tran_id, "currency": pending.currency,
                          "amount_minor": pending.amount_minor, "method": pending.payment_option,
                          "qr_string": pending.qr_string, "deeplink": pending.deeplink,
                          "expires_at": pending.expires_at}
    return out


def _own_order(db: Session, session: TableSession, public_id: str) -> Order:
    order = db.scalar(select(Order).where(Order.public_id == public_id))
    # Another phone's order looks exactly like a missing one
    if not order or order.table_session_id != session.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    return order


@router.get("/api/public/payment-options")
def payment_options(db: Session = Depends(get_db)):
    currencies = app_settings.get_setting(db, "accepted_payment_currencies")
    client = get_payway()
    s = get_settings()
    return {
        "online_payment_available": client is not None,
        "test_mode": s.payway_simulator and not s.is_production,
        "sandbox": client is not None and not s.payway_simulator and s.payway_is_sandbox,
        "currencies": currencies,
        "options": [
            {"id": "abapay_khqr", "currencies": ["USD", "KHR"]},
            {"id": "wechat", "currencies": ["USD"]},
            {"id": "alipay", "currencies": ["USD"]},
        ],
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
    order = create_order(db, priced, channel=OrderChannel.QR, session=session, idempotency_key=body.idempotency_key,
                         customer_note=body.customer_note, language=body.language)
    session.last_seen_at = utcnow()
    db.commit()
    return order_out(order)


@router.post("/api/public/orders/{public_id}/pay", dependencies=[Depends(rate_limit("pay", 20))])
def pay(public_id: str, body: PayIn, db: Session = Depends(get_db),
        session: TableSession = Depends(current_table_session)):
    order = _own_order(db, session, public_id)
    client = get_payway()
    if client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Online payment is not available right now. Please pay at the counter.")
    if body.currency.value not in app_settings.get_setting(db, "accepted_payment_currencies"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This currency is not accepted.")
    if body.currency == Currency.KHR and body.payment_option in USD_ONLY_OPTIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "WeChat Pay and Alipay only accept USD.")
    assert body.payment_option in QR_OPTIONS
    try:
        start_qr_payment(db, client, order, body.payment_option, body.currency)
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
    """The phone polls this while paying. If PayWay's callback was missed, this asks PayWay directly."""
    order = _own_order(db, session, public_id)
    if order.status == OrderStatus.PENDING_PAYMENT:
        client = get_payway()
        pending = [p for p in order.payments if p.status == PaymentStatus.PENDING]
        if client:
            for p in pending:
                verify_payment(db, client, p, source="status-poll")
        db.refresh(order)
        if order.status == OrderStatus.PENDING_PAYMENT and order.expires_at and order.expires_at <= utcnow() and not pending:
            expire_order(db, order)
        db.commit()
    return order_out(order)


@router.post("/api/payments/payway/callback", include_in_schema=False)
async def payway_callback(request: Request, db: Session = Depends(get_db)):
    """PayWay's server-to-server notification. Never trusted alone: always confirmed via Check Transaction."""
    try:
        if "application/json" in request.headers.get("content-type", ""):
            payload = await request.json()
        else:
            payload = dict(await request.form())
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    from starlette.concurrency import run_in_threadpool

    await run_in_threadpool(handle_callback, db, get_payway(), payload)
    # Always the same answer: tells an attacker nothing
    return {"received": True}


# ---------------------------------------------------------------- development simulator
class SimulatePayIn(BaseModel):
    tran_id: str


@router.post("/api/dev/payway-simulator/pay", include_in_schema=False)
async def simulate_pay(body: SimulatePayIn, db: Session = Depends(get_db)):
    """DEVELOPMENT ONLY. Pretends the customer paid in ABA Mobile, then PayWay calls our callback."""
    s = get_settings()
    if s.is_production or not s.payway_simulator:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    from starlette.concurrency import run_in_threadpool

    from app.services.payway_simulator import get_simulator

    payment = db.scalar(select(Payment).where(Payment.tran_id == body.tran_id))
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown transaction")
    try:
        get_simulator().pay(body.tran_id)
    except (KeyError, ValueError) as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    # Same path as a real PayWay notification
    outcome = await run_in_threadpool(handle_callback, db, get_payway(), {"tran_id": body.tran_id, "status": "0"})
    return {"outcome": outcome}
