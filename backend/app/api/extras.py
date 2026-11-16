"""Cash drawer shifts, table service requests, reviews, timed deals, backup and busiest hours."""
import io
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.orders_public import _own_order
from app.api.public import current_table_session
from app.core.deps import CurrentStaff, require
from app.core.rate_limit import rate_limit
from app.db import Base, get_db
from app.models import (CashShift, Category, Deal, ItemRating, Order, OrderReview, Payment, Product, Refund,
                        ServiceRequest, TableSession, User)
from app.models.base import utcnow
from app.models.enums import Currency, OrderStatus, PaymentStatus
from app.services import app_settings
from app.services import telegram as tg
from app.services.audit import audit
from app.services.notifications import _after_commit, _enabled, _money

router = APIRouter(tags=["extras"])

PAID_STATES = (OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.SERVED)


def _after_commit_publish(db: Session, channel: str, message: dict) -> None:
    from sqlalchemy import event

    from app.services.realtime import hub

    @event.listens_for(db, "after_commit", once=True)
    def _send(_session):
        hub.publish(channel, message)


# =============================================================== B. cash drawer shifts
def _cash_totals(db: Session, start: datetime, end: datetime) -> dict:
    """Cash taken and cash refunded between two moments, per currency."""
    usd = khr = orders = khqr_usd = 0
    approved = (PaymentStatus.APPROVED, PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED)
    for p in db.scalars(select(Payment).where(Payment.approved_at >= start, Payment.approved_at <= end,
                                              Payment.status.in_(approved))):
        if p.payment_option == "cash":
            orders += 1
            if p.currency == Currency.KHR:
                khr += p.amount_minor
            else:
                usd += p.amount_minor
        elif p.payment_option == "khqr" and p.currency == Currency.USD:
            khqr_usd += p.amount_minor
    for r, method in db.execute(select(Refund, Payment.payment_option).join(Payment, Payment.id == Refund.payment_id)
                                .where(Refund.status == "COMPLETED", Refund.updated_at >= start, Refund.updated_at <= end)):
        if method == "cash":
            if r.currency == Currency.KHR:
                khr -= r.amount_minor
            else:
                usd -= r.amount_minor
    return {"cash_usd_cents": usd, "cash_khr": khr, "cash_orders": orders, "khqr_usd_cents": khqr_usd}


def _shift_out(db: Session, s: CashShift) -> dict:
    live = s.closed_at is None
    totals = _cash_totals(db, s.opened_at, s.closed_at or utcnow()) if live else None
    exp_usd = s.expected_usd_cents if not live else s.opening_usd_cents + totals["cash_usd_cents"]
    exp_khr = s.expected_khr if not live else s.opening_khr + totals["cash_khr"]
    names = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(
        [x for x in (s.opened_by_user_id, s.closed_by_user_id) if x])))}
    return {
        "id": s.id, "status": "OPEN" if live else "CLOSED",
        "opened_at": s.opened_at, "opened_by": names.get(s.opened_by_user_id, ""),
        "closed_at": s.closed_at, "closed_by": names.get(s.closed_by_user_id, ""),
        "opening_usd_cents": s.opening_usd_cents, "opening_khr": s.opening_khr,
        "expected_usd_cents": exp_usd, "expected_khr": exp_khr,
        "counted_usd_cents": s.counted_usd_cents, "counted_khr": s.counted_khr,
        "difference_usd_cents": None if live else s.counted_usd_cents - s.expected_usd_cents,
        "difference_khr": None if live else s.counted_khr - s.expected_khr,
        "cash_orders": totals["cash_orders"] if live else s.cash_orders,
        "khqr_usd_cents": totals["khqr_usd_cents"] if live else s.khqr_usd_cents,
        "note": s.note,
    }


def _open_shift(db: Session) -> CashShift | None:
    return db.scalar(select(CashShift).where(CashShift.closed_at.is_(None)).order_by(CashShift.id.desc()))


