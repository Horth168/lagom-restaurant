"""Inventory deduction, purchases, adjustments, recipes, expenses and the profit report."""
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Ingredient, Order, Product, StockMovement
from app.models.enums import Role
from app.services import inventory as inv
from app.services import telegram as tg
from scripts.seed_demo import seed


@pytest.fixture
def seeded(SessionTest):
    with SessionTest() as s:
        seed(s, with_staff=False)
    return SessionTest


@pytest.fixture
def staff(make_user, login):
    out = {}
    for role in (Role.OWNER, Role.ADMIN, Role.CASHIER, Role.KITCHEN, Role.INVENTORY):
        make_user(role)
        out[role] = login(f"{role.value.lower()}@test.com")
    return out


def qty(SessionTest, name) -> Decimal:
    with SessionTest() as s:
        return s.scalar(select(Ingredient.quantity).where(Ingredient.name == name))


def _line(SessionTest, name, n=1, opts=()):
    with SessionTest() as s:
        p = s.scalar(select(Product).where(Product.name_en == name))
        g = {grp.name_en: {o.name_en: o.id for o in grp.options} for grp in p.option_groups}
    return {"product_id": p.id, "quantity": n, "option_ids": [g[a][b] for a, b in opts]}


def latte(size="Medium", extras=()):
    return (("Size", size), ("Sugar", "50%"), ("Ice", "Normal ice"), *(("Extras", e) for e in extras))


def sell(client, staff, SessionTest, items, pay=True):
    o = client.post("/api/pos/orders", headers=staff[Role.CASHIER], json={
        "channel": "POS_TAKEAWAY", "items": items, "idempotency_key": uuid.uuid4().hex}).json()
    if pay:
        r = client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=staff[Role.CASHIER], json={"received_minor": 10**6})
        assert r.status_code == 200, r.text
    return o


# ------------------------------------------------------------------ deduction
def test_paid_order_deducts_recipe_scaled_by_size(client, seeded, staff):
    beans, milk, cups = qty(seeded, "Coffee beans"), qty(seeded, "Fresh milk"), qty(seeded, "Plastic cup")
    sell(client, staff, seeded, [_line(seeded, "Iced Latte", 2, latte("Large"))])
    # Large = 1.6x: 18 g beans and 180 ml milk per latte, but still one cup each
    assert beans - qty(seeded, "Coffee beans") == Decimal("57.600")
    assert milk - qty(seeded, "Fresh milk") == Decimal("576.000")
    assert cups - qty(seeded, "Plastic cup") == 2


def test_option_recipe_lines(client, seeded, staff):
    beans, oat, milk = qty(seeded, "Coffee beans"), qty(seeded, "Oat milk"), qty(seeded, "Fresh milk")
    sell(client, staff, seeded, [_line(seeded, "Iced Latte", 1, latte("Small", ["Extra espresso shot", "Oat milk"]))])
    assert beans - qty(seeded, "Coffee beans") == Decimal("27")  # 18 + 9 extra shot
    assert oat - qty(seeded, "Oat milk") == Decimal("180")
    assert milk - qty(seeded, "Fresh milk") == Decimal("180")  # recipe as configured


def test_unpaid_orders_do_not_touch_stock(client, seeded, staff):
    beans = qty(seeded, "Coffee beans")
    sell(client, staff, seeded, [_line(seeded, "Iced Latte", 1, latte())], pay=False)
    assert qty(seeded, "Coffee beans") == beans


def test_deduction_happens_only_once(client, seeded, staff):
    o = sell(client, staff, seeded, [_line(seeded, "Iced Latte", 1, latte())])
    after = qty(seeded, "Coffee beans")
    with seeded() as db:
        order = db.scalar(select(Order).where(Order.public_id == o["public_id"]))
        assert inv.deduct_for_order(db, order) is False
        order.inventory_deducted = False  # even if the flag were lost, the unique key stops a 2nd deduction
        assert inv.deduct_for_order(db, order) is False
        db.commit()
        assert db.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.order_id == order.id)) == 4
    assert qty(seeded, "Coffee beans") == after


def test_cancel_puts_stock_back(client, seeded, staff):
    before = qty(seeded, "Coffee beans")
    o = sell(client, staff, seeded, [_line(seeded, "Iced Latte", 1, latte())])
    assert qty(seeded, "Coffee beans") < before
    client.post(f"/api/admin/orders/{o['public_id']}/cancel", headers=staff[Role.OWNER], json={"reason": "spilled"})
    assert qty(seeded, "Coffee beans") == before


