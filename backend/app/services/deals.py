"""Timed deals (happy hour) and automatic "sold out" from stock.

Both are applied by the server while pricing, so what the customer pays is always
decided here, never by the phone.
"""
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Deal, Ingredient, Product, RecipeItem
from app.models.base import utcnow
from app.services import app_settings


def _local(db: Session, now: datetime | None) -> datetime:
    return (now or utcnow()).astimezone(ZoneInfo(app_settings.get_setting(db, "timezone")))


def deal_is_on(deal: Deal, local: datetime) -> bool:
    if not deal.is_active or str(local.weekday()) not in deal.weekdays:
        return False
    hm = local.strftime("%H:%M")
    if deal.start_time <= deal.end_time:
        return deal.start_time <= hm <= deal.end_time
    return hm >= deal.start_time or hm <= deal.end_time  # e.g. 22:00–02:00 (over midnight)


class DealBook:
    """The deals running right now, looked up once per request."""

    def __init__(self, db: Session, now: datetime | None = None):
        local = _local(db, now)
        self.deals = [d for d in db.scalars(select(Deal).where(Deal.is_active.is_(True))) if deal_is_on(d, local)]

    def best_for(self, product: Product) -> Deal | None:
        matching = [d for d in self.deals
                    if (d.product_id == product.id)
                    or (d.product_id is None and d.category_id == product.category_id)
                    or (d.product_id is None and d.category_id is None)]
        return max(matching, key=lambda d: d.percent, default=None)


def apply_percent(cents: int, percent: int) -> int:
    """Price after a percentage off, rounded to the nearest cent."""
    return int((Decimal(cents) * (100 - percent) / 100).quantize(Decimal("1")))


def short_product_ids(db: Session, product_ids: set[int] | None = None) -> set[int]:
    """Dishes whose basic recipe needs more of an ingredient than is in stock.

    Only dishes with a recipe are checked, so a restaurant that does not use the
    inventory never sees anything marked sold out automatically.
    """
    if not app_settings.get_setting(db, "auto_sold_out"):
        return set()
    q = (select(RecipeItem.product_id, RecipeItem.quantity, Ingredient.quantity)
         .join(Ingredient, Ingredient.id == RecipeItem.ingredient_id)
         .where(RecipeItem.option_id.is_(None), Ingredient.is_active.is_(True)))
    if product_ids is not None:
        q = q.where(RecipeItem.product_id.in_(product_ids))
    return {pid for pid, need, have in db.execute(q) if Decimal(have) < Decimal(need)}