class ShiftOpenIn(BaseModel):
    opening_usd_cents: int = Field(0, ge=0, le=100_000_000)
    opening_khr: int = Field(0, ge=0, le=10_000_000_000)


class ShiftCloseIn(BaseModel):
    counted_usd_cents: int = Field(ge=0, le=100_000_000)
    counted_khr: int = Field(0, ge=0, le=10_000_000_000)
    note: str = Field("", max_length=500)


@router.get("/api/pos/shift")
def current_shift(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("payments.cash"))):
    s = _open_shift(db)
    return _shift_out(db, s) if s else None


@router.post("/api/pos/shift/open", status_code=201)
def open_shift(body: ShiftOpenIn, request: Request, db: Session = Depends(get_db),
               staff: CurrentStaff = Depends(require("payments.cash"))):
    if _open_shift(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "A shift is already open. Close it first.")
    s = CashShift(opened_by_user_id=staff.id, opening_usd_cents=body.opening_usd_cents, opening_khr=body.opening_khr,
                  opened_at=utcnow())
    db.add(s)
    db.flush()
    audit(db, "shift.opened", "shift", s.id, staff.id, body.model_dump(), request)
    db.commit()
    return _shift_out(db, s)


@router.post("/api/pos/shift/close")
def close_shift(body: ShiftCloseIn, request: Request, db: Session = Depends(get_db),
                staff: CurrentStaff = Depends(require("payments.cash"))):
    s = _open_shift(db)
    if not s:
        raise HTTPException(status.HTTP_409_CONFLICT, "No shift is open.")
    now = utcnow()
    totals = _cash_totals(db, s.opened_at, now)
    s.closed_at, s.closed_by_user_id = now, staff.id
    s.expected_usd_cents = s.opening_usd_cents + totals["cash_usd_cents"]
    s.expected_khr = s.opening_khr + totals["cash_khr"]
    s.counted_usd_cents, s.counted_khr = body.counted_usd_cents, body.counted_khr
    s.cash_orders, s.khqr_usd_cents = totals["cash_orders"], totals["khqr_usd_cents"]
    s.note = body.note.strip()
    out = _shift_out(db, s)
    audit(db, "shift.closed", "shift", s.id, staff.id,
          {"difference_usd_cents": out["difference_usd_cents"], "difference_khr": out["difference_khr"]}, request)
    if _enabled(db, "telegram_notify_shifts"):
        du, dk = out["difference_usd_cents"], out["difference_khr"]
        ok = du == 0 and dk == 0
        diff = "✅ Drawer matches" if ok else (
            f"⚠️ Difference: {'+' if du >= 0 else '-'}{_money(abs(du))}" + (f" · {dk:+,} ៛" if dk else ""))
        _after_commit(db, f"🧮 <b>Shift closed</b> by {tg.esc(staff.user.full_name)}\n"
                          f"Expected cash {_money(out['expected_usd_cents'])}"
                          + (f" + {out['expected_khr']:,} ៛" if out["expected_khr"] else "")
                          + f" · Counted {_money(body.counted_usd_cents)}"
                          + (f" + {body.counted_khr:,} ៛" if body.counted_khr else "")
                          + f"\n{diff}\nCash orders {out['cash_orders']} · ABA KHQR {_money(out['khqr_usd_cents'])}"
                          + (f"\nNote: {tg.esc(s.note)}" if s.note else ""))
    db.commit()
    return out


@router.get("/api/admin/shifts")
def shift_history(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("payments.view"))):
    rows = db.scalars(select(CashShift).order_by(CashShift.id.desc()).limit(60)).all()
    return [_shift_out(db, s) for s in rows]


# =============================================================== F. call waiter / request bill
class ServiceIn(BaseModel):
    kind: str = Field(pattern="^(waiter|bill)$")


def _service_out(r: ServiceRequest) -> dict:
    return {"id": r.id, "kind": r.kind, "table": r.table_label, "created_at": r.created_at, "resolved_at": r.resolved_at}


