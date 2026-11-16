"""Profit and loss from real records.

    Gross sales        what the menu prices add up to (paid orders)
  − Discounts
  = Net sales          what customers actually paid
  − Refunds            money given back (completed refunds)
  − Cost of goods sold ingredients used by those orders, at their cost when used
  − Waste              spoiled or thrown-away stock recorded in inventory
  = Gross profit
  − Expenses           rent, salaries, electricity… (entered by the owner)
  = Net profit (estimate)

Revenue is not profit: this report keeps them apart. Ingredient purchases are
shown for information; they become a cost only when the ingredients are used
(COGS), so they are never counted twice. Spending on ingredients that are not
tracked in inventory can be entered as an "Ingredients" expense instead.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Expense, Order, Payment, Purchase, Refund, StockMovement
from app.models.enums import Currency, ExpenseCategory, PaymentStatus, StockMovementKind
from app.services import app_settings
from app.services.reports import SOLD

GROUPS = ("day", "week", "month", "quarter", "year")


def auto_group(start: date, end: date) -> str:
    days = (end - start).days + 1
    return "day" if days <= 31 else "week" if days <= 120 else "month"


def bucket(d: date, group: str) -> str:
    if group == "day":
        return d.isoformat()
    if group == "week":
        monday = d - timedelta(days=d.weekday())
        return f"Week of {monday.isoformat()}"
    if group == "month":
        return f"{d.year}-{d.month:02d}"
    if group == "quarter":
        return f"{d.year} Q{(d.month - 1) // 3 + 1}"
    return str(d.year)


def _local_date(dt: datetime, tz: ZoneInfo) -> date:
    return dt.astimezone(tz).date()


def report(db: Session, start: date, end: date, group: str | None = None) -> dict:
    tz = ZoneInfo(app_settings.get_setting(db, "timezone"))
    group = group or auto_group(start, end)
    # UTC window wide enough to contain the local dates; exact local-date filter below
    lo = datetime.combine(start - timedelta(days=1), datetime.min.time())
    hi = datetime.combine(end + timedelta(days=2), datetime.min.time())

    rows: dict[str, dict] = defaultdict(lambda: {"net_sales": 0, "refunds": 0, "cogs": 0, "waste": 0, "expenses": 0, "orders": 0})

    orders = db.scalars(select(Order).where(Order.business_date >= start, Order.business_date <= end,
                                            Order.status.in_(SOLD)).options(selectinload(Order.payments))).all()
    gross = sum(o.subtotal_usd_cents for o in orders)
    discounts = sum(o.discount_usd_cents for o in orders)
    net_sales = sum(o.total_usd_cents for o in orders)
    by_method = {"cash": 0, "khqr": 0}
    for o in orders:
        b = rows[bucket(o.business_date, group)]
        b["net_sales"] += o.total_usd_cents
        b["orders"] += 1
        paid = next((p for p in o.payments if p.status in (PaymentStatus.APPROVED, PaymentStatus.REFUNDED,
                                                           PaymentStatus.PARTIALLY_REFUNDED)), None)
        if paid:
            by_method[paid.payment_option] = by_method.get(paid.payment_option, 0) + o.total_usd_cents

    # Refunds that were actually given back in the period (orders cancelled after payment)
    refunds_total = 0
    for r in db.scalars(select(Refund).where(Refund.status == "COMPLETED", Refund.updated_at >= lo, Refund.updated_at < hi)):
        d = _local_date(r.updated_at, tz)
        if not (start <= d <= end):
            continue
        p = db.get(Payment, r.payment_id)
        usd = r.amount_minor if r.currency == Currency.USD else int(Decimal(r.amount_minor) / p.order.khr_per_usd * 100)
        refunds_total += usd
        rows[bucket(d, group)]["refunds"] += usd

    # Cost of ingredients used (sales minus reversals of cancelled orders)
    cogs_total = 0
    for m in db.scalars(select(StockMovement).where(
            StockMovement.kind.in_([StockMovementKind.SALE, StockMovementKind.SALE_REVERSAL]),
            StockMovement.created_at >= lo, StockMovement.created_at < hi)):
        d = _local_date(m.created_at, tz)
        if not (start <= d <= end):
            continue
        cents = int(-Decimal(m.change) * m.unit_cost_usd_millicents / 1000)
        cogs_total += cents
        rows[bucket(d, group)]["cogs"] += cents
    waste_total = 0
    for m in db.scalars(select(StockMovement).where(StockMovement.kind == StockMovementKind.WASTE,
                                                    StockMovement.created_at >= lo, StockMovement.created_at < hi)):
        d = _local_date(m.created_at, tz)
        if start <= d <= end:
            cents = int(-Decimal(m.change) * m.unit_cost_usd_millicents / 1000)
            waste_total += cents
            rows[bucket(d, group)]["waste"] += cents

    expenses = db.scalars(select(Expense).where(Expense.spent_on >= start, Expense.spent_on <= end)).all()
    by_category = {c.value: 0 for c in ExpenseCategory}
    for e in expenses:
        by_category[e.category.value] += e.amount_usd_cents
        rows[bucket(e.spent_on, group)]["expenses"] += e.amount_usd_cents
    expenses_total = sum(by_category.values())

    purchases_total = sum(p.total_usd_cents for p in db.scalars(
        select(Purchase).where(Purchase.purchased_on >= start, Purchase.purchased_on <= end)))

    gross_profit = net_sales - refunds_total - cogs_total - waste_total
    periods = []
    for label in sorted(rows):
        r = rows[label]
        gp = r["net_sales"] - r["refunds"] - r["cogs"] - r["waste"]
        periods.append({"label": label, **r, "gross_profit": gp, "net_profit": gp - r["expenses"]})

    return {
        "period": {"start": start, "end": end, "group": group},
        "orders": len(orders),
        "gross_sales_usd_cents": gross,
        "discounts_usd_cents": discounts,
        "net_sales_usd_cents": net_sales,
        "refunds_usd_cents": refunds_total,
        "cogs_usd_cents": cogs_total,
        "gross_profit_usd_cents": gross_profit,
        "gross_margin_percent": round(gross_profit / net_sales * 100, 1) if net_sales else None,
        "expenses_usd_cents": expenses_total,
        "net_profit_usd_cents": gross_profit - expenses_total,
        "expenses_by_category": by_category,
        "sales_by_method": by_method,
        "purchases_usd_cents": purchases_total,
        "waste_usd_cents": waste_total,
        "periods": periods,
    }
