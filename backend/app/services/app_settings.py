"""Owner-editable business settings (exchange rate, display currency, policies)."""
import json
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import AppSetting

# key -> (default value, type)
DEFAULTS: dict[str, tuple[object, type]] = {
    "restaurant_name": ("LAGOM", str),
    "khr_per_usd": ("4100", Decimal),
    "display_currency": ("USD", str),  # USD or KHR – what customers see first
    "show_secondary_currency": (True, bool),
    "accepted_payment_currencies": (["USD"], list),  # what PayWay charges in
    # When stock is deducted: "PAID" (as soon as paid) or "READY" (when prepared)
    "inventory_deduct_on": ("PAID", str),
    "kds_sound_enabled": (True, bool),
    "receipt_footer": ("Thank you · JUST THE RIGHT AMOUNT.", str),
    "telegram_notify_new_orders": (True, bool),
    "telegram_notify_failed_payments": (True, bool),
    "telegram_notify_cancellations": (True, bool),
    "telegram_notify_low_stock": (True, bool),
    "telegram_daily_summary": (True, bool),
    "daily_summary_time": ("22:00", str),  # restaurant time, HH:MM
    "daily_summary_last_sent": ("", str),  # internal: date of the last summary
    "timezone": ("Asia/Phnom_Penh", str),
    "telegram_notify_shifts": (True, bool),  # cash drawer closed (expected vs counted)
    "telegram_notify_service": (True, bool),  # "Table 05 asks for the bill"
    "telegram_notify_reviews": (True, bool),  # low ratings (1–2 stars)
    "auto_sold_out": (True, bool),  # dishes become "sold out" when an ingredient runs out
    "backup_reminder": (True, bool),  # weekly Telegram reminder to download a backup
    "backup_reminder_last_week": ("", str),  # internal
    # Telegram stamp card: every N eligible items paid in the Mini App earns one free item
    "loyalty_enabled": (False, bool),
    "loyalty_stamps_needed": (9, int),
    "loyalty_category_ids": ([], list),
}

INTERNAL_KEYS = {"daily_summary_last_sent", "backup_reminder_last_week"}  # managed by the system, not editable in Settings
PUBLIC_KEYS = {"restaurant_name", "khr_per_usd", "display_currency", "show_secondary_currency"}


def _decode(raw: str, typ: type):
    if typ is Decimal:
        return Decimal(raw)
    if typ is str:
        return raw
    return json.loads(raw)


def _encode(value, typ: type) -> str:
    if typ in (Decimal, str):
        return str(value)
    return json.dumps(value)


def get_setting(db: Session, key: str):
    default, typ = DEFAULTS[key]
    row = db.get(AppSetting, key)
    if row is None:
        return _decode(_encode(default, typ), typ)
    return _decode(row.value, typ)


def all_settings(db: Session) -> dict:
    return {k: get_setting(db, k) for k in DEFAULTS}


def set_setting(db: Session, key: str, value) -> None:
    if key not in DEFAULTS:
        raise KeyError(key)
    _, typ = DEFAULTS[key]
    row = db.get(AppSetting, key)
    encoded = _encode(value, typ)
    if row is None:
        db.add(AppSetting(key=key, value=encoded))
    else:
        row.value = encoded


def khr_per_usd(db: Session) -> Decimal:
    return get_setting(db, "khr_per_usd")


def usd_cents_to_khr(cents: int, rate: Decimal) -> int:
    """Convert and round to the nearest 100 riel (smallest note in common use)."""
    riel = Decimal(cents) * rate / Decimal(100)
    return int((riel / 100).quantize(Decimal("1"), rounding="ROUND_HALF_UP") * 100)
