"""Admin: categories, products, options, availability and photos."""
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.deps import CurrentStaff, require
from app.db import get_db
from app.models import Category, Option, OptionGroup, Product
from app.models.enums import OptionSelection, Station
from app.services.audit import audit
from app.services.storage import UploadProblem, save_product_photo

router = APIRouter(prefix="/api/admin", tags=["menu admin"])

Name = Field(min_length=1, max_length=160)


# ---------------------------------------------------------------- shapes
class CategoryIn(BaseModel):
    slug: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9-]+$")
    name_en: str = Name
    name_km: str = Field("", max_length=120)
    name_zh: str = Field("", max_length=120)
    default_station: Station = Station.KITCHEN
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name_en: str | None = Field(None, min_length=1, max_length=120)
    name_km: str | None = Field(None, max_length=120)
    name_zh: str | None = Field(None, max_length=120)
    default_station: Station | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class OptionIn(BaseModel):
    id: int | None = None
    name_en: str = Field(min_length=1, max_length=80)
    name_km: str = Field("", max_length=80)
    name_zh: str = Field("", max_length=80)
    price_delta_usd_cents: int = Field(0, ge=0, le=100_000)
    is_default: bool = False
    is_available: bool = True


class GroupIn(BaseModel):
    id: int | None = None
    name_en: str = Field(min_length=1, max_length=80)
    name_km: str = Field("", max_length=80)
    name_zh: str = Field("", max_length=80)
    selection: OptionSelection = OptionSelection.SINGLE
    is_required: bool = False
    max_select: int = Field(1, ge=1, le=20)
    options: list[OptionIn] = Field(min_length=1, max_length=30)


class ProductIn(BaseModel):
    category_id: int
    name_en: str = Name
    name_km: str = Field("", max_length=160)
    name_zh: str = Field("", max_length=160)
    description_en: str = Field("", max_length=1000)
    description_km: str = Field("", max_length=1000)
    description_zh: str = Field("", max_length=1000)
    price_usd_cents: int = Field(ge=0, le=1_000_000)
    station: Station | None = None
    prep_minutes: int = Field(10, ge=0, le=180)
    is_available: bool = True
    is_featured: bool = False
    is_best_seller: bool = False
    allow_special_instructions: bool = True
    sort_order: int = 0
    option_groups: list[GroupIn] = Field(default_factory=list, max_length=12)


class ProductUpdate(BaseModel):
    category_id: int | None = None
    name_en: str | None = Field(None, min_length=1, max_length=160)
    name_km: str | None = Field(None, max_length=160)
    name_zh: str | None = Field(None, max_length=160)
    description_en: str | None = Field(None, max_length=1000)
    description_km: str | None = Field(None, max_length=1000)
    description_zh: str | None = Field(None, max_length=1000)
    price_usd_cents: int | None = Field(None, ge=0, le=1_000_000)
    station: Station | None = None
    prep_minutes: int | None = Field(None, ge=0, le=180)
    is_available: bool | None = None
    is_archived: bool | None = None
    is_featured: bool | None = None
    is_best_seller: bool | None = None
    allow_special_instructions: bool | None = None
    sort_order: int | None = None
    option_groups: list[GroupIn] | None = Field(None, max_length=12)


# ---------------------------------------------------------------- output
def product_out(p: Product) -> dict:
    return {
        "id": p.id, "category_id": p.category_id,
        "name_en": p.name_en, "name_km": p.name_km, "name_zh": p.name_zh,
        "description_en": p.description_en, "description_km": p.description_km, "description_zh": p.description_zh,
        "image_url": p.image_url, "image_credit": p.image_credit,
        "price_usd_cents": p.price_usd_cents, "station": p.station, "effective_station": p.effective_station,
        "prep_minutes": p.prep_minutes, "is_available": p.is_available, "is_archived": p.is_archived,
        "is_featured": p.is_featured, "is_best_seller": p.is_best_seller,
        "allow_special_instructions": p.allow_special_instructions, "sort_order": p.sort_order,
        "option_groups": [
            {"id": g.id, "name_en": g.name_en, "name_km": g.name_km, "name_zh": g.name_zh, "selection": g.selection,
             "is_required": g.is_required, "max_select": g.max_select,
             "options": [{"id": o.id, "name_en": o.name_en, "name_km": o.name_km, "name_zh": o.name_zh,
                          "price_delta_usd_cents": o.price_delta_usd_cents, "is_default": o.is_default,
                          "is_available": o.is_available} for o in g.options]}
            for g in p.option_groups
        ],
    }


def category_out(c: Category) -> dict:
    return {"id": c.id, "slug": c.slug, "name_en": c.name_en, "name_km": c.name_km, "name_zh": c.name_zh,
            "default_station": c.default_station, "sort_order": c.sort_order, "is_active": c.is_active}


def _load_product(db: Session, product_id: int) -> Product:
    p = db.scalar(select(Product).where(Product.id == product_id).options(
        selectinload(Product.category), selectinload(Product.option_groups).selectinload(OptionGroup.options)))
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
    return p