@router.post("/api/public/service-requests", status_code=201, dependencies=[Depends(rate_limit("service", 10))])
def ask_for_service(body: ServiceIn, db: Session = Depends(get_db),
                    session: TableSession = Depends(current_table_session)):
    if session.table_id is None:
        raise HTTPException(422, "This is only for customers at a table.")
    open_one = db.scalar(select(ServiceRequest).where(ServiceRequest.table_session_id == session.id,
                                                      ServiceRequest.kind == body.kind,
                                                      ServiceRequest.resolved_at.is_(None)))
    if open_one:
        return _service_out(open_one)  # pressing again does not ring again
    r = ServiceRequest(table_session_id=session.id, table_label=session.place_label, kind=body.kind)
    db.add(r)
    db.flush()
    _after_commit_publish(db, "staff", {"type": "service", **{k: str(v) for k, v in _service_out(r).items()
                                                             if k in ("id", "kind", "table")}})
    if _enabled(db, "telegram_notify_service"):
        what = "asks for the bill 🧾" if body.kind == "bill" else "is calling a waiter 🙋"
        _after_commit(db, f"🔔 <b>{tg.esc(r.table_label)}</b> {what}")
    db.commit()
    return _service_out(r)


@router.get("/api/public/service-requests")
def my_service_requests(db: Session = Depends(get_db), session: TableSession = Depends(current_table_session)):
    rows = db.scalars(select(ServiceRequest).where(ServiceRequest.table_session_id == session.id,
                                                   ServiceRequest.resolved_at.is_(None)))
    return [_service_out(r) for r in rows]


@router.get("/api/admin/service-requests")
def open_service_requests(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("orders.view"))):
    rows = db.scalars(select(ServiceRequest).where(ServiceRequest.resolved_at.is_(None)).order_by(ServiceRequest.id))
    return [_service_out(r) for r in rows]


