"""Ingredient stock: deduction from recipes, purchases, adjustments, alerts.

Rules
- Each order deducts its ingredients exactly ONCE. A database unique key on
  (order, ingredient, kind) makes a second deduction impossible, even if two
  events (payment + kitchen) arrive at the same moment.
- When it happens is the owner's choice (setting inventory_deduct_on):
  PAID (as soon as the order is paid) or READY (when the kitchen finishes it).
- A cancelled order that had been deducted puts the stock back (SALE_REVERSAL).
- Every change is a StockMovement row with the unit cost at that moment, so the
  cost of goods sold (COGS) in reports never changes when prices change later.
"""
import logging
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Ingredient, Option, Order, RecipeItem, StockMovement
from app.models.enums import ItemStatus, StockMovementKind
from app.services import app_settings
from app.services import telegram as tg

log = logging.getLogger("lagom.inventory")
Q = Decimal("0.001")


def _q(x: Decimal) -> Decimal:
    return x.quantize(Q, rounding=ROUND_HALF_UP)


def usage_for_order(db: Session, order: Order) -> dict[int, Decimal]:
    """Ingredient id -> quantity this order uses, from the products' recipes."""
    product_ids = {i.product_id for i in order.items if i.product_id}
    if not product_ids:
        return {}
    lines = db.scalars(select(RecipeItem).where(RecipeItem.product_id.in_(product_ids))).all()
    by_product: dict[int, list[RecipeItem]] = defaultdict(list)
    for r in lines:
        by_product[r.product_id].append(r)
    option_ids = {o["option_id"] for i in order.items for o in i.options if o.get("option_id")}
    multipliers = {o.id: Decimal(o.recipe_multiplier or 1)
                   for o in db.scalars(select(Option).where(Option.id.in_(option_ids)))} if option_ids else {}

    usage: dict[int, Decimal] = defaultdict(Decimal)
    for item in order.items:
        if item.status == ItemStatus.CANCELLED or not item.product_id:
            continue
        chosen = {o["option_id"] for o in item.options if o.get("option_id")}
        factor = Decimal(1)
        for oid in chosen:
            factor *= multipliers.get(oid, Decimal(1))  # e.g. Large = 1.6x milk
        for r in by_product.get(item.product_id, []):
            if r.option_id is None:
                scale = factor if r.scales_with_size else Decimal(1)
                usage[r.ingredient_id] += Decimal(r.quantity) * scale * item.quantity
            elif r.option_id in chosen:  # e.g. extra espresso shot adds 9 g beans
                usage[r.ingredient_id] += Decimal(r.quantity) * item.quantity
    return {k: _q(v) for k, v in usage.items() if v > 0}


def _move(db: Session, ingredient: Ingredient, change: Decimal, kind: StockMovementKind, *, order_id=None,
          purchase_id=None, user_id=None, note="", unit_cost=None) -> StockMovement:
    ingredient.quantity = _q(Decimal(ingredient.quantity) + change)
    m = StockMovement(ingredient_id=ingredient.id, kind=kind, change=_q(change), balance_after=ingredient.quantity,
                      unit_cost_usd_millicents=ingredient.unit_cost_usd_millicents if unit_cost is None else unit_cost,
                      order_id=order_id, purchase_id=purchase_id, user_id=user_id, note=note[:255])
    db.add(m)
    return m


def check_low_stock(db: Session, ingredient: Ingredient) -> None:
    """Alert once when an ingredient drops to its alert level; re-arm when restocked."""
    low = Decimal(ingredient.quantity) <= Decimal(ingredient.low_stock_threshold)
    if low and not ingredient.low_stock_alerted:
        ingredient.low_stock_alerted = True
        if app_settings.get_setting(db, "telegram_notify_low_stock"):
            tg.notify(f"📦 <b>Low stock</b>: {tg.esc(ingredient.name)} — {_q(Decimal(ingredient.quantity)).normalize()} "
                      f"{tg.esc(ingredient.unit)} left (alert at {Decimal(ingredient.low_stock_threshold).normalize()})")
    elif not low and ingredient.low_stock_alerted:
        ingredient.low_stock_alerted = False


def deduct_for_order(db: Session, order: Order) -> bool:
    """Take this order's ingredients out of stock. Safe to call any number of times."""
    if order.inventory_deducted:
        return False
    usage = usage_for_order(db, order)
    try:
        with db.begin_nested():
            for ing_id, qty in usage.items():
                ing = db.get(Ingredient, ing_id, with_for_update=True)
                if ing is None:
                    continue
                _move(db, ing, -qty, StockMovementKind.SALE, order_id=order.id, note=f"Order #{order.display_number}")
                check_low_stock(db, ing)
            order.inventory_deducted = True
            db.flush()
    except IntegrityError:
        # Another process deducted this order at the same moment: nothing more to do
        db.refresh(order)
        return False
    return True


def reverse_for_order(db: Session, order: Order) -> bool:
    """Put a cancelled order's ingredients back (only if they had been deducted)."""
    if not order.inventory_deducted:
        return False
    sales = db.scalars(select(StockMovement).where(StockMovement.order_id == order.id,
                                                   StockMovement.kind == StockMovementKind.SALE)).all()
    try:
        with db.begin_nested():
            for m in sales:
                ing = db.get(Ingredient, m.ingredient_id, with_for_update=True)
                _move(db, ing, -Decimal(m.change), StockMovementKind.SALE_REVERSAL, order_id=order.id,
                      note=f"Order #{order.display_number} cancelled", unit_cost=m.unit_cost_usd_millicents)
                check_low_stock(db, ing)
            order.inventory_deducted = False
            db.flush()
    except IntegrityError:
        db.refresh(order)
        return False
    return True


def receive_purchase_line(db: Session, ingredient: Ingredient, quantity: Decimal, line_total_cents: int, *,
                          purchase_id: int, user_id: int) -> None:
    """Add bought stock and update the average cost per unit (weighted average)."""
    old_qty = max(Decimal(ingredient.quantity), Decimal(0))
    old_cost = Decimal(ingredient.unit_cost_usd_millicents)
    new_unit = Decimal(line_total_cents) * 1000 / quantity if quantity > 0 else old_cost
    total_qty = old_qty + quantity
    if total_qty > 0:
        ingredient.unit_cost_usd_millicents = int(((old_qty * old_cost + quantity * new_unit) / total_qty)
                                                  .to_integral_value(ROUND_HALF_UP))
    _move(db, ingredient, quantity, StockMovementKind.PURCHASE, purchase_id=purchase_id, user_id=user_id,
          note="Purchase", unit_cost=int(new_unit.to_integral_value(ROUND_HALF_UP)))
    check_low_stock(db, ingredient)


def adjust(db: Session, ingredient: Ingredient, *, change: Decimal, kind: StockMovementKind, user_id: int,
           note: str) -> StockMovement:
    m = _move(db, ingredient, change, kind, user_id=user_id, note=note)
    check_low_stock(db, ingredient)
    return m


# ---------------------------------------------------------------- automatic triggers
def _on_paid(db: Session, order: Order) -> None:
    if app_settings.get_setting(db, "inventory_deduct_on") == "PAID":
        deduct_for_order(db, order)


def register() -> None:
    from app.services import orders as order_service

    if _on_paid not in order_service.paid_listeners:
        order_service.paid_listeners.append(_on_paid)


register()
