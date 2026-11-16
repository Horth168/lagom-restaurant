"""Server-side pricing.

The customer's phone never decides a price. It only sends *which* product,
options and quantity it wants; this module checks every choice against the
database and calculates the price. The same code is used for the cart preview
and for creating the real order.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Option, OptionGroup, Product
from app.models.enums import OptionSelection, Station
from app.services.app_settings import khr_per_usd, usd_cents_to_khr

MAX_QTY_PER_LINE = 50
MAX_LINES = 40


class CartLineIn(BaseModel):
    product_id: int
    option_ids: list[int] = Field(default_factory=list, max_length=30)
    quantity: int = Field(ge=1, le=MAX_QTY_PER_LINE)
    special_instructions: str = Field("", max_length=255)


class CartIn(BaseModel):
    items: list[CartLineIn] = Field(min_length=1, max_length=MAX_LINES)


class PricingError(ValueError):
    def __init__(self, message: str, line: int | None = None, code: str = "invalid"):
        super().__init__(message)
        self.message = message
        self.line = line
        self.code = code


@dataclass
class PricedLine:
    product: Product
    options: list[Option]
    quantity: int
    special_instructions: str
    unit_price_usd_cents: int
    line_total_usd_cents: int
    station: Station
    prep_minutes: int
    option_snapshot: list[dict] = field(default_factory=list)


@dataclass
class PricedCart:
    lines: list[PricedLine]
    subtotal_usd_cents: int
    khr_per_usd: Decimal
    subtotal_khr: int

    @property
    def estimated_minutes(self) -> int:
        # Stations work in parallel; the slowest item decides, plus a little per extra item
        if not self.lines:
            return 0
        slowest = max(line.prep_minutes for line in self.lines)
        extra = max(0, sum(line.quantity for line in self.lines) - 1)
        return slowest + min(extra, 10)


def _load_products(db: Session, ids: set[int]) -> dict[int, Product]:
    rows = db.scalars(
        select(Product)
        .where(Product.id.in_(ids))
        .options(
            selectinload(Product.category),
            selectinload(Product.option_groups).selectinload(OptionGroup.options),
        )
    ).all()
    return {p.id: p for p in rows}


def price_line(product: Product | None, line: CartLineIn, index: int) -> PricedLine:
    if product is None or product.is_archived or not product.category.is_active:
        raise PricingError("This item is no longer on the menu.", index, "not_found")
    if not product.is_available:
        raise PricingError(f"{product.name_en} is sold out right now.", index, "sold_out")

    if len(set(line.option_ids)) != len(line.option_ids):
        raise PricingError("The same option was chosen twice.", index)
    options_by_id = {o.id: (g, o) for g in product.option_groups for o in g.options}
    chosen: dict[int, list[Option]] = {g.id: [] for g in product.option_groups}
    for oid in line.option_ids:
        if oid not in options_by_id:
            raise PricingError("An option does not belong to this item.", index)
        group, option = options_by_id[oid]
        if not option.is_available:
            raise PricingError(f"{option.name_en} is not available right now.", index, "sold_out")
        chosen[group.id].append(option)

    for group in product.option_groups:
        picks = chosen[group.id]
        limit = 1 if group.selection == OptionSelection.SINGLE else group.max_select
        minimum = max(group.min_select, 1 if group.is_required else 0)
        if len(picks) < minimum:
            raise PricingError(f"Please choose {group.name_en}.", index, "missing_option")
        if len(picks) > limit:
            raise PricingError(f"Too many choices for {group.name_en}.", index)

    instructions = line.special_instructions.strip()
    if instructions and not product.allow_special_instructions:
        instructions = ""

    ordered = [o for g in product.option_groups for o in chosen[g.id]]
    unit = product.price_usd_cents + sum(o.price_delta_usd_cents for o in ordered)
    snapshot = [
        {
            "option_id": o.id,
            "group_en": o.group.name_en, "group_km": o.group.name_km, "group_zh": o.group.name_zh,
            "name_en": o.name_en, "name_km": o.name_km, "name_zh": o.name_zh,
            "price_delta_usd_cents": o.price_delta_usd_cents,
        }
        for o in ordered
    ]
    return PricedLine(
        product=product,
        options=ordered,
        quantity=line.quantity,
        special_instructions=instructions,
        unit_price_usd_cents=unit,
        line_total_usd_cents=unit * line.quantity,
        station=product.effective_station,
        prep_minutes=product.prep_minutes,
        option_snapshot=snapshot,
    )


def price_cart(db: Session, cart: CartIn) -> PricedCart:
    products = _load_products(db, {line.product_id for line in cart.items})
    lines = [price_line(products.get(line.product_id), line, i) for i, line in enumerate(cart.items)]
    subtotal = sum(line.line_total_usd_cents for line in lines)
    rate = khr_per_usd(db)
    return PricedCart(lines=lines, subtotal_usd_cents=subtotal, khr_per_usd=rate,
                      subtotal_khr=usd_cents_to_khr(subtotal, rate))
