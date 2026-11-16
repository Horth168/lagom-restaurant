"""Customer-facing endpoints (no login). Used by the QR self-ordering app."""
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.rate_limit import rate_limit
from app.db import get_db
from app.models import Category, DiningTable, OptionGroup, Product, Promotion, TableSession
from app.models.base import utcnow
from app.services import app_settings
from app.services.pricing import CartIn, PricingError, price_cart

router = APIRouter(prefix="/api/public", tags=["customer"])

SESSION_IDLE_HOURS = 12  # a phone's table session is recoverable for this long


def _tr(obj, field: str) -> dict:
    return {lang: getattr(obj, f"{field}_{lang}") or getattr(obj, f"{field}_en") for lang in ("en", "km", "zh")}


# ---------------------------------------------------------------- menu
@router.get("/menu")
def menu(response: Response, db: Session = Depends(get_db)):
    """Everything the menu screen needs, in all three languages."""
    categories = db.scalars(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order, Category.id)
    ).all()
    products = db.scalars(
        select(Product)
        .join(Category)
        .where(Product.is_archived.is_(False), Category.is_active.is_(True))
        .order_by(Product.sort_order, Product.id)
        .options(
            selectinload(Product.category),
            selectinload(Product.option_groups).selectinload(OptionGroup.options),
        )
    ).all()
    promos = db.scalars(
        select(Promotion).where(Promotion.is_active.is_(True)).order_by(Promotion.sort_order, Promotion.id)
    ).all()
    response.headers["Cache-Control"] = "public, max-age=30"
    return {
        "categories": [{"id": c.id, "slug": c.slug, "name": _tr(c, "name")} for c in categories],
        "products": [
            {
                "id": p.id,
                "category_id": p.category_id,
                "name": _tr(p, "name"),
                "description": _tr(p, "description"),
                "image_url": p.image_url,
                "price_usd_cents": p.price_usd_cents,
                "prep_minutes": p.prep_minutes,
                "is_available": p.is_available,
                "is_featured": p.is_featured,
                "is_best_seller": p.is_best_seller,
                "allow_special_instructions": p.allow_special_instructions,
                "station": p.effective_station,
                "option_groups": [
                    {
                        "id": g.id,
                        "name": _tr(g, "name"),
                        "selection": g.selection,
                        "is_required": g.is_required,
                        "min_select": max(g.min_select, 1 if g.is_required else 0),
                        "max_select": 1 if g.selection == "SINGLE" else g.max_select,
                        "options": [
                            {
                                "id": o.id,
                                "name": _tr(o, "name"),
                                "price_delta_usd_cents": o.price_delta_usd_cents,
                                "is_default": o.is_default,
                                "is_available": o.is_available,
                            }
                            for o in g.options
                        ],
                    }
                    for g in p.option_groups
                ],
            }
            for p in products
        ],
        "promotions": [
            {"id": pr.id, "title": _tr(pr, "title"), "subtitle": _tr(pr, "subtitle"),
             "image_url": pr.image_url, "product_id": pr.product_id}
            for pr in promos
        ],
    }


# ---------------------------------------------------------------- table sessions
class SessionIn(BaseModel):
    # The token this phone saved last time (to recover the session), if any
    previous_session_token: str | None = Field(None, max_length=64)
    language: str = Field("en", pattern="^(en|km|zh)$")


def _session_out(s: TableSession) -> dict:
    return {"session_token": s.token, "table": {"label": s.table.label, "area": s.table.area}, "language": s.language}


@router.post("/tables/{qr_token}/session", dependencies=[Depends(rate_limit("table-session", 30))])
def open_table_session(qr_token: str, body: SessionIn, db: Session = Depends(get_db)):
    """Called when a phone opens a table QR link. Returns this phone's private session token."""
    table = db.scalar(select(DiningTable).where(DiningTable.qr_token == qr_token))
    if not table or not table.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This QR code is not valid. Please ask our staff for help.")

    now = utcnow()
    if body.previous_session_token:
        prev = db.scalar(select(TableSession).where(TableSession.token == body.previous_session_token))
        if (prev and prev.table_id == table.id and prev.closed_at is None
                and now - prev.last_seen_at < timedelta(hours=SESSION_IDLE_HOURS)):
            prev.last_seen_at = now
            db.commit()
            return _session_out(prev)

    session = TableSession(table_id=table.id, language=body.language)
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_out(session)


def current_table_session(
    x_table_session: str | None = Header(None),
    db: Session = Depends(get_db),
) -> TableSession:
    """Dependency for endpoints that act on behalf of a seated customer."""
    if not x_table_session:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please scan the QR code on your table.")
    s = db.scalar(select(TableSession).where(TableSession.token == x_table_session))
    if not s or s.closed_at is not None or not s.table.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your table session has ended. Please scan the QR code again.")
    if utcnow() - s.last_seen_at > timedelta(hours=SESSION_IDLE_HOURS):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your table session has expired. Please scan the QR code again.")
    return s


@router.get("/session")
def read_session(s: TableSession = Depends(current_table_session)):
    return _session_out(s)


# ---------------------------------------------------------------- cart quote
@router.post("/cart/quote", dependencies=[Depends(rate_limit("cart-quote", 120))])
def quote(cart: CartIn, db: Session = Depends(get_db)):
    """Price a cart on the server. The app shows these numbers, never its own."""
    try:
        priced = price_cart(db, cart)
    except PricingError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"message": e.message, "line": e.line, "code": e.code})
    display = app_settings.get_setting(db, "display_currency")
    return {
        "lines": [
            {
                "product_id": line.product.id,
                "quantity": line.quantity,
                "unit_price_usd_cents": line.unit_price_usd_cents,
                "line_total_usd_cents": line.line_total_usd_cents,
                "options": line.option_snapshot,
                "special_instructions": line.special_instructions,
            }
            for line in priced.lines
        ],
        "subtotal_usd_cents": priced.subtotal_usd_cents,
        "subtotal_khr": priced.subtotal_khr,
        "khr_per_usd": str(priced.khr_per_usd),
        "display_currency": display,
        "estimated_minutes": priced.estimated_minutes,
    }
