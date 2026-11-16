"""Staff payment tools: take cash at the counter, decide unmatched ABA payments."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import CurrentStaff, require
from app.db import get_db
from app.models import BankNotice, Order
from app.models.enums import Currency, OrderStatus, PaymentProvider, PaymentStatus
from app.services import aba_notices, tg_listener
from app.services.audit import audit
from app.services.payments import PaymentProblem, confirm_cash

router = APIRouter(prefix="/api/admin", tags=["payments"])


class CashIn(BaseModel):
    currency: Currency = Currency.USD
    received_minor: int = Field(ge=0, le=100_000_000)  # cents for USD, riel for KHR


class AssignIn(BaseModel):
    order_public_id: str


def _order(db: Session, public_id: str) -> Order:
    order = db.scalar(select(Order).where(Order.public_id == public_id))
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    return order


def _waiting(o: Order) -> dict:
    pending = next((p for p in reversed(o.payments) if p.status in (PaymentStatus.PENDING, PaymentStatus.EXPIRED)), None)
    return {
        "public_id": o.public_id, "number": o.display_number, "table": o.table_label, "status": o.status,
        "total_usd_cents": o.total_usd_cents, "total_khr": o.total_khr, "created_at": o.created_at,
        "expires_at": o.expires_at, "method": pending.payment_option if pending else None,
        "reference": pending.tran_id if pending else None,
        "amount_minor": pending.amount_minor if pending else None,
        "currency": pending.currency if pending else None,
    }


@router.get("/payments/waiting")
def waiting_orders(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("payments.view"))):
    """Orders waiting for payment (cash at the counter or KHQR not yet confirmed)."""
    orders = db.scalars(select(Order).where(Order.status == OrderStatus.PENDING_PAYMENT).order_by(Order.id)).all()
    return [_waiting(o) for o in orders]


@router.post("/orders/{public_id}/cash")
def take_cash(public_id: str, body: CashIn, request: Request, db: Session = Depends(get_db),
              staff: CurrentStaff = Depends(require("payments.cash"))):
    order = _order(db, public_id)
    try:
        p = confirm_cash(db, order, received_minor=body.received_minor, currency=body.currency, user_id=staff.id)
    except PaymentProblem as e:
        raise HTTPException(e.status_code, e.message)
    audit(db, "payment.cash", "order", order.id, staff.id,
          {"currency": body.currency, "received_minor": body.received_minor, "change_minor": p.change_given_minor}, request)
    db.commit()
    return {"status": "PAID", "change_minor": p.change_given_minor, "currency": p.currency}


@router.get("/bank-notices")
def bank_notices(outcome: str | None = Query(None, pattern="^(matched|ambiguous|unmatched|resolved)$"),
                 db: Session = Depends(get_db), _: CurrentStaff = Depends(require("payments.view"))):
    q = select(BankNotice).order_by(BankNotice.id.desc()).limit(200)
    if outcome:
        q = q.where(BankNotice.outcome == outcome)
    return [
        {"id": n.id, "trx_id": n.trx_id, "currency": n.currency, "amount_minor": n.amount_minor, "payer": n.payer,
         "payer_account": n.payer_account, "received_at": n.received_at, "outcome": n.outcome, "payment_id": n.payment_id}
        for n in db.scalars(q)
    ]


@router.post("/bank-notices/{notice_id}/assign")
def assign_notice(notice_id: int, body: AssignIn, request: Request, db: Session = Depends(get_db),
                  staff: CurrentStaff = Depends(require("payments.cash"))):
    """Staff link an ABA payment that LAGOM could not match on its own to the right order."""
    notice = db.get(BankNotice, notice_id)
    if not notice:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bank payment not found.")
    order = _order(db, body.order_public_id)
    payment = next((p for p in reversed(order.payments) if p.provider == PaymentProvider.ABA_KHQR
                    and p.status in (PaymentStatus.PENDING, PaymentStatus.EXPIRED)), None)
    if payment is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That order is not waiting for a KHQR payment.")
    try:
        aba_notices.assign(db, notice, payment, staff.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    audit(db, "payment.bank_notice_assigned", "order", order.id, staff.id, {"trx": notice.trx_id}, request)
    db.commit()
    return {"status": "PAID"}


@router.get("/payments/status")
def payment_setup_status(_: CurrentStaff = Depends(require("payments.view"))):
    """Is KHQR set up, and is the Telegram listener connected? (no secrets)"""
    s = get_settings()
    return {"khqr_configured": s.khqr_enabled, "listener_configured": s.listener_enabled,
            "listener": {k: v for k, v in tg_listener.STATUS.items() if k != "error"} | {"error": tg_listener.STATUS["error"]}}
