from decimal import Decimal

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, LargeBinary, String, Text, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import TimestampMixin, UTCDateTime, str_enum, utcnow
from app.models.enums import OptionSelection, Station


class Category(TimestampMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name_en: Mapped[str] = mapped_column(String(120))
    name_km: Mapped[str] = mapped_column(String(120), default="")
    name_zh: Mapped[str] = mapped_column(String(120), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Products in this category go to this station unless the product overrides it
    default_station: Mapped[Station] = mapped_column(str_enum(Station), default=Station.KITCHEN)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    name_en: Mapped[str] = mapped_column(String(160))
    name_km: Mapped[str] = mapped_column(String(160), default="")
    name_zh: Mapped[str] = mapped_column(String(160), default="")
    description_en: Mapped[str] = mapped_column(Text, default="")
    description_km: Mapped[str] = mapped_column(Text, default="")
    description_zh: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    # Photo credit when the licence requires it, e.g. "Photo: Jane Doe, CC BY-SA 4.0, Wikimedia Commons"
    image_credit: Mapped[str] = mapped_column(String(300), default="")
    image_source_url: Mapped[str] = mapped_column(String(500), default="")
    price_usd_cents: Mapped[int] = mapped_column(Integer)
    station: Mapped[Station | None] = mapped_column(str_enum(Station), nullable=True)
    prep_minutes: Mapped[int] = mapped_column(Integer, default=10)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)  # temporarily sold out = False
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)  # hidden permanently
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    is_best_seller: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_special_instructions: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped[Category] = relationship(back_populates="products")
    option_groups: Mapped[list["OptionGroup"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="OptionGroup.sort_order"
    )
    recipe: Mapped[list["RecipeItem"]] = relationship(  # noqa: F821
        back_populates="product", cascade="all, delete-orphan"
    )

    @property
    def effective_station(self) -> Station:
        return self.station or self.category.default_station


class OptionGroup(Base):
    """A set of choices on a product: Size, Sugar, Ice, Toppings, Extras…"""

    __tablename__ = "option_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    name_en: Mapped[str] = mapped_column(String(80))
    name_km: Mapped[str] = mapped_column(String(80), default="")
    name_zh: Mapped[str] = mapped_column(String(80), default="")
    selection: Mapped[OptionSelection] = mapped_column(str_enum(OptionSelection))
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    min_select: Mapped[int] = mapped_column(Integer, default=0)
    max_select: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped[Product] = relationship(back_populates="option_groups")
    options: Mapped[list["Option"]] = relationship(
        back_populates="group", cascade="all, delete-orphan", order_by="Option.sort_order"
    )


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("option_groups.id", ondelete="CASCADE"), index=True)
    name_en: Mapped[str] = mapped_column(String(80))
    name_km: Mapped[str] = mapped_column(String(80), default="")
    name_zh: Mapped[str] = mapped_column(String(80), default="")
    price_delta_usd_cents: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    # Multiplies the product recipe (e.g. Large = 1.5x milk). 1 = no change.
    recipe_multiplier: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=Decimal("1"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    group: Mapped[OptionGroup] = relationship(back_populates="options")


class Promotion(TimestampMixin, Base):
    """A banner on the customer menu (e.g. 'Happy hour: 20% off milk tea')."""

    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_en: Mapped[str] = mapped_column(String(160))
    title_km: Mapped[str] = mapped_column(String(160), default="")
    title_zh: Mapped[str] = mapped_column(String(160), default="")
    subtitle_en: Mapped[str] = mapped_column(String(255), default="")
    subtitle_km: Mapped[str] = mapped_column(String(255), default="")
    subtitle_zh: Mapped[str] = mapped_column(String(255), default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class StoredPhoto(Base):
    """A menu photo kept inside the database (PHOTO_STORAGE=database).

    Used on hosting without a permanent disk (Render's free plan wipes files on every
    restart) when Cloudflare R2 is not set up. Photos are small JPEGs (max 1600 px).
    """

    __tablename__ = "stored_photos"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
