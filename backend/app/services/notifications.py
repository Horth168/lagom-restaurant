"""Telegram messages to the owner/staff chat.

Each kind can be switched off in Settings. Messages are sent only after the
change is saved (so a failed save never sends a false alert) and never contain
secrets or full account numbers.
"""
import logging
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import Expense, Ingredient, Order
from app.models.base import utcnow
from app.models.enums import OrderChannel, PaymentStatus
from app.services import app_settings
from app.services import telegram as tg

log = logging.getLogger("lagom.notifications")

CHANNEL = {OrderChannel.QR: "Table QR", OrderChannel.POS_DINE_IN: "POS dine-in",
           OrderChannel.POS_TAKEAWAY: "POS takeaway", OrderChannel.TELEGRAM: "Telegram pickup"}


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _safely(send, *args) -> None:
    """An alert must never break the request that triggered it (the payment is already saved)."""
    try:
        send(*args)
    except Exception:  # noqa: BLE001
        log.exception("Telegram alert could not be sent")


def _after_commit(db: Session, text: str) -> None:
    @event.listens_for(db, "after_commit", once=True)
    def _send(_session):
        _safely(tg.notify, text)


def _enabled(db: Session, key: str) -> bool:
    return bool(app_settings.get_setting(db, key))


# ---------------------------------------------------------------- events
def order_paid(db: Session, order: Order) -> None:
    if not _enabled(db, "telegram_notify_new_orders"):
        return
    paid = next((p for p in order.payments if p.status == PaymentStatus.APPROVED), None)
    how = "Cash" if paid and paid.payment_option == "cash" else "ABA KHQR"
    if paid and paid.provider_reference:
        how += f" · Trx {tg.esc(paid.provider_reference)}"
    items = "\n".join(f"• {i.quantity}× {tg.esc(i.name_en)}" for i in order.items[:12])
    more = f"\n• … {len(order.items) - 12} more" if len(order.items) > 12 else ""
    where = tg.esc(order.table_label or CHANNEL.get(order.channel, ""))
    _after_commit(db, f"🧾 <b>New order #{order.display_number}</b> · {where}\n{items}{more}\n"
                      f"<b>{_money(order.total_usd_cents)}</b> · {how}")


def order_cancelled(db: Session, order: Order, reason: str, by: str, refunds: int) -> None:
    if not _enabled(db, "telegram_notify_cancellations"):
        return
    refund = f"\nRefund to give back: {refunds}" if refunds else ""
    _after_commit(db, f"✖️ <b>Order #{order.display_number} cancelled</b> by {tg.esc(by)}\n"
                      f"Reason: {tg.esc(reason)}{refund}")


def khqr_not_paid(db: Session, order: Order) -> None:
    """A customer chose KHQR but no payment arrived before the order expired."""
    if not _enabled(db, "telegram_notify_failed_payments"):
        return
    _after_commit(db, f"⌛ <b>Order #{order.display_number} expired unpaid</b> · "
                      f"{tg.esc(order.table_label or CHANNEL.get(order.channel, ''))} · {_money(order.total_usd_cents)}\n"
                      "No KHQR payment arrived. Nothing was sent to the kitchen.")


CUSTOMER_TEXT = {
    "paid": {"en": "✅ LAGOM: payment received for order #{n}. We are preparing it.",
             "km": "✅ LAGOM: បានទទួលការបង់ប្រាក់សម្រាប់ការកុម្ម៉ង់ #{n}។ យើងកំពុងរៀបចំ។",
             "zh": "✅ LAGOM：已收到订单 #{n} 的付款，正在为您制作。"},
    "ready": {"en": "🔔 LAGOM: order #{n} is ready. Please come to the counter.",
              "km": "🔔 LAGOM: ការកុម្ម៉ង់ #{n} រួចរាល់ហើយ។ សូមមកយកនៅបញ្ជរ។",
              "zh": "🔔 LAGOM：订单 #{n} 已完成，请到柜台取餐。"},
}


def tell_customer(db: Session, order: Order, kind: str) -> None:
    """Message the customer in Telegram (only for orders placed in the Telegram Mini App)."""
    from app.models import TableSession

    s = db.get(TableSession, order.table_session_id) if order.table_session_id else None
    if not s or not s.telegram_user_id:
        return
    text = CUSTOMER_TEXT[kind].get(s.language, CUSTOMER_TEXT[kind]["en"]).format(n=order.display_number)
    user_id = s.telegram_user_id

    @event.listens_for(db, "after_commit", once=True)
    def _send(_session):
        _safely(tg.send_to_user, user_id, text)


def _paid_listener(db: Session, order: Order) -> None:
    order_paid(db, order)
    tell_customer(db, order, "paid")


def register() -> None:
    from app.services import orders as order_service

    if _paid_listener not in order_service.paid_listeners:
        order_service.paid_listeners.append(_paid_listener)


register()


# ---------------------------------------------------------------- daily summary
def daily_summary_text(db: Session, day) -> str:
    from app.services.finance import report

    r = report(db, day, day, "day")
    orders = db.scalars(select(Order).where(Order.business_date == day)).all()
    top = Counter()
    for o in orders:
        if o.status in ("PAID", "PREPARING", "READY", "SERVED"):
            for i in o.items:
                top[i.name_en] += i.quantity
    best = ", ".join(f"{n} ×{q}" for n, q in top.most_common(3)) or "—"
    expenses = sum(e.amount_usd_cents for e in db.scalars(select(Expense).where(Expense.spent_on == day)))
    low = [i.name for i in db.scalars(select(Ingredient).where(Ingredient.is_active.is_(True))) if i.is_low]
    avg = r["net_sales_usd_cents"] // r["orders"] if r["orders"] else 0
    lines = [
        f"📊 <b>LAGOM · {day:%a %d %b %Y}</b>",
        f"Sales: <b>{_money(r['net_sales_usd_cents'])}</b> from {r['orders']} orders (average {_money(avg)})",
        f"ABA KHQR {_money(r['sales_by_method'].get('khqr', 0))} · Cash {_money(r['sales_by_method'].get('cash', 0))}",
        f"Discounts {_money(r['discounts_usd_cents'])} · Refunds {_money(r['refunds_usd_cents'])}",
        f"Ingredients used {_money(r['cogs_usd_cents'])} · Expenses today {_money(expenses)}",
        f"Best sellers: {tg.esc(best)}",
    ]
    if low:
        lines.append(f"Low stock: {tg.esc(', '.join(low[:8]))}")
    return "\n".join(lines)


def maybe_send_daily_summary(db: Session, now: datetime | None = None) -> bool:
    """Called every minute. Sends once per day, after the closing time set in Settings."""
    if not _enabled(db, "telegram_daily_summary") or not tg.enabled() and tg.sent_log is None:
        return False
    tz = ZoneInfo(app_settings.get_setting(db, "timezone"))
    local = (now or utcnow()).astimezone(tz)
    hh, mm = (int(x) for x in app_settings.get_setting(db, "daily_summary_time").split(":"))
    if (local.hour, local.minute) < (hh, mm):
        return False
    today = local.date().isoformat()
    if app_settings.get_setting(db, "daily_summary_last_sent") == today:
        return False
    app_settings.set_setting(db, "daily_summary_last_sent", today)
    db.commit()
    _safely(lambda: tg.notify(daily_summary_text(db, local.date())))
    return True
