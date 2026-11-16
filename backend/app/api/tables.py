"""Admin: dining tables and their QR codes."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import CurrentStaff, require
from app.db import get_db
from app.models import DiningTable, Order, TableSession
from app.models.base import utcnow
from app.models.enums import OrderStatus
from app.models.tables import new_table_token
from app.services.audit import audit
from app.services.qr import qr_png, table_cards_pdf, table_url

router = APIRouter(prefix="/api/admin/tables", tags=["tables"])

ACTIVE_ORDER_STATUSES = (OrderStatus.PENDING_PAYMENT, OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY)


class TableIn(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    seats: int = Field(4, ge=1, le=50)
    area: str = Field("", max_length=60)
    sort_order: int = 0


class TableUpdate(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=40)
    seats: int | None = Field(None, ge=1, le=50)
    area: str | None = Field(None, max_length=60)
    sort_order: int | None = None
    is_active: bool | None = None


def _out(db: Session, t: DiningTable) -> dict:
    active_orders = db.scalar(
        select(func.count()).select_from(Order).where(Order.table_id == t.id, Order.status.in_(ACTIVE_ORDER_STATUSES))
    )
    recent_sessions = db.scalar(
        select(func.count()).select_from(TableSession).where(
            TableSession.table_id == t.id, TableSession.last_seen_at > utcnow() - timedelta(hours=3)
        )
    )
    return {
        "id": t.id, "label": t.label, "seats": t.seats, "area": t.area, "sort_order": t.sort_order,
        "is_active": t.is_active, "qr_url": table_url(t),
        "active_orders": active_orders, "recent_sessions": recent_sessions,
    }


def _get(db: Session, table_id: int) -> DiningTable:
    t = db.get(DiningTable, table_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table not found.")
    return t


@router.get("")
def list_tables(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("tables.manage"))):
    tables = db.scalars(select(DiningTable).order_by(DiningTable.sort_order, DiningTable.label)).all()
    return [_out(db, t) for t in tables]


@router.post("", status_code=201)
def create_table(body: TableIn, request: Request, db: Session = Depends(get_db),
                 staff: CurrentStaff = Depends(require("tables.manage"))):
    t = DiningTable(**body.model_dump())
    db.add(t)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A table with this name already exists.")
    audit(db, "table.created", "table", t.id, staff.id, {"label": t.label}, request)
    db.commit()
    return _out(db, t)


@router.patch("/{table_id}")
def update_table(table_id: int, body: TableUpdate, request: Request, db: Session = Depends(get_db),
                 staff: CurrentStaff = Depends(require("tables.manage"))):
    t = _get(db, table_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(t, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A table with this name already exists.")
    audit(db, "table.updated", "table", t.id, staff.id, {k: str(v) for k, v in changes.items()}, request)
    db.commit()
    return _out(db, t)


@router.post("/{table_id}/rotate-qr")
def rotate_qr(table_id: int, request: Request, db: Session = Depends(get_db),
              staff: CurrentStaff = Depends(require("tables.manage"))):
    """Make a new secret QR code. Old printed cards for this table stop working."""
    t = _get(db, table_id)
    t.qr_token = new_table_token()
    # Close open phone sessions so the old link cannot be reused
    for s in db.scalars(select(TableSession).where(TableSession.table_id == t.id, TableSession.closed_at.is_(None))):
        s.closed_at = utcnow()
    audit(db, "table.qr_rotated", "table", t.id, staff.id, request=request)
    db.commit()
    return _out(db, t)


@router.get("/{table_id}/qr.png")
def table_qr_png(table_id: int, download: bool = False, db: Session = Depends(get_db),
                 _: CurrentStaff = Depends(require("tables.manage"))):
    t = _get(db, table_id)
    headers = {"Cache-Control": "no-store"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="lagom-{t.label.replace(" ", "-").lower()}-qr.png"'
    return Response(qr_png(table_url(t)), media_type="image/png", headers=headers)


@router.get("/cards.pdf")
def table_cards(ids: list[int] | None = Query(None), db: Session = Depends(get_db),
                _: CurrentStaff = Depends(require("tables.manage"))):
    """Printable A4 sheet, 4 QR table cards per page. Pass ?ids=1&ids=2 for specific tables."""
    q = select(DiningTable).where(DiningTable.is_active.is_(True)).order_by(DiningTable.sort_order, DiningTable.label)
    if ids:
        q = q.where(DiningTable.id.in_(ids))
    tables = db.scalars(q).all()
    if not tables:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active tables to print.")
    return Response(table_cards_pdf(tables), media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="lagom-table-cards.pdf"', "Cache-Control": "no-store"})
