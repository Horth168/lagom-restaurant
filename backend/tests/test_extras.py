# ruff: noqa: F811  (pytest fixtures shared from test_telegram are used as arguments)
"""Shifts, waiter calls, reviews, deals, sold-out, stamp card, backup and busiest hours."""
import io
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.models import Category, Ingredient, LoyaltyCard, Order, Product
from app.models.base import utcnow
from app.models.enums import Role
from app.services import notifications
from app.services.payments import expire_due_orders
from app.services.realtime import hub
from tests.test_telegram import init_data, rice, sent, seeded, staff, table_qr  # noqa: F401  (fixtures)


def line(SessionTest, name, qty=1):
    """A cart line for a dish with its default (required) options."""
    with SessionTest() as s:
        p = s.scalar(select(Product).where(Product.name_en == name))
        opts = []
        for g in p.option_groups:
            if g.is_required or g.min_select:
                opts.append(next((o for o in g.options if o.is_default), g.options[0]).id)
    return {"product_id": p.id, "quantity": qty, "option_ids": opts}


def table_session(client, SessionTest):
    return {"X-Table-Session": client.post(f"/api/public/tables/{table_qr(SessionTest)}/session", json={}).json()["session_token"]}


def checkout(client, h, items, **extra):
    return client.post("/api/public/orders", headers=h,
                       json={"items": items, "idempotency_key": uuid.uuid4().hex, **extra})


def cash_paid(client, staff, h, items):
    o = checkout(client, h, items).json()
    client.post(f"/api/public/orders/{o['public_id']}/pay", headers=h, json={"method": "cash", "currency": "USD"})
    client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=staff[Role.CASHIER], json={"received_minor": 100000})
    return o


# ================================================================== B. cash drawer shifts
def test_shift_expected_cash_and_difference(client, seeded, staff, sent):
    c = staff[Role.CASHIER]
    assert client.get("/api/pos/shift", headers=c).json() is None
    assert client.post("/api/pos/shift/open", headers=c, json={"opening_usd_cents": 5000}).status_code == 201
    assert client.post("/api/pos/shift/open", headers=c, json={}).status_code == 409  # only one drawer
    h = table_session(client, seeded)
    cash_paid(client, staff, h, [rice(seeded)])  # $4.50 cash
    cash_paid(client, staff, h, [rice(seeded)])
    live = client.get("/api/pos/shift", headers=c).json()
    assert live["expected_usd_cents"] == 5000 + 900 and live["cash_orders"] == 2
    r = client.post("/api/pos/shift/close", headers=c, json={"counted_usd_cents": 5800, "note": "short"}).json()
    assert r["difference_usd_cents"] == -100 and r["status"] == "CLOSED"
    assert any("Shift closed" in m and "Difference: -$1.00" in m for m in sent)
    assert client.post("/api/pos/shift/close", headers=c, json={"counted_usd_cents": 0}).status_code == 409
    assert client.get("/api/admin/shifts", headers=staff[Role.OWNER]).json()[0]["counted_usd_cents"] == 5800
    assert client.get("/api/pos/shift", headers=staff[Role.KITCHEN]).status_code == 403


def test_cash_refund_lowers_expected_cash(client, seeded, staff, sent):
    c, owner = staff[Role.CASHIER], staff[Role.OWNER]
    client.post("/api/pos/shift/open", headers=c, json={"opening_usd_cents": 0})
    o = cash_paid(client, staff, table_session(client, seeded), [rice(seeded)])
    client.post(f"/api/admin/orders/{o['public_id']}/cancel", headers=owner, json={"reason": "Wrong dish"})
    refund = client.get("/api/admin/refunds", headers=owner).json()[0]
    client.post(f"/api/admin/refunds/{refund['id']}/complete", headers=owner, json={"reference": "cash"})
    assert client.get("/api/pos/shift", headers=c).json()["expected_usd_cents"] == 0


# ================================================================== F. waiter / bill
def test_call_waiter_and_request_bill(client, seeded, staff, sent):
    h = table_session(client, seeded)
    hub.sent.clear()
    r = client.post("/api/public/service-requests", headers=h, json={"kind": "bill"})
    assert r.status_code == 201 and r.json()["table"] == "Table 01"
    again = client.post("/api/public/service-requests", headers=h, json={"kind": "bill"}).json()
    assert again["id"] == r.json()["id"]  # pressing twice does not ring twice
    assert any("Table 01" in m and "bill" in m for m in sent)
    assert any(ch == "staff" and msg["type"] == "service" for ch, msg in hub.sent)
    waiting = client.get("/api/admin/service-requests", headers=staff[Role.CASHIER]).json()
    assert [w["kind"] for w in waiting] == ["bill"]
    client.post(f"/api/admin/service-requests/{waiting[0]['id']}/done", headers=staff[Role.CASHIER])
    assert client.get("/api/admin/service-requests", headers=staff[Role.CASHIER]).json() == []
    assert client.get("/api/public/service-requests", headers=h).json() == []


