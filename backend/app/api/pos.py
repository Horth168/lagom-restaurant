"""POS: cashier orders (dine-in or takeaway), discounts, KHQR on the counter screen, history."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.orders_admin import order_detail, order_row
from app.core.deps import CurrentStaff, require
from app.db import get_db
from app.models import DiningTable, Order
from app.models.base import utcnow
from app.models.enums import Currency, OrderChannel
from app.services import app_settings
from app.services.audit import audit
from app.services.orders import business_date, create_order
from app.services.payments import PaymentProblem, start_payment
from app.services.pricing import CartLineIn, PricingError, CartIn, price_cart

router = APIRouter(prefix="/api/pos", tags=["pos"])


class PosOrderIn(BaseModel):
    channel: OrderChannel = OrderChannel.POS_TAKEAWAY
    table_id: int | None = None
    items: list[CartLineIn] = Field(min_length=1, max_length=60)
    discount_usd_cents: int = Field(0, ge=0, le=10_000_000)
    discount_percent: int = Field(0, ge=0, le=100)
    discount_reason: str = Field("", max_length=160)
    customer_note: str = Field("", max_length=500)
    idempotency_key: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")

    @model_validator(mode="after")
    def _check(self):
        if self.channel not in (OrderChannel.POS_DINE_IN, OrderChannel.POS_TAKEAWAY):
            raise ValueError("POS orders are dine-in or takeaway")
        if self.channel == OrderChannel.POS_DINE_IN and not self.table_id:
            raise ValueError("Choose a table for dine-in")
        if self.discount_usd_cents and self.discount_percent:
            raise ValueError("Use either an amount or a percentage discount")
        return self


@router.get("/tables")
def pos_tables(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("orders.create"))):
    return [{"id": t.id, "label": t.label, "area": t.area}
            for t in db.scalars(select(DiningTable).where(DiningTable.is_active.is_(True)).order_by(DiningTable.sort_order))]


@router.post("/orders", status_code=201)
def create_pos_order(body: PosOrderIn, request: Request, db: Session = Depends(get_db),
                     staff: CurrentStaff = Depends(require("orders.create"))):
    existing = db.scalar(select(Order).where(Order.idempotency_key == body.idempotency_key))
    if existing:
        return order_detail(db, existing)
    if (body.discount_usd_cents or body.discount_percent) and not staff.can("orders.discount"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You are not allowed to give discounts.")
    if (body.discount_usd_cents or body.discount_percent) and not body.discount_reason.strip():
        raise HTTPException(422, "Please give a reason for the discount.")
    table = None
    if body.channel == OrderChannel.POS_DINE_IN:
        table = db.get(DiningTable, body.table_id)
        if not table or not table.is_active:
            raise HTTPException(422, "Choose an active table.")
    try:
        priced = price_cart(db, CartIn(items=body.items))
    except PricingError as e:
        raise HTTPException(422, {"message": e.message, "line": e.line, "code": e.code})
    discount = body.discount_usd_cents or round(priced.subtotal_usd_cents * body.discount_percent / 100)
    if discount > priced.subtotal_usd_cents:
        raise HTTPException(422, "The discount is larger than the order.")
    order = create_order(
        db, priced, channel=body.channel, table_id=table.id if table else None, table_label=table.label if table else "",
        idempotency_key=body.idempotency_key, customer_note=body.customer_note, created_by_user_id=staff.id,
        discount_usd_cents=discount, discount_reason=body.discount_reason.strip(),
    )
    if discount:
        audit(db, "order.discount", "order", order.id, staff.id,
              {"usd_cents": discount, "reason": body.discount_reason}, request)
    db.commit()
    return order_detail(db, order)


class KhqrIn(BaseModel):
    currency: Currency = Currency.USD


@router.post("/orders/{public_id}/khqr")
def pos_khqr(public_id: str, body: KhqrIn, db: Session = Depends(get_db),
             staff: CurrentStaff = Depends(require("orders.create"))):
    """Show a KHQR on the counter screen; ABA's notice confirms it automatically."""
    order = db.scalar(select(Order).where(Order.public_id == public_id))
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if body.currency.value not in app_settings.get_setting(db, "accepted_payment_currencies"):
        raise HTTPException(422, "This currency is not accepted.")
    try:
        p = start_payment(db, order, "khqr", body.currency)
    except PaymentProblem as e:
        raise HTTPException(e.status_code, e.message)
    return {"qr_string": p.qr_string, "reference": p.tran_id, "currency": p.currency, "amount_minor": p.amount_minor,
            "expires_at": p.expires_at}


@router.get("/history")
def pos_history(db: Session = Depends(get_db), staff: CurrentStaff = Depends(require("orders.view"))):
    """Today's orders (all channels), newest first, for the cashier."""
    today = business_date(db)
    rows = db.scalars(select(Order).where(Order.business_date >= today - timedelta(days=0))
                      .options(selectinload(Order.items), selectinload(Order.payments))
                      .order_by(Order.id.desc()).limit(200)).all()
    return {"date": today, "now": utcnow(), "orders": [order_row(o) for o in rows]}
