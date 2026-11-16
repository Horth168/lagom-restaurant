"""Admin: order list, order details (also used for receipts), cancellations, refunds, dashboard."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import CurrentStaff, require
from app.db import get_db
from app.models import Order, Payment, Refund, User
from app.models.base import utcnow
from app.models.enums import OrderChannel, OrderStatus, PaymentStatus
from app.services import app_settings
from app.services.audit import audit
from app.services.kitchen import notify_after_commit
from app.services.orders import cancel_order
from app.services.reports import PRESETS, dashboard, resolve_period

router = APIRouter(prefix="/api/admin", tags=["orders admin"])


def order_row(o: Order) -> dict:
    paid = next((p for p in o.payments if p.status in (PaymentStatus.APPROVED, PaymentStatus.REFUNDED,
                                                      PaymentStatus.PARTIALLY_REFUNDED)), None)
    return {
        "public_id": o.public_id, "number": o.display_number, "business_date": o.business_date,
        "status": o.status, "channel": o.channel, "table": o.table_label,
        "total_usd_cents": o.total_usd_cents, "total_khr": o.total_khr,
        "items_count": sum(i.quantity for i in o.items), "created_at": o.created_at, "paid_at": o.paid_at,
        "payment_method": paid.payment_option if paid else None,
    }


def order_detail(db: Session, o: Order) -> dict:
    users = {u.id: u.full_name for u in db.scalars(select(User))}
    return {
        **order_row(o),
        "subtotal_usd_cents": o.subtotal_usd_cents, "discount_usd_cents": o.discount_usd_cents,
        "discount_reason": o.discount_reason, "khr_per_usd": str(o.khr_per_usd),
        "customer_note": o.customer_note, "language": o.language,
        "accepted_at": o.accepted_at, "ready_at": o.ready_at, "served_at": o.served_at,
        "cancelled_at": o.cancelled_at, "cancel_reason": o.cancel_reason,
        "cancelled_by": users.get(o.cancelled_by_user_id), "created_by": users.get(o.created_by_user_id),
        "items": [
            {"id": i.id, "name": i.name_en, "name_km": i.name_km, "name_zh": i.name_zh, "quantity": i.quantity,
             "options": [x["name_en"] for x in i.options], "special_instructions": i.special_instructions,
             "unit_price_usd_cents": i.unit_price_usd_cents, "line_total_usd_cents": i.line_total_usd_cents,
             "station": i.station, "status": i.status}
            for i in o.items
        ],
        "payments": [
            {"id": p.id, "method": p.payment_option, "provider": p.provider, "status": p.status,
             "currency": p.currency, "amount_minor": p.amount_minor, "reference": p.tran_id,
             "bank_reference": p.provider_reference, "cash_received_minor": p.cash_received_minor,
             "change_given_minor": p.change_given_minor, "received_by": users.get(p.received_by_user_id),
             "created_at": p.created_at, "approved_at": p.approved_at, "refunded_minor": p.refunded_minor,
             "refunds": [{"id": r.id, "amount_minor": r.amount_minor, "status": r.status, "reason": r.reason,
                          "reference": r.provider_reference, "created_at": r.created_at}
                         for r in db.scalars(select(Refund).where(Refund.payment_id == p.id))],
             "events": [{"kind": e.kind, "note": e.note, "verified": e.verified, "at": e.created_at} for e in p.events]}
            for p in o.payments
        ],
    }


def _get(db: Session, public_id: str) -> Order:
    o = db.scalar(select(Order).where(Order.public_id == public_id)
                  .options(selectinload(Order.items), selectinload(Order.payments)))
    if not o:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    return o


@router.get("/orders")
def list_orders(
    status_: OrderStatus | None = Query(None, alias="status"),
    channel: OrderChannel | None = None,
    start: date | None = None,
    end: date | None = None,
    q: str | None = Query(None, max_length=60),
    page: int = Query(1, ge=1, le=1000),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: CurrentStaff = Depends(require("orders.view")),
):
    stmt = select(Order)
    if status_:
        stmt = stmt.where(Order.status == status_)
    if channel:
        stmt = stmt.where(Order.channel == channel)
    if start:
        stmt = stmt.where(Order.business_date >= start)
    if end:
        stmt = stmt.where(Order.business_date <= end)
    if q:
        term = q.strip().lstrip("#")
        conds = [Order.table_label.ilike(f"%{term}%"), Order.public_id == term]
        if term.isdigit():
            conds.append(Order.number == int(term))
        # search by payment reference (our KHQR reference or the ABA transaction ID)
        pay_ids = select(Payment.order_id).where(or_(Payment.tran_id == term, Payment.provider_reference == term))
        conds.append(Order.id.in_(pay_ids))
        stmt = stmt.where(or_(*conds))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.options(selectinload(Order.items), selectinload(Order.payments))
                      .order_by(Order.id.desc()).offset((page - 1) * per_page).limit(per_page)).all()
    return {"total": total, "page": page, "per_page": per_page, "orders": [order_row(o) for o in rows]}


@router.get("/orders/{public_id}")
def get_order(public_id: str, db: Session = Depends(get_db), _: CurrentStaff = Depends(require("orders.view"))):
    o = _get(db, public_id)
    return {**order_detail(db, o), "restaurant": app_settings.get_setting(db, "restaurant_name"),
            "receipt_footer": app_settings.get_setting(db, "receipt_footer")}


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


@router.post("/orders/{public_id}/cancel")
def cancel(public_id: str, body: CancelIn, request: Request, db: Session = Depends(get_db),
           staff: CurrentStaff = Depends(require("orders.cancel"))):
    o = _get(db, public_id)
    paid = any(p.status == PaymentStatus.APPROVED for p in o.payments)
    if paid and not staff.can("payments.refund"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This order is paid. Only a manager who can refund may cancel it.")
    try:
        refunds = cancel_order(db, o, reason=body.reason.strip(), user_id=staff.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    audit(db, "order.cancelled", "order", o.id, staff.id,
          {"reason": body.reason, "refunds": [r.amount_minor for r in refunds]}, request)
    notify_after_commit(db, o)
    db.commit()
    return order_detail(db, o)


class RefundDoneIn(BaseModel):
    reference: str = Field("", max_length=80)  # e.g. the ABA refund transaction ID, or "cash"


@router.post("/refunds/{refund_id}/complete")
def complete_refund(refund_id: int, body: RefundDoneIn, request: Request, db: Session = Depends(get_db),
                    staff: CurrentStaff = Depends(require("payments.refund"))):
    """Staff gave the money back (ABA Mobile transfer or cash). Recorded here for the books."""
    r = db.get(Refund, refund_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Refund not found.")
    if r.status != "PENDING":
        raise HTTPException(status.HTTP_409_CONFLICT, "This refund is already recorded.")
    p = db.get(Payment, r.payment_id)
    r.status = "COMPLETED"
    r.provider_reference = body.reference.strip()
    p.refunded_minor += r.amount_minor
    p.status = PaymentStatus.REFUNDED if p.refunded_minor >= p.amount_minor else PaymentStatus.PARTIALLY_REFUNDED
    audit(db, "payment.refunded", "payment", p.id, staff.id, {"amount_minor": r.amount_minor, "currency": r.currency,
                                                             "reference": r.provider_reference}, request)
    db.commit()
    return {"status": r.status}


@router.get("/refunds")
def pending_refunds(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("payments.view"))):
    rows = db.scalars(select(Refund).where(Refund.status == "PENDING").order_by(Refund.id)).all()
    out = []
    for r in rows:
        p = db.get(Payment, r.payment_id)
        out.append({"id": r.id, "amount_minor": r.amount_minor, "currency": r.currency, "reason": r.reason,
                    "method": p.payment_option, "bank_reference": p.provider_reference,
                    "order": p.order.public_id, "number": p.order.display_number, "created_at": r.created_at})
    return out


@router.get("/dashboard")
def get_dashboard(
    period: str = Query("today", pattern="^(" + "|".join(PRESETS) + ")$"),
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    _: CurrentStaff = Depends(require("dashboard.view")),
):
    try:
        s, e = resolve_period(db, period, start, end)
    except ValueError as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(err))
    data = dashboard(db, s, e)
    data["server_time"] = utcnow()
    return data