@router.post("/api/admin/service-requests/{request_id}/done")
def service_done(request_id: int, db: Session = Depends(get_db), staff: CurrentStaff = Depends(require("orders.view"))):
    r = db.get(ServiceRequest, request_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if r.resolved_at is None:
        r.resolved_at, r.resolved_by_user_id = utcnow(), staff.id
        _after_commit_publish(db, "staff", {"type": "service_done", "id": str(r.id)})
        _after_commit_publish(db, f"session:{r.table_session_id}", {"type": "service_done", "id": str(r.id)})
        db.commit()
    return _service_out(r)


# =============================================================== H. reviews
class ItemStarsIn(BaseModel):
    item_id: int
    stars: int = Field(ge=1, le=5)


class ReviewIn(BaseModel):
    stars: int = Field(ge=1, le=5)
    comment: str = Field("", max_length=500)
    items: list[ItemStarsIn] = Field(default_factory=list, max_length=40)


@router.post("/api/public/orders/{public_id}/review", status_code=201, dependencies=[Depends(rate_limit("review", 10))])
def review_order(public_id: str, body: ReviewIn, db: Session = Depends(get_db),
                 session: TableSession = Depends(current_table_session)):
    order = _own_order(db, session, public_id)
    if order.status not in (OrderStatus.READY, OrderStatus.SERVED):
        raise HTTPException(status.HTTP_409_CONFLICT, "You can rate your order once it is ready.")
    if db.scalar(select(OrderReview.id).where(OrderReview.order_id == order.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Thank you, this order is already rated.")
    items = {i.id: i for i in order.items}
    db.add(OrderReview(order_id=order.id, stars=body.stars, comment=body.comment.strip()))
    for it in {x.item_id: x for x in body.items}.values():
        item = items.get(it.item_id)
        if item is None:
            raise HTTPException(422, "That dish is not in this order.")
        db.add(ItemRating(order_item_id=item.id, product_id=item.product_id, name_en=item.name_en, stars=it.stars))
    if body.stars <= 2 and _enabled(db, "telegram_notify_reviews"):
        _after_commit(db, f"⭐ <b>{body.stars}/5 for order #{order.display_number}</b> · {tg.esc(order.table_label)}"
                          + (f"\n“{tg.esc(body.comment.strip())}”" if body.comment.strip() else ""))
    db.commit()
    return {"stars": body.stars}


@router.get("/api/public/orders/{public_id}/review")
def my_review(public_id: str, db: Session = Depends(get_db), session: TableSession = Depends(current_table_session)):
    order = _own_order(db, session, public_id)
    r = db.scalar(select(OrderReview).where(OrderReview.order_id == order.id))
    return {"stars": r.stars, "comment": r.comment} if r else None


@router.get("/api/admin/reviews")
def reviews(days: int = 90, db: Session = Depends(get_db), _: CurrentStaff = Depends(require("dashboard.view"))):
    since = utcnow() - timedelta(days=max(1, min(days, 730)))
    dishes = db.execute(select(ItemRating.name_en, func.avg(ItemRating.stars), func.count(ItemRating.id))
                        .where(ItemRating.created_at >= since).group_by(ItemRating.name_en)
                        .order_by(func.avg(ItemRating.stars).desc(), func.count(ItemRating.id).desc())).all()
    overall = db.execute(select(func.avg(OrderReview.stars), func.count(OrderReview.id))
                         .where(OrderReview.created_at >= since)).one()
    recent = db.execute(select(OrderReview, Order).join(Order, Order.id == OrderReview.order_id)
                        .where(OrderReview.created_at >= since).order_by(OrderReview.id.desc()).limit(50)).all()
    return {
        "average": round(float(overall[0]), 2) if overall[0] is not None else None,
        "count": overall[1],
        "dishes": [{"name": n, "average": round(float(a), 2), "count": c} for n, a, c in dishes],
        "recent": [{"order": o.display_number, "table": o.table_label, "stars": r.stars, "comment": r.comment,
                    "created_at": r.created_at} for r, o in recent],
    }


# =============================================================== J. timed deals
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class DealIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    percent: int = Field(ge=1, le=90)
    category_id: int | None = None
    product_id: int | None = None
    weekdays: str = Field("0123456", min_length=1, max_length=7)
    start_time: str = "00:00"
    end_time: str = "23:59"
    is_active: bool = True

    @field_validator("weekdays")
    @classmethod
    def _days(cls, v: str) -> str:
        if not set(v) <= set("0123456"):
            raise ValueError("Days must be 0 (Monday) to 6 (Sunday)")
        return "".join(sorted(set(v)))

    @field_validator("start_time", "end_time")
    @classmethod
    def _time(cls, v: str) -> str:
        if not HHMM.match(v):
            raise ValueError("Use a time like 14:00")
        return v


def _deal_out(d: Deal) -> dict:
    return {"id": d.id, "name": d.name, "percent": d.percent, "category_id": d.category_id, "product_id": d.product_id,
            "weekdays": d.weekdays, "start_time": d.start_time, "end_time": d.end_time, "is_active": d.is_active}


def _check_target(db: Session, body: DealIn) -> None:
    if body.category_id and not db.get(Category, body.category_id):
        raise HTTPException(422, "Choose a category from the list.")
    if body.product_id and not db.get(Product, body.product_id):
        raise HTTPException(422, "Choose a dish from the list.")


@router.get("/api/admin/deals")
def list_deals(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("menu.view"))):
    from app.services.deals import DealBook

    live = {d.id for d in DealBook(db).deals}
    return [_deal_out(d) | {"running_now": d.id in live} for d in db.scalars(select(Deal).order_by(Deal.id))]


@router.post("/api/admin/deals", status_code=201)
def create_deal(body: DealIn, request: Request, db: Session = Depends(get_db),
                staff: CurrentStaff = Depends(require("menu.edit"))):
    _check_target(db, body)
    d = Deal(**body.model_dump())
    db.add(d)
    db.flush()
    audit(db, "deal.created", "deal", d.id, staff.id, body.model_dump(), request)
    db.commit()
    return _deal_out(d)


@router.put("/api/admin/deals/{deal_id}")
def update_deal(deal_id: int, body: DealIn, request: Request, db: Session = Depends(get_db),
                staff: CurrentStaff = Depends(require("menu.edit"))):
    d = db.get(Deal, deal_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    _check_target(db, body)
    for k, v in body.model_dump().items():
        setattr(d, k, v)
    audit(db, "deal.changed", "deal", d.id, staff.id, body.model_dump(), request)
    db.commit()
    return _deal_out(d)


@router.delete("/api/admin/deals/{deal_id}", status_code=204)
def delete_deal(deal_id: int, request: Request, db: Session = Depends(get_db),
                staff: CurrentStaff = Depends(require("menu.edit"))):
    d = db.get(Deal, deal_id)
    if d:
        audit(db, "deal.deleted", "deal", d.id, staff.id, _deal_out(d), request)
        db.delete(d)
        db.commit()
    return Response(status_code=204)


# =============================================================== C. full backup (Excel)
# Never written to the backup file: passwords, login/session keys and photo bytes
SKIP_COLUMNS = {("users", "password_hash"), ("table_sessions", "token"), ("stored_photos", "data")}


def _cell_value(v):
    if v is None or isinstance(v, (int, float, bool)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


@router.get("/api/admin/backup.xlsx")
def backup(request: Request, db: Session = Depends(get_db), staff: CurrentStaff = Depends(require("settings.edit"))):
    """Everything in the database as one Excel file (one sheet per table). Owner only."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell

    wb = Workbook(write_only=True)
    for table in Base.metadata.sorted_tables:
        cols = [c for c in table.columns if (table.name, c.name) not in SKIP_COLUMNS]
        ws = wb.create_sheet(table.name[:31])
        ws.append([c.name for c in cols])
        for row in db.execute(select(*cols)):
            cells = []
            for v in row:
                cell = WriteOnlyCell(ws, value=_cell_value(v))
                if isinstance(cell.value, str):
                    cell.data_type = "s"  # text stays text, never a formula
                cells.append(cell)
            ws.append(cells)
    buf = io.BytesIO()
    wb.save(buf)
    audit(db, "backup.downloaded", "database", None, staff.id, request=request)
    db.commit()
    stamp = utcnow().astimezone(ZoneInfo(app_settings.get_setting(db, "timezone"))).strftime("%Y-%m-%d")
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="lagom-backup-{stamp}.xlsx"'})


# =============================================================== L. busiest hours
@router.get("/api/admin/reports/hours")
def busiest_hours(days: int = 28, db: Session = Depends(get_db), _: CurrentStaff = Depends(require("dashboard.view"))):
    """Paid orders by weekday and hour (restaurant time) over the last N days."""
    days = max(7, min(days, 365))
    tz = ZoneInfo(app_settings.get_setting(db, "timezone"))
    since = utcnow() - timedelta(days=days)
    cells: dict[tuple[int, int], list[int]] = {}
    for paid_at, total in db.execute(select(Order.paid_at, Order.total_usd_cents)
                                     .where(Order.paid_at >= since, Order.status.in_(PAID_STATES))):
        local = paid_at.astimezone(tz)
        c = cells.setdefault((local.weekday(), local.hour), [0, 0])
        c[0] += 1
        c[1] += total
    out = [{"weekday": w, "hour": h, "orders": n, "sales_usd_cents": s} for (w, h), (n, s) in sorted(cells.items())]
    busiest = max(out, key=lambda c: c["orders"], default=None)
    return {"days": days, "cells": out, "busiest": busiest,
            "orders": sum(c["orders"] for c in out), "sales_usd_cents": sum(c["sales_usd_cents"] for c in out)}

