"""Owner: who did what, and when (read-only)."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import CurrentStaff, require
from app.db import get_db
from app.models import AuditLog, User
from app.services import app_settings

router = APIRouter(prefix="/api/admin/audit", tags=["audit"])


@router.get("")
def audit_log(
    action: str | None = Query(None, max_length=60, description="e.g. 'order.' for every order action"),
    user_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
    page: int = Query(1, ge=1, le=10000),
    db: Session = Depends(get_db),
    _: CurrentStaff = Depends(require("audit.view")),
):
    tz = ZoneInfo(app_settings.get_setting(db, "timezone"))  # dates are restaurant dates
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action.startswith(action))
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    if start:
        q = q.where(AuditLog.created_at >= datetime.combine(start, time.min, tz))
    if end:
        q = q.where(AuditLog.created_at < datetime.combine(end + timedelta(days=1), time.min, tz))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(AuditLog.id.desc()).offset((page - 1) * 50).limit(50)).all()
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    return {"total": total, "page": page, "per_page": 50, "entries": [
        {"id": a.id, "action": a.action, "entity": a.entity, "entity_id": a.entity_id, "details": a.details,
         "user": names.get(a.user_id), "ip": a.ip_address, "at": a.created_at} for a in rows]}