def test_deduct_when_ready_setting(client, seeded, staff):
    client.patch("/api/settings", headers=staff[Role.OWNER], json={"inventory_deduct_on": "READY"})
    before = qty(seeded, "Jasmine rice")
    o = sell(client, staff, seeded, [_line(seeded, "Fried Rice", 1, [("Protein", "Chicken")])])
    assert qty(seeded, "Jasmine rice") == before
    client.post(f"/api/kds/kitchen/orders/{o['public_id']}/ready", headers=staff[Role.KITCHEN])
    assert before - qty(seeded, "Jasmine rice") == 200


def test_low_stock_alert_once(client, seeded, staff, monkeypatch):
    sent = []
    monkeypatch.setattr(tg, "sent_log", sent)
    with seeded() as db:
        mango = db.scalar(select(Ingredient).where(Ingredient.name == "Mango"))
        mango.quantity = Decimal(16)  # alert level is 15
        db.commit()
    sell(client, staff, seeded, [_line(seeded, "Mango Smoothie", 2, [("Size", "Small"), ("Sugar", "50%"), ("Ice", "Normal ice")])])
    sell(client, staff, seeded, [_line(seeded, "Mango Sticky Rice", 1)])
    assert len([m for m in sent if "Low stock" in m and "Mango" in m]) == 1
    ings = client.get("/api/admin/inventory/ingredients", headers=staff[Role.INVENTORY]).json()
    assert next(i for i in ings if i["name"] == "Mango")["is_low"] is True
    assert "Mango" in [x["name"] for x in client.get("/api/admin/dashboard", headers=staff[Role.OWNER]).json()["low_stock"]]


# ------------------------------------------------------------------ inventory admin
def test_inventory_permissions(client, seeded, staff):
    assert client.get("/api/admin/inventory/ingredients", headers=staff[Role.CASHIER]).status_code == 403
    assert client.get("/api/admin/inventory/ingredients", headers=staff[Role.INVENTORY]).status_code == 200
    assert client.post("/api/admin/inventory/ingredients", headers=staff[Role.KITCHEN], json={"name": "X", "unit": "g"}).status_code == 403


def test_purchase_adds_stock_and_averages_cost(client, seeded, staff):
    h = staff[Role.INVENTORY]
    ings = {i["name"]: i for i in client.get("/api/admin/inventory/ingredients", headers=h).json()}
    beans = ings["Coffee beans"]
    assert beans["unit_cost_usd_millicents"] == 2500  # $0.025 per gram
    sup = client.post("/api/admin/inventory/suppliers", headers=h, json={"name": "Kampot Coffee Co."}).json()
    r = client.post("/api/admin/inventory/purchases", headers=h, json={
        "supplier_id": sup["id"], "purchased_on": "2026-11-16", "invoice_ref": "INV-77",
        "lines": [{"ingredient_id": beans["id"], "quantity": "1000", "line_total_usd_cents": 3000}]})
    assert r.status_code == 201 and r.json()["total_usd_cents"] == 3000
    after = next(i for i in client.get("/api/admin/inventory/ingredients", headers=h).json() if i["name"] == "Coffee beans")
    assert Decimal(after["quantity"]) == Decimal(beans["quantity"]) + 1000
    assert after["unit_cost_usd_millicents"] == 2583  # (5000 g x 2.5c + 1000 g x 3c) / 6000 g
    assert client.get("/api/admin/inventory/purchases", headers=h).json()[0]["supplier"] == "Kampot Coffee Co."


def test_count_correction_and_waste(client, seeded, staff):
    h = staff[Role.INVENTORY]
    milk = next(i for i in client.get("/api/admin/inventory/ingredients", headers=h).json() if i["name"] == "Fresh milk")
    r = client.post("/api/admin/inventory/adjustments", headers=h, json={
        "ingredient_id": milk["id"], "counted_quantity": "19500", "note": "Weekly count"})
    assert r.json()["ingredient"]["quantity"] == "19500.000"
    r = client.post("/api/admin/inventory/adjustments", headers=h, json={
        "ingredient_id": milk["id"], "kind": "WASTE", "change": "500", "note": "Spoiled"})
    assert r.json()["ingredient"]["quantity"] == "19000.000"
    moves = client.get(f"/api/admin/inventory/ingredients/{milk['id']}/movements", headers=h).json()
    assert [m["kind"] for m in moves[:2]] == ["WASTE", "ADJUSTMENT"]
    assert client.post("/api/admin/inventory/adjustments", headers=h, json={
        "ingredient_id": milk["id"], "note": "nothing"}).status_code == 422