def _apply_groups(p: Product, groups: list[GroupIn]) -> None:
    """Update option groups in place: keep ids that still exist (recipes and history stay linked)."""
    existing = {g.id: g for g in p.option_groups}
    keep = []
    for gi, gin in enumerate(groups):
        g = existing.get(gin.id) if gin.id else None
        if g is None:
            g = OptionGroup()
        g.name_en, g.name_km, g.name_zh = gin.name_en.strip(), gin.name_km.strip(), gin.name_zh.strip()
        g.selection = gin.selection
        g.is_required = gin.is_required
        g.max_select = 1 if gin.selection == OptionSelection.SINGLE else max(1, min(gin.max_select, len(gin.options)))
        g.min_select = 1 if gin.is_required else 0
        g.sort_order = gi
        old_opts = {o.id: o for o in g.options}
        new_opts = []
        for oi, oin in enumerate(gin.options):
            o = old_opts.get(oin.id) if oin.id else None
            if o is None:
                o = Option()
            o.name_en, o.name_km, o.name_zh = oin.name_en.strip(), oin.name_km.strip(), oin.name_zh.strip()
            o.price_delta_usd_cents = oin.price_delta_usd_cents
            o.is_default = oin.is_default
            o.is_available = oin.is_available
            o.sort_order = oi
            new_opts.append(o)
        if gin.selection == OptionSelection.SINGLE and sum(o.is_default for o in new_opts) > 1:
            raise HTTPException(422, f"'{gin.name_en}' can have only one default choice.")
        g.options = new_opts
        keep.append(g)
    p.option_groups = keep


# ---------------------------------------------------------------- endpoints
@router.get("/menu")
def admin_menu(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("menu.view"))):
    cats = db.scalars(select(Category).order_by(Category.sort_order, Category.id)).all()
    products = db.scalars(select(Product).order_by(Product.sort_order, Product.id).options(
        selectinload(Product.category), selectinload(Product.option_groups).selectinload(OptionGroup.options))).all()
    return {"categories": [category_out(c) for c in cats], "products": [product_out(p) for p in products]}


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, request: Request, db: Session = Depends(get_db),
                    staff: CurrentStaff = Depends(require("menu.edit"))):
    c = Category(**body.model_dump())
    db.add(c)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A category with this short name already exists.")
    audit(db, "menu.category_created", "category", c.id, staff.id, {"name": c.name_en}, request)
    db.commit()
    return category_out(c)


@router.patch("/categories/{category_id}")
def update_category(category_id: int, body: CategoryUpdate, request: Request, db: Session = Depends(get_db),
                    staff: CurrentStaff = Depends(require("menu.edit"))):
    c = db.get(Category, category_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found.")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(c, k, v)
    audit(db, "menu.category_updated", "category", c.id, staff.id, {k: str(v) for k, v in changes.items()}, request)
    db.commit()
    return category_out(c)


@router.post("/products", status_code=201)
def create_product(body: ProductIn, request: Request, db: Session = Depends(get_db),
                   staff: CurrentStaff = Depends(require("menu.edit"))):
    if not db.get(Category, body.category_id):
        raise HTTPException(422, "Choose a category.")
    data = body.model_dump(exclude={"option_groups"})
    p = Product(**data)
    db.add(p)
    _apply_groups(p, body.option_groups)
    db.flush()
    audit(db, "menu.product_created", "product", p.id, staff.id, {"name": p.name_en, "price": p.price_usd_cents}, request)
    db.commit()
    return product_out(_load_product(db, p.id))


@router.patch("/products/{product_id}")
def update_product(product_id: int, body: ProductUpdate, request: Request, db: Session = Depends(get_db),
                   staff: CurrentStaff = Depends(require("menu.edit"))):
    p = _load_product(db, product_id)
    changes = body.model_dump(exclude_unset=True, exclude={"option_groups"})
    if "category_id" in changes and not db.get(Category, changes["category_id"]):
        raise HTTPException(422, "Choose a category.")
    details = {}
    for k, v in changes.items():
        if getattr(p, k) != v:
            details[k] = {"from": str(getattr(p, k)), "to": str(v)}
            setattr(p, k, v)
    if body.option_groups is not None:
        _apply_groups(p, body.option_groups)
        details["option_groups"] = "updated"
    # Price changes never affect existing orders: orders keep their own price copy
    action = "menu.price_changed" if "price_usd_cents" in details else "menu.product_updated"
    audit(db, action, "product", p.id, staff.id, details, request)
    db.commit()
    return product_out(_load_product(db, p.id))


@router.post("/products/{product_id}/photo")
async def upload_photo(product_id: int, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                       staff: CurrentStaff = Depends(require("menu.edit"))):
    p = _load_product(db, product_id)
    data = await file.read(8 * 1024 * 1024 + 1)
    try:
        from starlette.concurrency import run_in_threadpool

        url = await run_in_threadpool(save_product_photo, data)
    except UploadProblem as e:
        raise HTTPException(422, str(e))
    p.image_url, p.image_credit, p.image_source_url = url, "", ""
    audit(db, "menu.photo_changed", "product", p.id, staff.id, request=request)
    db.commit()
    return product_out(p)
