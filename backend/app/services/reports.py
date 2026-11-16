"""Dashboard numbers, always calculated from real orders and payments.

"Sales" = orders that were paid (PAID, PREPARING, READY, SERVED). Cancelled and
unpaid/expired orders are not sales. Dates are restaurant dates (Asia/Phnom_Penh).
"""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import DiningTable, Ingredient, Order
from app.models.base import utcnow
from app.models.enums import OrderStatus, PaymentProvider, PaymentStatus
from app.services import app_settings

SOLD = (OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.SERVED)
PRESETS = ("today", "yesterday", "7d", "30d", "month", "custom")


def resolve_period(db: Session, preset: str, start: date | None = None, end: date | None = None) -> tuple[date, date]:
    tz = ZoneInfo(app_settings.get_setting(db, "timezone"))
    today = utcnow().astimezone(tz).date()
    if preset == "today":
        return today, today
    if preset == "yesterday":
        y = today - timedelta(days=1)
        return y, y
    if preset == "7d":
        return today - timedelta(days=6), today
    if preset == "30d":
        return today - timedelta(days=29), today
    if preset == "month":
        return today.replace(day=1), today
    if preset == "custom" and start and end:
        if end < start:
            start, end = end, start
        if (end - start).days > 366:
            raise ValueError("Choose a period of one year or less.")
        return start, end
    raise ValueError("Unknown period.")


def dashboard(db: Session, start: date, end: date) -> dict:
    tz = ZoneInfo(app_settings.get_setting(db, "timezone"))
    orders = db.scalars(
        select(Order).where(Order.business_date >= start, Order.business_date <= end)
        .options(selectinload(Order.items), selectinload(Order.payments))
    ).all()
    sold = [o for o in orders if o.status in SOLD]
    revenue = sum(o.total_usd_cents for o in sold)
    discounts = sum(o.discount_usd_cents for o in sold)

    # Sales chart: by hour for one day, by day otherwise
    single_day = start == end
    buckets: dict[str, int] = defaultdict(int)
    if single_day:
        for h in range(24):
            buckets[f"{h:02d}"] = 0
        for o in sold:
            buckets[f"{(o.paid_at or o.created_at).astimezone(tz).hour:02d}"] += o.total_usd_cents
    else:
        d = start
        while d <= end:
            buckets[d.isoformat()] = 0
            d += timedelta(days=1)
        for o in sold:
            buckets[o.business_date.isoformat()] += o.total_usd_cents

    # Best sellers
    qty: Counter = Counter()
    amount: Counter = Counter()
    for o in sold:
        for i in o.items:
            if i.status != "CANCELLED":
                qty[i.name_en] += i.quantity
                amount[i.name_en] += i.line_total_usd_cents
    best = [{"name": n, "quantity": q, "revenue_usd_cents": amount[n]} for n, q in qty.most_common(8)]

    # Payment breakdown (USD value of each paid order, by how it was paid)
    by_method: dict[str, dict] = {p.value: {"orders": 0, "usd_cents": 0} for p in PaymentProvider}
    for o in sold:
        paid = next((p for p in o.payments if p.status in (PaymentStatus.APPROVED, PaymentStatus.REFUNDED,
                                                          PaymentStatus.PARTIALLY_REFUNDED)), None)
        key = paid.provider.value if paid else "OTHER"
        by_method.setdefault(key, {"orders": 0, "usd_cents": 0})
        by_method[key]["orders"] += 1
        by_method[key]["usd_cents"] += o.total_usd_cents

    # Tables: sales in the period and orders open right now
    per_table: dict[str, dict] = {}
    for t in db.scalars(select(DiningTable).where(DiningTable.is_active.is_(True)).order_by(DiningTable.sort_order)):
        per_table[t.label] = {"table": t.label, "orders": 0, "usd_cents": 0, "open_orders": 0}
    for o in sold:
        if o.table_label in per_table:
            per_table[o.table_label]["orders"] += 1
            per_table[o.table_label]["usd_cents"] += o.total_usd_cents
    open_now = db.scalars(select(Order).where(Order.status.in_([OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY]))).all()
    for o in open_now:
        if o.table_label in per_table:
            per_table[o.table_label]["open_orders"] += 1

    low_stock = [
        {"id": i.id, "name": i.name, "quantity": str(i.quantity), "unit": i.unit, "threshold": str(i.low_stock_threshold)}
        for i in db.scalars(select(Ingredient).where(Ingredient.is_active.is_(True)).order_by(Ingredient.name))
        if i.quantity <= i.low_stock_threshold
    ]

    return {
        "period": {"start": start, "end": end, "by": "hour" if single_day else "day"},
        "revenue_usd_cents": revenue,
        "orders": len(sold),
        "average_order_usd_cents": round(revenue / len(sold)) if sold else 0,
        "discounts_usd_cents": discounts,
        "pending_payment": sum(1 for o in orders if o.status == OrderStatus.PENDING_PAYMENT),
        "in_progress": sum(1 for o in orders if o.status in (OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY)),
        "completed": sum(1 for o in orders if o.status == OrderStatus.SERVED),
        "cancelled": sum(1 for o in orders if o.status == OrderStatus.CANCELLED),
        "sales_chart": [{"label": k, "usd_cents": v} for k, v in buckets.items()],
        "best_sellers": best,
        "payments": by_method,
        "tables": list(per_table.values()),
        "low_stock": low_stock,
        "generated_at": datetime.now(tz),
    }