def test_recipe_editor(client, seeded, staff):
    h = staff[Role.INVENTORY]
    pid = _line(seeded, "Americano")["product_id"]
    ings = {i["name"]: i["id"] for i in client.get("/api/admin/inventory/ingredients", headers=h).json()}
    r = client.put(f"/api/admin/inventory/recipes/{pid}", headers=h, json=[
        {"ingredient_id": ings["Coffee beans"], "quantity": "20"},
        {"ingredient_id": ings["Plastic cup"], "quantity": "1", "scales_with_size": False}])
    assert r.status_code == 200 and r.json()["base_cost_usd_cents"] == 56  # 20 g x 2.5c + 1 cup x 6c
    dup = client.put(f"/api/admin/inventory/recipes/{pid}", headers=h, json=[
        {"ingredient_id": ings["Straw"], "quantity": "1"}, {"ingredient_id": ings["Straw"], "quantity": "2"}])
    assert dup.status_code == 422


# ------------------------------------------------------------------ finance
def test_expenses_keep_their_exchange_rate(client, seeded, staff):
    h = staff[Role.OWNER]
    r = client.post("/api/admin/finance/expenses", headers=h, json={
        "category": "ELECTRICITY", "spent_on": "2026-11-16", "description": "EDC bill", "currency": "KHR", "amount_minor": 410000})
    assert r.json()["amount_usd_cents"] == 10000  # 410,000 riel at 4,100 = $100
    client.patch("/api/settings", headers=h, json={"khr_per_usd": "4000"})
    rows = client.get("/api/admin/finance/expenses?period=custom&start=2026-11-01&end=2026-11-30", headers=h).json()
    assert rows[0]["amount_usd_cents"] == 10000 and rows[0]["khr_per_usd"] == "4100.00"
    assert client.post("/api/admin/finance/expenses", headers=staff[Role.CASHIER], json={
        "category": "RENT", "spent_on": "2026-11-16", "description": "x", "amount_minor": 1}).status_code == 403


def test_profit_report(client, seeded, staff):
    h = staff[Role.OWNER]
    a = sell(client, staff, seeded, [_line(seeded, "Iced Latte", 2, latte("Medium"))])  # $6.50
    sell(client, staff, seeded, [_line(seeded, "Fried Rice", 1, [("Protein", "Chicken")])])  # $4.50
    c = sell(client, staff, seeded, [_line(seeded, "Americano", 1, latte("Small")[:3])])  # $2.25 then refunded
    client.post(f"/api/admin/orders/{c['public_id']}/cancel", headers=h, json={"reason": "wrong order"})
    ref = client.get("/api/admin/refunds", headers=h).json()[0]
    client.post(f"/api/admin/refunds/{ref['id']}/complete", headers=h, json={"reference": "cash"})
    client.post("/api/admin/finance/expenses", headers=h, json={
        "category": "RENT", "spent_on": a["business_date"], "description": "Shop rent", "amount_minor": 30000})

    r = client.get("/api/admin/finance/report?period=today", headers=h).json()
    assert r["net_sales_usd_cents"] == 1100  # the cancelled order is not a sale
    assert r["refunds_usd_cents"] == 225
    # COGS: 2 medium lattes: beans 46.8 g x 2.5c, milk 468 ml x 0.18c, 2 cups x 6c, 2 straws x 1c
    #       fried rice: rice 200 g x 0.12c, egg 12c, chicken 120 g x 0.6c
    latte_cost = 46.8 * 2.5 + 468 * 0.18 + 2 * 6 + 2 * 1
    rice_cost = 200 * 0.12 + 12 + 120 * 0.6
    assert abs(r["cogs_usd_cents"] - (latte_cost + rice_cost)) <= 2
    assert r["expenses_by_category"]["RENT"] == 30000
    assert r["gross_profit_usd_cents"] == 1100 - 225 - r["cogs_usd_cents"]
    assert r["net_profit_usd_cents"] == r["gross_profit_usd_cents"] - 30000
    assert r["sales_by_method"]["cash"] == 1100
    assert r["periods"][0]["net_sales"] == 1100

    xlsx = client.get("/api/admin/finance/report.xlsx?period=today", headers=h)
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    pdf = client.get("/api/admin/finance/report.pdf?period=year", headers=h)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert client.get("/api/admin/finance/report", headers=staff[Role.INVENTORY]).status_code == 403


def test_report_groups(client, seeded, staff):
    h = staff[Role.OWNER]
    for g in ("day", "week", "month", "quarter", "year"):
        assert client.get(f"/api/admin/finance/report?period=year&group={g}", headers=h).json()["period"]["group"] == g
    assert client.get("/api/admin/finance/report?period=last_month", headers=h).status_code == 200