def test_pickup_customers_cannot_call_waiter(client, seeded, sent):
    tok = client.post("/api/public/telegram/session", json={"init_data": init_data()}).json()["session_token"]
    r = client.post("/api/public/service-requests", headers={"X-Table-Session": tok}, json={"kind": "waiter"})
    assert r.status_code == 422


# ================================================================== H. reviews
def test_review_after_ready_once_with_dish_stars(client, seeded, staff, sent):
    h = table_session(client, seeded)
    o = cash_paid(client, staff, h, [rice(seeded)])
    assert client.post(f"/api/public/orders/{o['public_id']}/review", headers=h, json={"stars": 5}).status_code == 409
    client.post(f"/api/kds/kitchen/orders/{o['public_id']}/ready", headers=staff[Role.KITCHEN])
    item_id = client.get(f"/api/public/orders/{o['public_id']}", headers=h).json()["items"][0]["id"]
    r = client.post(f"/api/public/orders/{o['public_id']}/review", headers=h,
                    json={"stars": 2, "comment": "Cold rice", "items": [{"item_id": item_id, "stars": 1}]})
    assert r.status_code == 201
    assert any("2/5" in m and "Cold rice" in m for m in sent)  # low rating alert
    assert client.post(f"/api/public/orders/{o['public_id']}/review", headers=h, json={"stars": 5}).status_code == 409
    other = table_session(client, seeded)
    assert client.get(f"/api/public/orders/{o['public_id']}/review", headers=other).status_code == 404
    data = client.get("/api/admin/reviews", headers=staff[Role.OWNER]).json()
    assert data["count"] == 1 and data["dishes"] == [{"name": "Fried Rice", "average": 1.0, "count": 1}]
    assert data["recent"][0]["comment"] == "Cold rice"


def test_review_rejects_dish_from_another_order(client, seeded, staff, sent):
    h = table_session(client, seeded)
    o = cash_paid(client, staff, h, [rice(seeded)])
    client.post(f"/api/kds/kitchen/orders/{o['public_id']}/ready", headers=staff[Role.KITCHEN])
    r = client.post(f"/api/public/orders/{o['public_id']}/review", headers=h,
                    json={"stars": 4, "items": [{"item_id": 99999, "stars": 5}]})
    assert r.status_code == 422


# ================================================================== J. timed deals
def _coffee_cat(SessionTest):
    with SessionTest() as s:
        return s.scalar(select(Category.id).where(Category.slug == "coffee"))


def test_happy_hour_deal_changes_server_price(client, seeded, staff):
    owner = staff[Role.OWNER]
    r = client.post("/api/admin/deals", headers=owner, json={"name": "Happy hour", "percent": 20,
                                                             "category_id": _coffee_cat(seeded)})
    assert r.status_code == 201
    q = client.post("/api/public/cart/quote", json={"items": [line(seeded, "Iced Latte")]}).json()
    full = q["lines"][0]["deal"]["list_unit_price_usd_cents"]  # price with the default options
    assert q["subtotal_usd_cents"] == round(full * 0.8) and q["lines"][0]["deal"]["percent"] == 20
    latte = next(p for p in client.get("/api/public/menu").json()["products"] if p["name"]["en"] == "Iced Latte")
    assert latte["deal"] == {"name": "Happy hour", "percent": 20}
    # Rice is not coffee: no deal
    assert client.post("/api/public/cart/quote", json={"items": [rice(seeded)]}).json()["lines"][0]["deal"] is None
    # Switched off: full price again
    client.put(f"/api/admin/deals/{r.json()['id']}", headers=owner,
               json={"name": "Happy hour", "percent": 20, "category_id": _coffee_cat(seeded), "is_active": False})
    assert client.post("/api/public/cart/quote", json={"items": [line(seeded, "Iced Latte")]}).json()["subtotal_usd_cents"] == full


