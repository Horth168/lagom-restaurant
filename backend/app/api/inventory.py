"""Admin: ingredients, suppliers, purchases, stock adjustments, movements, recipes."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.deps import CurrentStaff, require
from app.db import get_db
from app.models import Ingredient, Option, OptionGroup, Product, Purchase, PurchaseLine, RecipeItem, StockMovement, Supplier
from app.models.enums import StockMovementKind
from app.services import inventory as inv
from app.services.audit import audit

router = APIRouter(prefix="/api/admin/inventory", tags=["inventory"])



# ---------------------------------------------------------------- shapes
class IngredientIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=20)
    low_stock_threshold: Decimal = Field(Decimal(0), ge=0, max_digits=12, decimal_places=3)
    unit_cost_usd_millicents: int = Field(0, ge=0, le=100_000_000)  # 1 US cent = 1,000 millicents
    supplier_id: int | None = None
    is_active: bool = True


class IngredientUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=160)
    unit: str | None = Field(None, min_length=1, max_length=20)
    low_stock_threshold: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=3)
    unit_cost_usd_millicents: int | None = Field(None, ge=0, le=100_000_000)
    supplier_id: int | None = None
    is_active: bool | None = None


class SupplierIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    phone: str = Field("", max_length=40)
    contact_name: str = Field("", max_length=120)
    notes: str = Field("", max_length=1000)
    is_active: bool = True


class PurchaseLineIn(BaseModel):
    ingredient_id: int
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    line_total_usd_cents: int = Field(ge=0, le=100_000_000)


class PurchaseIn(BaseModel):
    supplier_id: int | None = None
    purchased_on: date
    invoice_ref: str = Field("", max_length=80)
    notes: str = Field("", max_length=1000)
    lines: list[PurchaseLineIn] = Field(min_length=1, max_length=100)


class AdjustIn(BaseModel):
    ingredient_id: int
    kind: StockMovementKind = StockMovementKind.ADJUSTMENT
    change: Decimal | None = Field(None, gt=Decimal("-1000000"), lt=Decimal("1000000"), max_digits=12,
                                   decimal_places=3)  # +/- amount, or…
    counted_quantity: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=3)  # …what is really on the shelf
    note: str = Field(min_length=1, max_length=255)


class RecipeLineIn(BaseModel):
    ingredient_id: int
    option_id: int | None = None
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    scales_with_size: bool = True


# ---------------------------------------------------------------- helpers
def ingredient_out(i: Ingredient) -> dict:
    return {"id": i.id, "name": i.name, "unit": i.unit, "quantity": str(i.quantity),
            "low_stock_threshold": str(i.low_stock_threshold), "unit_cost_usd_millicents": i.unit_cost_usd_millicents,
            "stock_value_usd_cents": int(Decimal(max(i.quantity, 0)) * i.unit_cost_usd_millicents / 1000),
            "supplier_id": i.supplier_id, "supplier": i.supplier.name if i.supplier else None,
            "is_active": i.is_active, "is_low": i.is_low}


def supplier_out(s: Supplier) -> dict:
    return {"id": s.id, "name": s.name, "phone": s.phone, "contact_name": s.contact_name, "notes": s.notes,
            "is_active": s.is_active}


def _ingredient(db: Session, ingredient_id: int, lock: bool = False) -> Ingredient:
    i = db.get(Ingredient, ingredient_id, with_for_update=lock)
    if not i:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ingredient not found.")
    return i


# ---------------------------------------------------------------- ingredients
@router.get("/ingredients")
def list_ingredients(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("inventory.view"))):
    rows = db.scalars(select(Ingredient).options(selectinload(Ingredient.supplier)).order_by(Ingredient.name)).all()
    return [ingredient_out(i) for i in rows]


@router.post("/ingredients", status_code=201)
def create_ingredient(body: IngredientIn, request: Request, db: Session = Depends(get_db),
                      staff: CurrentStaff = Depends(require("inventory.edit"))):
    i = Ingredient(**body.model_dump(), quantity=Decimal(0))
    db.add(i)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An ingredient with this name already exists.")
    audit(db, "inventory.ingredient_created", "ingredient", i.id, staff.id, {"name": i.name}, request)
    db.commit()
    return ingredient_out(i)


@router.patch("/ingredients/{ingredient_id}")
def update_ingredient(ingredient_id: int, body: IngredientUpdate, request: Request, db: Session = Depends(get_db),
                      staff: CurrentStaff = Depends(require("inventory.edit"))):
    i = _ingredient(db, ingredient_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(i, k, v)
    inv.check_low_stock(db, i)
    audit(db, "inventory.ingredient_updated", "ingredient", i.id, staff.id, {k: str(v) for k, v in changes.items()}, request)
    db.commit()
    return ingredient_out(i)


@router.get("/ingredients/{ingredient_id}/movements")
def movements(ingredient_id: int, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
              _: CurrentStaff = Depends(require("inventory.view"))):
    _ingredient(db, ingredient_id)
    rows = db.scalars(select(StockMovement).where(StockMovement.ingredient_id == ingredient_id)
                      .order_by(StockMovement.id.desc()).limit(limit)).all()
    return [{"id": m.id, "kind": m.kind, "change": str(m.change), "balance_after": str(m.balance_after),
             "unit_cost_usd_millicents": m.unit_cost_usd_millicents, "order_id": m.order_id, "purchase_id": m.purchase_id,
             "note": m.note, "created_at": m.created_at} for m in rows]


@router.post("/adjustments", status_code=201)
def adjust_stock(body: AdjustIn, request: Request, db: Session = Depends(get_db),
                 staff: CurrentStaff = Depends(require("inventory.edit"))):
    """Correct the count (counted_quantity) or record waste / a +/- change."""
    if body.kind not in (StockMovementKind.ADJUSTMENT, StockMovementKind.WASTE):
        raise HTTPException(422, "Use ADJUSTMENT or WASTE.")
    i = _ingredient(db, body.ingredient_id, lock=True)
    if body.counted_quantity is not None:
        change = body.counted_quantity - Decimal(i.quantity)
    elif body.change is not None:
        change = body.change
    else:
        raise HTTPException(422, "Give a change or the counted quantity.")
    if body.kind == StockMovementKind.WASTE and change > 0:
        change = -change  # waste always reduces stock
    if change == 0:
        raise HTTPException(422, "Nothing to change.")
    m = inv.adjust(db, i, change=change, kind=body.kind, user_id=staff.id, note=body.note)
    audit(db, "inventory.adjusted", "ingredient", i.id, staff.id, {"kind": body.kind, "change": str(change), "note": body.note}, request)
    db.commit()
    return {"ingredient": ingredient_out(i), "movement_id": m.id}


# ---------------------------------------------------------------- suppliers
@router.get("/suppliers")
def list_suppliers(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("inventory.view"))):
    return [supplier_out(s) for s in db.scalars(select(Supplier).order_by(Supplier.name))]


@router.post("/suppliers", status_code=201)
def create_supplier(body: SupplierIn, request: Request, db: Session = Depends(get_db),
                    staff: CurrentStaff = Depends(require("inventory.edit"))):
    s = Supplier(**body.model_dump())
    db.add(s)
    db.flush()
    audit(db, "inventory.supplier_created", "supplier", s.id, staff.id, {"name": s.name}, request)
    db.commit()
    return supplier_out(s)


@router.patch("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, body: SupplierIn, request: Request, db: Session = Depends(get_db),
                    staff: CurrentStaff = Depends(require("inventory.edit"))):
    s = db.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found.")
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    audit(db, "inventory.supplier_updated", "supplier", s.id, staff.id, request=request)
    db.commit()
    return supplier_out(s)


# ---------------------------------------------------------------- purchases
@router.get("/purchases")
def list_purchases(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("inventory.view"))):
    rows = db.scalars(select(Purchase).options(selectinload(Purchase.lines).selectinload(PurchaseLine.ingredient),
                                               selectinload(Purchase.supplier))
                      .order_by(Purchase.purchased_on.desc(), Purchase.id.desc()).limit(100)).all()
    return [{"id": p.id, "purchased_on": p.purchased_on, "supplier": p.supplier.name if p.supplier else None,
             "total_usd_cents": p.total_usd_cents, "invoice_ref": p.invoice_ref, "notes": p.notes,
             "lines": [{"ingredient": ln.ingredient.name, "unit": ln.ingredient.unit, "quantity": str(ln.quantity),
                        "line_total_usd_cents": ln.line_total_usd_cents} for ln in p.lines]} for p in rows]


@router.post("/purchases", status_code=201)
def record_purchase(body: PurchaseIn, request: Request, db: Session = Depends(get_db),
                    staff: CurrentStaff = Depends(require("inventory.edit"))):
    """Stock bought from a supplier: adds the quantities and updates the average cost."""
    if body.supplier_id and not db.get(Supplier, body.supplier_id):
        raise HTTPException(422, "Supplier not found.")
    p = Purchase(supplier_id=body.supplier_id, purchased_on=body.purchased_on, invoice_ref=body.invoice_ref,
                 notes=body.notes, total_usd_cents=sum(ln.line_total_usd_cents for ln in body.lines),
                 created_by_user_id=staff.id)
    db.add(p)
    db.flush()
    for ln in body.lines:
        ing = _ingredient(db, ln.ingredient_id, lock=True)
        db.add(PurchaseLine(purchase_id=p.id, ingredient_id=ing.id, quantity=ln.quantity,
                            line_total_usd_cents=ln.line_total_usd_cents))
        inv.receive_purchase_line(db, ing, ln.quantity, ln.line_total_usd_cents, purchase_id=p.id, user_id=staff.id)
    audit(db, "inventory.purchase", "purchase", p.id, staff.id, {"total_usd_cents": p.total_usd_cents}, request)
    db.commit()
    return {"id": p.id, "total_usd_cents": p.total_usd_cents}


# ---------------------------------------------------------------- recipes
@router.get("/recipes/{product_id}")
def get_recipe(product_id: int, db: Session = Depends(get_db), _: CurrentStaff = Depends(require("inventory.view"))):
    p = db.scalar(select(Product).where(Product.id == product_id).options(
        selectinload(Product.option_groups).selectinload(OptionGroup.options)))
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
    lines = db.scalars(select(RecipeItem).where(RecipeItem.product_id == product_id).options(selectinload(RecipeItem.ingredient))).all()
    cost = sum(Decimal(r.quantity) * r.ingredient.unit_cost_usd_millicents for r in lines if r.option_id is None) / 1000
    return {
        "product": {"id": p.id, "name": p.name_en, "price_usd_cents": p.price_usd_cents},
        "options": [{"id": o.id, "name": f"{g.name_en}: {o.name_en}", "recipe_multiplier": str(o.recipe_multiplier)}
                    for g in p.option_groups for o in g.options],
        "lines": [{"ingredient_id": r.ingredient_id, "ingredient": r.ingredient.name, "unit": r.ingredient.unit,
                   "option_id": r.option_id, "quantity": str(r.quantity),
                   "scales_with_size": r.scales_with_size} for r in lines],
        "base_cost_usd_cents": int(cost),
    }


@router.put("/recipes/{product_id}")
def set_recipe(product_id: int, body: list[RecipeLineIn], request: Request, db: Session = Depends(get_db),
               staff: CurrentStaff = Depends(require("inventory.edit"))):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")
    option_ids = {o.id for g in p.option_groups for o in g.options}
    seen = set()
    for ln in body:
        if not db.get(Ingredient, ln.ingredient_id):
            raise HTTPException(422, "Unknown ingredient.")
        if ln.option_id is not None and ln.option_id not in option_ids:
            raise HTTPException(422, "That option does not belong to this product.")
        if (ln.ingredient_id, ln.option_id) in seen:
            raise HTTPException(422, "The same ingredient is listed twice.")
        seen.add((ln.ingredient_id, ln.option_id))
    for r in db.scalars(select(RecipeItem).where(RecipeItem.product_id == product_id)):
        db.delete(r)
    db.flush()
    for ln in body:
        db.add(RecipeItem(product_id=product_id, ingredient_id=ln.ingredient_id, option_id=ln.option_id,
                          quantity=ln.quantity, scales_with_size=ln.scales_with_size))
    audit(db, "inventory.recipe_changed", "product", product_id, staff.id, {"lines": len(body)}, request)
    db.commit()
    return get_recipe(product_id, db, staff)


class MultiplierIn(BaseModel):
    recipe_multiplier: Decimal = Field(gt=0, le=10, max_digits=6, decimal_places=3)


@router.patch("/options/{option_id}/multiplier")
def set_multiplier(option_id: int, body: MultiplierIn, db: Session = Depends(get_db),
                   staff: CurrentStaff = Depends(require("inventory.edit"))):
    """E.g. Large size uses 1.6x the recipe."""
    o = db.get(Option, option_id)
    if not o:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Option not found.")
    o.recipe_multiplier = body.recipe_multiplier
    db.commit()
    return {"id": o.id, "recipe_multiplier": str(o.recipe_multiplier)}
