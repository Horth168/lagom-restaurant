from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UTCDateTime, str_enum, utcnow
from app.models.enums import StockMovementKind

QTY = Numeric(14, 3)  # quantities like 0.018 kg of coffee beans


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str] = mapped_column(String(40), default="")
    contact_name: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Ingredient(TimestampMixin, Base):
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    unit: Mapped[str] = mapped_column(String(20))  # g, kg, ml, l, pcs
    quantity: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    low_stock_threshold: Mapped[Decimal] = mapped_column(QTY, default=Decimal("0"))
    # Average cost of one unit, in thousandths of a US cent for precision (e.g. 1 g of beans)
    unit_cost_usd_millicents: Mapped[int] = mapped_column(Integer, default=0)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    low_stock_alerted: Mapped[bool] = mapped_column(Boolean, default=False)

    supplier: Mapped[Supplier | None] = relationship()

    @property
    def is_low(self) -> bool:
        return self.quantity <= self.low_stock_threshold


class RecipeItem(Base):
    """How much of an ingredient one unit of a product uses."""

    __tablename__ = "recipe_items"
    __table_args__ = (UniqueConstraint("product_id", "ingredient_id", "option_id", name="uq_recipe_line"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    # If set, this line only applies when the option is chosen (e.g. Extra espresso → +9 g beans)
    option_id: Mapped[int | None] = mapped_column(ForeignKey("options.id", ondelete="CASCADE"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(QTY)
    # Bigger sizes use more milk/coffee (True), but still one cup and one straw (False)
    scales_with_size: Mapped[bool] = mapped_column(Boolean, default=True)

    product: Mapped["Product"] = relationship(back_populates="recipe")  # noqa: F821
    ingredient: Mapped[Ingredient] = relationship()


class Purchase(TimestampMixin, Base):
    """Stock bought from a supplier."""

    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    purchased_on: Mapped[date] = mapped_column(Date, index=True)
    total_usd_cents: Mapped[int] = mapped_column(Integer)
    invoice_ref: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    lines: Mapped[list["PurchaseLine"]] = relationship(back_populates="purchase", cascade="all, delete-orphan")
    supplier: Mapped[Supplier | None] = relationship()


class PurchaseLine(Base):
    __tablename__ = "purchase_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id", ondelete="CASCADE"), index=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    quantity: Mapped[Decimal] = mapped_column(QTY)
    line_total_usd_cents: Mapped[int] = mapped_column(Integer)

    purchase: Mapped[Purchase] = relationship(back_populates="lines")
    ingredient: Mapped[Ingredient] = relationship()


class StockMovement(Base):
    """Every change to stock. The ingredient quantity is the sum of these."""

    __tablename__ = "stock_movements"
    # An order can deduct each ingredient only once → no double deductions
    __table_args__ = (
        UniqueConstraint("order_id", "ingredient_id", "kind", name="uq_stock_once_per_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"), index=True)
    kind: Mapped[StockMovementKind] = mapped_column(str_enum(StockMovementKind))
    change: Mapped[Decimal] = mapped_column(QTY)  # negative = stock went out
    balance_after: Mapped[Decimal] = mapped_column(QTY)
    unit_cost_usd_millicents: Mapped[int] = mapped_column(Integer, default=0)  # cost snapshot (for COGS)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)

    ingredient: Mapped[Ingredient] = relationship()
