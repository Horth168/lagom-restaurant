"""Telegram stamp card: every N eligible items paid in the Mini App earn one free item.

* Stamps are given only when an order is really paid (never for unpaid orders).
* A free item is "reserved" when the customer uses it at checkout; if that order
  expires or is cancelled, the free item goes back on the card.
* Cancelling a paid order also takes back the stamps it earned.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LoyaltyCard, Order, Product, TableSession
from app.models.enums import OrderChannel
from app.services import app_settings

log = logging.getLogger("lagom.loyalty")


def enabled(db: Session) -> bool:
    return bool(app_settings.get_setting(db, "loyalty_enabled"))


def needed(db: Session) -> int:
    return int(app_settings.get_setting(db, "loyalty_stamps_needed"))


def eligible_category_ids(db: Session) -> set[int]:
    return set(app_settings.get_setting(db, "loyalty_category_ids"))


def card_for(db: Session, telegram_user_id: str, create: bool = False) -> LoyaltyCard | None:
    card = db.scalar(select(LoyaltyCard).where(LoyaltyCard.telegram_user_id == telegram_user_id))
    if card is None and create:
        card = LoyaltyCard(telegram_user_id=telegram_user_id, stamps=0, rewards=0, rewards_used=0)
        db.add(card)
        db.flush()
    return card


def _telegram_id(db: Session, order: Order) -> str | None:
    if order.channel != OrderChannel.TELEGRAM or not order.table_session_id:
        return None
    s = db.get(TableSession, order.table_session_id)
    return s.telegram_user_id if s else None


def free_item_discount(db: Session, priced_lines) -> tuple[int, str]:
    """The cheapest eligible item in the cart becomes free. Returns (cents, dish name)."""
    cats = eligible_category_ids(db)
    units = [(line.unit_price_usd_cents, line.product.name_en) for line in priced_lines
             if line.product.category_id in cats]
    return min(units, default=(0, ""))


def eligible_quantity(db: Session, order: Order) -> int:
    cats = eligible_category_ids(db)
    ids = {i.product_id for i in order.items if i.product_id}
    cat_of = dict(db.execute(select(Product.id, Product.category_id).where(Product.id.in_(ids))).tuples().all()) if ids else {}
    return sum(i.quantity for i in order.items if cat_of.get(i.product_id) in cats)


def on_paid(db: Session, order: Order) -> None:
    tg_id = _telegram_id(db, order)
    if not tg_id or not enabled(db) or order.loyalty_stamps_given:
        return
    earned = eligible_quantity(db, order) - (1 if order.loyalty_reward_used else 0)  # the free item earns nothing
    if earned <= 0:
        return
    card = card_for(db, tg_id, create=True)
    n = needed(db)
    card.stamps += earned
    while card.stamps >= n:
        card.stamps -= n
        card.rewards += 1
    order.loyalty_stamps_given = earned


def give_back(db: Session, order: Order, was_paid: bool) -> None:
    """Order expired or cancelled: return a reserved free item; take back earned stamps."""
    tg_id = _telegram_id(db, order)
    if not tg_id:
        return
    card = card_for(db, tg_id)
    if card is None:
        return
    if order.loyalty_reward_used:
        card.rewards += 1
        card.rewards_used = max(0, card.rewards_used - 1)
        order.loyalty_reward_used = False
    if was_paid and order.loyalty_stamps_given:
        n = needed(db)
        card.stamps -= order.loyalty_stamps_given
        while card.stamps < 0 and card.rewards > 0:
            card.rewards -= 1
            card.stamps += n
        card.stamps = max(0, card.stamps)
        order.loyalty_stamps_given = 0


def summary(db: Session, telegram_user_id: str | None) -> dict:
    if not telegram_user_id or not enabled(db):
        return {"enabled": False}
    card = card_for(db, telegram_user_id)
    return {"enabled": True, "needed": needed(db), "stamps": card.stamps if card else 0,
            "rewards": card.rewards if card else 0, "category_ids": sorted(eligible_category_ids(db))}


STAMP_TEXT = {
    "en": ("⭐ Stamp card: {s}/{n}", "🎁 You have {r} free item(s) ready - tick \"Use my free item\" next time."),
    "km": ("⭐ កាតត្រា: {s}/{n}", "🎁 អ្នកមាន {r} មុខឥតគិតថ្លៃ - ធីក \"ប្រើមុខឥតគិតថ្លៃ\" លើកក្រោយ។"),
    "zh": ("⭐ 集章卡：{s}/{n}", "🎁 您有 {r} 份免费商品 - 下次勾选“使用免费商品”。"),
}


def customer_line(db: Session, order: Order, session: TableSession) -> str:
    """Extra lines for the customer's "payment received" Telegram message."""
    if not enabled(db) or not session.telegram_user_id:
        return ""
    card = card_for(db, session.telegram_user_id)
    if card is None:
        return ""
    stamps, free = STAMP_TEXT.get(session.language, STAMP_TEXT["en"])
    out = "\n" + stamps.format(s=card.stamps, n=needed(db))
    if card.rewards:
        out += "\n" + free.format(r=card.rewards)
    return out


def _paid_listener(db: Session, order: Order) -> None:
    on_paid(db, order)


def register() -> None:
    from app.services import orders as order_service

    if _paid_listener not in order_service.paid_listeners:
        order_service.paid_listeners.insert(0, _paid_listener)  # before the customer's "paid" message


register()
