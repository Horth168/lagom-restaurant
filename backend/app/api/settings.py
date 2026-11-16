from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import CurrentStaff, require
from app.db import get_db
from app.services import app_settings as svc
from app.services.audit import audit

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _jsonable(d: dict) -> dict:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in d.items()}


@router.get("/public")
def public_settings(db: Session = Depends(get_db)):
    """Settings the customer app needs (no secrets)."""
    data = svc.all_settings(db)
    return _jsonable({k: data[k] for k in svc.PUBLIC_KEYS})


@router.get("")
def read_settings(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("settings.edit"))):
    s = get_settings()
    return {
        "settings": _jsonable(svc.all_settings(db)),
        # Integration status only – secret values are never sent to the browser
        "integrations": {
            "khqr_configured": s.khqr_enabled,
            "payment_listener_configured": s.listener_enabled,
            "telegram_configured": bool(s.telegram_bot_token and s.telegram_chat_id),
            "r2_configured": bool(s.r2_bucket and s.r2_access_key_id),
            "environment": s.environment,
            "production_problems": s.validate_for_production() if s.is_production else [],
        },
    }


@router.patch("")
def update_settings(
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
    staff: CurrentStaff = Depends(require("settings.edit")),
):
    for key, value in body.items():
        if key not in svc.DEFAULTS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown setting: {key}")
        _, typ = svc.DEFAULTS[key]
        if typ is Decimal:
            try:
                value = Decimal(str(value))
            except InvalidOperation:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key} must be a number")
            if key == "khr_per_usd" and not (Decimal(1000) <= value <= Decimal(10000)):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Exchange rate looks wrong (1000–10000).")
        elif typ is bool and not isinstance(value, bool):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key} must be true or false")
        elif typ is str and not isinstance(value, str):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key} must be text")
        elif typ is list and not isinstance(value, list):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{key} must be a list")
        if key == "display_currency" and value not in ("USD", "KHR"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "display_currency must be USD or KHR")
        if key == "inventory_deduct_on" and value not in ("PAID", "READY"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "inventory_deduct_on must be PAID or READY")
        old = svc.get_setting(db, key)
        svc.set_setting(db, key, value)
        audit(db, "settings.changed", "setting", key, staff.id, {"from": str(old), "to": str(value)}, request)
    db.commit()
    return _jsonable(svc.all_settings(db))