def test_deal_time_window_and_validation(client, seeded, staff):
    from app.models import Deal
    from app.services.deals import deal_is_on

    d = Deal(name="x", percent=10, weekdays="01234", start_time="14:00", end_time="17:00", is_active=True)
    mon_3pm = datetime(2026, 11, 16, 15, 0)  # a Monday
    assert deal_is_on(d, mon_3pm) and not deal_is_on(d, mon_3pm.replace(hour=18))
    assert not deal_is_on(d, datetime(2026, 11, 21, 15, 0))  # Saturday
    night = Deal(name="n", percent=10, weekdays="0123456", start_time="22:00", end_time="02:00", is_active=True)
    assert deal_is_on(night, mon_3pm.replace(hour=23)) and deal_is_on(night, mon_3pm.replace(hour=1))
    owner = staff[Role.OWNER]
    assert client.post("/api/admin/deals", headers=owner, json={"name": "x", "percent": 95}).status_code == 422
    assert client.post("/api/admin/deals", headers=owner, json={"name": "x", "percent": 10, "start_time": "25:00"}).status_code == 422
    assert client.post("/api/admin/deals", headers=staff[Role.CASHIER], json={"name": "x", "percent": 10}).status_code == 403


# ================================================================== K. sold out from stock
def test_dish_sold_out_when_ingredient_runs_out(client, seeded, staff):
    with seeded() as s:
        s.add(Ingredient(name="Test beans", unit="g", quantity=Decimal("5")))
        s.flush()
        from app.models import RecipeItem
        latte = s.scalar(select(Product).where(Product.name_en == "Iced Latte"))
        beans = s.scalar(select(Ingredient).where(Ingredient.name == "Test beans"))
        s.add(RecipeItem(product_id=latte.id, ingredient_id=beans.id, quantity=Decimal("18")))
        s.commit()

    def latte_available():
        return next(p for p in client.get("/api/public/menu").json()["products"] if p["name"]["en"] == "Iced Latte")["is_available"]

    assert latte_available() is False
    r = client.post("/api/public/cart/quote", json={"items": [line(seeded, "Iced Latte")]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "sold_out"
    client.patch("/api/settings", headers=staff[Role.OWNER], json={"auto_sold_out": False})
    assert latte_available() is True


# ================================================================== I. Telegram stamp card
@pytest.fixture
def stamp_card(client, seeded, staff, sent):
    client.patch("/api/settings", headers=staff[Role.OWNER], json={
        "loyalty_enabled": True, "loyalty_stamps_needed": 3, "loyalty_category_ids": [_coffee_cat(seeded)]})
    tok = client.post("/api/public/telegram/session", json={"init_data": init_data(555)}).json()["session_token"]
    return {"X-Table-Session": tok}


def test_stamps_earn_a_free_item(client, seeded, staff, sent, stamp_card):
    h = stamp_card
    assert client.get("/api/public/loyalty", headers=h).json() == {
        "enabled": True, "needed": 3, "stamps": 0, "rewards": 0, "category_ids": [_coffee_cat(seeded)]}
    unpaid = checkout(client, h, [line(seeded, "Iced Latte", 3)]).json()
    assert client.get("/api/public/loyalty", headers=h).json()["stamps"] == 0  # no stamps before payment
    client.post(f"/api/public/orders/{unpaid['public_id']}/pay", headers=h, json={"method": "cash", "currency": "USD"})
    client.post(f"/api/admin/orders/{unpaid['public_id']}/cash", headers=staff[Role.CASHIER], json={"received_minor": 10000})
    card = client.get("/api/public/loyalty", headers=h).json()
    assert card["stamps"] == 0 and card["rewards"] == 1
    assert any(m.startswith("to 555:") and "Stamp card" in m and "free item" in m for m in sent)

    # Use it: the cheapest coffee becomes free, rice is not eligible
    cart = [line(seeded, "Iced Latte"), line(seeded, "Khmer Iced Coffee"), rice(seeded)]
    units = [x["unit_price_usd_cents"] for x in client.post("/api/public/cart/quote", json={"items": cart}).json()["lines"]]
    o = checkout(client, h, cart, use_reward=True).json()
    assert o["discount_usd_cents"] == min(units[:2]) and "Khmer Iced Coffee" in o["discount_reason"]
    assert client.get("/api/public/loyalty", headers=h).json()["rewards"] == 0  # reserved
    # Unpaid order expires: the free item comes back
    with seeded() as db:
        db.scalar(select(Order).where(Order.public_id == o["public_id"])).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
        expire_due_orders(db)
    assert client.get("/api/public/loyalty", headers=h).json()["rewards"] == 1


def test_reward_rules(client, seeded, staff, sent, stamp_card):
    h = stamp_card
    r = checkout(client, h, [line(seeded, "Iced Latte")], use_reward=True)
    assert r.status_code == 422  # nothing earned yet
    table = table_session(client, seeded)
    assert client.get("/api/public/loyalty", headers=table).json() == {"enabled": False}  # table QR: no card


def test_cancelling_paid_order_takes_stamps_back(client, seeded, staff, sent, stamp_card):
    h = stamp_card
    o = checkout(client, h, [line(seeded, "Iced Latte", 4)]).json()
    client.post(f"/api/public/orders/{o['public_id']}/pay", headers=h, json={"method": "cash", "currency": "USD"})
    client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=staff[Role.CASHIER], json={"received_minor": 10000})
    assert client.get("/api/public/loyalty", headers=h).json() | {} == {
        "enabled": True, "needed": 3, "stamps": 1, "rewards": 1, "category_ids": [_coffee_cat(seeded)]}
    client.post(f"/api/admin/orders/{o['public_id']}/cancel", headers=staff[Role.OWNER], json={"reason": "Mistake"})
    card = client.get("/api/public/loyalty", headers=h).json()
    assert card["stamps"] == 0 and card["rewards"] == 0
    with seeded() as db:
        assert db.scalar(select(LoyaltyCard)).rewards_used == 0


# ================================================================== C. backup
def test_owner_backup_has_every_table_but_no_secrets(client, seeded, staff, sent):
    owner = staff[Role.OWNER]
    client.post("/api/admin/finance/expenses", headers=owner, json={
        "category": "OTHER", "spent_on": "2026-11-16", "description": "=HYPERLINK(\"x\")", "currency": "USD", "amount_minor": 1})
    r = client.get("/api/admin/backup.xlsx", headers=owner)
    assert r.status_code == 200 and "lagom-backup-" in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert {"orders", "products", "users", "expenses", "cash_shifts", "loyalty_cards"} <= set(wb.sheetnames)
    users_header = [c.value for c in next(wb["users"].iter_rows(max_row=1))]
    assert "password_hash" not in users_header and "email" in users_header
    assert "token" not in [c.value for c in next(wb["table_sessions"].iter_rows(max_row=1))]
    desc = [row for row in wb["expenses"].iter_rows(min_row=2, values_only=True)][0]
    assert any(isinstance(v, str) and v.startswith("=HYPERLINK") for v in desc)
    expense_cell = next(c for c in next(wb["expenses"].iter_rows(min_row=2)) if str(c.value).startswith("="))
    assert expense_cell.data_type == "s"  # stays text, never runs as a formula
    assert client.get("/api/admin/backup.xlsx", headers=staff[Role.CASHIER]).status_code == 403


def test_weekly_backup_reminder_once(client, seeded, sent, SessionTest):
    monday_morning = datetime(2026, 11, 16, 2, 0, tzinfo=timezone.utc)  # 09:00 Phnom Penh: too early
    with SessionTest() as db:
        assert notifications.maybe_send_backup_reminder(db, monday_morning) is False
        assert notifications.maybe_send_backup_reminder(db, monday_morning + timedelta(hours=2)) is True
        assert notifications.maybe_send_backup_reminder(db, monday_morning + timedelta(hours=5)) is False
    assert sum("Weekly backup" in m for m in sent) == 1


# ================================================================== L. busiest hours
def test_busiest_hours(client, seeded, staff, sent):
    cash_paid(client, staff, table_session(client, seeded), [rice(seeded)])
    data = client.get("/api/admin/reports/hours?days=7", headers=staff[Role.OWNER]).json()
    assert data["orders"] == 1 and data["sales_usd_cents"] == 450
    local = utcnow().astimezone(__import__("zoneinfo").ZoneInfo("Asia/Phnom_Penh"))
    assert data["busiest"]["hour"] == local.hour and data["busiest"]["weekday"] == local.weekday()
    assert client.get("/api/admin/reports/hours", headers=staff[Role.KITCHEN]).status_code == 403


# ================================================================== E. photo storage label
def test_settings_report_photo_storage(client, staff):
    assert client.get("/api/settings", headers=staff[Role.OWNER]).json()["integrations"]["photo_storage"] == "disk"





def test_fully_free_order_goes_straight_to_kitchen(client, seeded, staff, sent, stamp_card):
    h = stamp_card
    o = checkout(client, h, [line(seeded, "Iced Latte", 3)]).json()
    client.post(f"/api/public/orders/{o['public_id']}/pay", headers=h, json={"method": "cash", "currency": "USD"})
    client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=staff[Role.CASHIER], json={"received_minor": 10000})
    free = checkout(client, h, [line(seeded, "Iced Latte")], use_reward=True).json()
    assert free["total_usd_cents"] == 0 and free["status"] == "PAID"  # no payment step
    assert free["payment"]["method"] == "free"
    kitchen = client.get("/api/kds/drinks", headers=staff[Role.OWNER]).json()["active"]
    assert any(k["public_id"] == free["public_id"] for k in kitchen)
    card = client.get("/api/public/loyalty", headers=h).json()
    assert card["rewards"] == 0 and card["stamps"] == 0  # the free coffee earns no stamp
