"""Admin menu, photos, orders, cancellations/refunds, dashboard and POS."""
import io
import uuid
from datetime import timedelta

import pytest
from PIL import Image
from sqlalchemy import select

from app.config import get_settings
from app.models import AuditLog, DiningTable, Order, Product
from app.models.enums import Role
from app.services import telegram as tg
from scripts.seed_demo import seed
from tests.test_khqr_payments import TEMPLATE


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


def _pid(SessionTest, name):
    with SessionTest() as s:
        return s.scalar(select(Product.id).where(Product.name_en == name))


def _line(SessionTest, name, qty=1, opts=()):
    with SessionTest() as s:
        p = s.scalar(select(Product).where(Product.name_en == name))
        g = {grp.name_en: {o.name_en: o.id for o in grp.options} for grp in p.option_groups}
    return {"product_id": p.id, "quantity": qty, "option_ids": [g[a][b] for a, b in opts]}


LATTE = (("Size", "Medium"), ("Sugar", "50%"), ("Ice", "Normal ice"))


def _pos_order(client, h, SessionTest, **extra):
    body = {"channel": "POS_TAKEAWAY", "items": [_line(SessionTest, "Iced Latte", 2, LATTE)],
            "idempotency_key": uuid.uuid4().hex} | extra
    r = client.post("/api/pos/orders", headers=h, json=body)
    return r


def _cash(client, h, o, amount=100000):
    return client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=h, json={"received_minor": amount})


# ------------------------------------------------------------------ menu admin
def test_menu_permissions(client, seeded, staff):
    assert client.get("/api/admin/menu", headers=staff[Role.KITCHEN]).status_code == 403
    assert client.get("/api/admin/menu", headers=staff[Role.INVENTORY]).status_code == 200
    pid = _pid(seeded, "Cola")
    assert client.patch(f"/api/admin/products/{pid}", headers=staff[Role.CASHIER], json={"is_available": False}).status_code == 403


def test_create_category_and_product_with_options(client, seeded, staff):
    h = staff[Role.ADMIN]
    cat = client.post("/api/admin/categories", headers=h, json={
        "slug": "smoothies", "name_en": "Smoothies", "name_km": "ទឹកក្រឡុក", "default_station": "DRINKS"}).json()
    assert client.post("/api/admin/categories", headers=h, json={"slug": "smoothies", "name_en": "X"}).status_code == 409
    r = client.post("/api/admin/products", headers=h, json={
        "category_id": cat["id"], "name_en": "Dragon Fruit Smoothie", "price_usd_cents": 325,
        "option_groups": [{"name_en": "Size", "selection": "SINGLE", "is_required": True,
                           "options": [{"name_en": "Regular", "is_default": True}, {"name_en": "Large", "price_delta_usd_cents": 75}]}]})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["effective_station"] == "DRINKS" and p["option_groups"][0]["options"][1]["price_delta_usd_cents"] == 75
    names = [x["name"]["en"] for x in client.get("/api/public/menu").json()["products"]]
    assert "Dragon Fruit Smoothie" in names


def test_two_defaults_in_single_choice_rejected(client, seeded, staff):
    pid = _pid(seeded, "Cola")
    r = client.patch(f"/api/admin/products/{pid}", headers=staff[Role.ADMIN], json={"option_groups": [
        {"name_en": "Size", "selection": "SINGLE", "options": [{"name_en": "A", "is_default": True}, {"name_en": "B", "is_default": True}]}]})
    assert r.status_code == 422


def test_price_change_is_audited_and_never_changes_old_orders(client, seeded, staff):
    o = _pos_order(client, staff[Role.CASHIER], seeded).json()
    pid = _pid(seeded, "Iced Latte")
    r = client.patch(f"/api/admin/products/{pid}", headers=staff[Role.ADMIN], json={"price_usd_cents": 300})
    assert r.json()["price_usd_cents"] == 300
    assert client.get(f"/api/admin/orders/{o['public_id']}", headers=staff[Role.ADMIN]).json()["total_usd_cents"] == 650
    with seeded() as s:
        log = s.scalar(select(AuditLog).where(AuditLog.action == "menu.price_changed"))
        assert log.details["price_usd_cents"] == {"from": "275", "to": "300"}


def test_option_edit_keeps_existing_option_ids(client, seeded, staff):
    pid = _pid(seeded, "Iced Latte")
    p = client.get("/api/admin/menu", headers=staff[Role.ADMIN]).json()
    latte = next(x for x in p["products"] if x["id"] == pid)
    groups = latte["option_groups"]
    groups[0]["options"][2]["price_delta_usd_cents"] = 120  # Large costs more
    r = client.patch(f"/api/admin/products/{pid}", headers=staff[Role.ADMIN], json={"option_groups": groups})
    after = r.json()["option_groups"][0]["options"]
    assert [o["id"] for o in after] == [o["id"] for o in groups[0]["options"]]
    assert after[2]["price_delta_usd_cents"] == 120


def test_sold_out_and_archive(client, seeded, staff):
    pid = _pid(seeded, "Cola")
    client.patch(f"/api/admin/products/{pid}", headers=staff[Role.ADMIN], json={"is_available": False})
    cola = next(x for x in client.get("/api/public/menu").json()["products"] if x["id"] == pid)
    assert cola["is_available"] is False
    client.patch(f"/api/admin/products/{pid}", headers=staff[Role.ADMIN], json={"is_archived": True})
    assert pid not in [x["id"] for x in client.get("/api/public/menu").json()["products"]]


def test_photo_upload_is_cleaned(client, seeded, staff, tmp_path, monkeypatch):
    from app.services import storage
    monkeypatch.setattr(storage, "LOCAL_DIR", tmp_path)
    img = Image.new("RGB", (2400, 1200), "orange")
    exif = Image.Exif()
    exif[0x010F] = "Secret Phone Maker"  # hidden camera data that must be removed
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    pid = _pid(seeded, "Cola")
    r = client.post(f"/api/admin/products/{pid}/photo", headers=staff[Role.ADMIN],
                    files={"file": ("cola.jpg", buf.getvalue(), "image/jpeg")})
    assert r.status_code == 200, r.text
    saved = next(tmp_path.rglob("*.jpg"))
    out = Image.open(saved)
    assert max(out.size) == 1600 and not out.getexif()
    bad = client.post(f"/api/admin/products/{pid}/photo", headers=staff[Role.ADMIN],
                      files={"file": ("x.jpg", b"<script>alert(1)</script>", "image/jpeg")})
    assert bad.status_code == 422


# ------------------------------------------------------------------ orders admin
def test_order_list_search_and_detail(client, seeded, staff):
    a = _pos_order(client, staff[Role.CASHIER], seeded).json()
    _cash(client, staff[Role.CASHIER], a)
    _pos_order(client, staff[Role.CASHIER], seeded)
    h = staff[Role.CASHIER]
    assert client.get("/api/admin/orders", headers=h).json()["total"] == 2
    assert client.get("/api/admin/orders?status=PAID", headers=h).json()["total"] == 1
    assert [o["number"] for o in client.get("/api/admin/orders?q=%23001", headers=h).json()["orders"]] == ["001"]
    d = client.get(f"/api/admin/orders/{a['public_id']}", headers=h).json()
    assert d["payments"][0]["change_given_minor"] == 100000 - 650 and d["restaurant"] == "LAGOM"
    assert d["created_by"] == "Cashier Person"
    assert client.get("/api/admin/orders", headers=staff[Role.KITCHEN]).status_code == 403


def test_cancel_unpaid_and_paid_orders(client, seeded, staff):
    unpaid = _pos_order(client, staff[Role.CASHIER], seeded).json()
    paid = _pos_order(client, staff[Role.CASHIER], seeded).json()
    _cash(client, staff[Role.CASHIER], paid)
    # cashiers cannot cancel
    assert client.post(f"/api/admin/orders/{unpaid['public_id']}/cancel", headers=staff[Role.CASHIER],
                       json={"reason": "changed mind"}).status_code == 403
    r = client.post(f"/api/admin/orders/{unpaid['public_id']}/cancel", headers=staff[Role.ADMIN], json={"reason": "changed mind"})
    assert r.json()["status"] == "CANCELLED"
    r = client.post(f"/api/admin/orders/{paid['public_id']}/cancel", headers=staff[Role.ADMIN], json={"reason": "wrong drink"})
    assert r.json()["status"] == "CANCELLED"
    refunds = client.get("/api/admin/refunds", headers=staff[Role.ADMIN]).json()
    assert len(refunds) == 1 and refunds[0]["amount_minor"] == 650
    assert client.post(f"/api/admin/refunds/{refunds[0]['id']}/complete", headers=staff[Role.CASHIER],
                       json={"reference": "cash"}).status_code == 403
    assert client.post(f"/api/admin/refunds/{refunds[0]['id']}/complete", headers=staff[Role.ADMIN],
                       json={"reference": "cash"}).json() == {"status": "COMPLETED"}
    d = client.get(f"/api/admin/orders/{paid['public_id']}", headers=staff[Role.ADMIN]).json()
    assert d["payments"][0]["status"] == "REFUNDED"
    assert client.get("/api/kds/drinks", headers=staff[Role.ADMIN]).json()["active"] == []
    assert client.post(f"/api/admin/orders/{paid['public_id']}/cancel", headers=staff[Role.ADMIN],
                       json={"reason": "again"}).status_code == 409


# ------------------------------------------------------------------ dashboard
def test_dashboard_counts_only_real_sales(client, seeded, staff):
    h = staff[Role.CASHIER]
    a = _pos_order(client, h, seeded).json()
    _cash(client, h, a)  # $6.50 sale
    b = _pos_order(client, h, seeded, items=[_line(seeded, "Fried Rice", 1, [("Protein", "Beef")])]).json()
    _cash(client, h, b)  # $5.50 sale
    _pos_order(client, h, seeded)  # unpaid: not a sale
    c = _pos_order(client, h, seeded).json()
    _cash(client, h, c)
    client.post(f"/api/admin/orders/{c['public_id']}/cancel", headers=staff[Role.OWNER], json={"reason": "test"})
    d = client.get("/api/admin/dashboard?period=today", headers=staff[Role.OWNER]).json()
    assert d["revenue_usd_cents"] == 1200 and d["orders"] == 2 and d["average_order_usd_cents"] == 600
    assert d["pending_payment"] == 1 and d["cancelled"] == 1
    assert d["best_sellers"][0] == {"name": "Iced Latte", "quantity": 2, "revenue_usd_cents": 650}
    assert d["payments"]["CASH"] == {"orders": 2, "usd_cents": 1200}
    assert sum(x["usd_cents"] for x in d["sales_chart"]) == 1200 and len(d["sales_chart"]) == 24
    assert {x["name"] for x in d["low_stock"]} == set()  # demo stock is healthy
    week = client.get("/api/admin/dashboard?period=7d", headers=staff[Role.OWNER]).json()
    assert len(week["sales_chart"]) == 7 and week["revenue_usd_cents"] == 1200
    assert client.get("/api/admin/dashboard?period=custom", headers=staff[Role.OWNER]).status_code == 422
    assert client.get("/api/admin/dashboard", headers=staff[Role.CASHIER]).status_code == 403


def test_yesterday_excludes_today(client, seeded, staff):
    a = _pos_order(client, staff[Role.CASHIER], seeded).json()
    _cash(client, staff[Role.CASHIER], a)
    assert client.get("/api/admin/dashboard?period=yesterday", headers=staff[Role.OWNER]).json()["revenue_usd_cents"] == 0
    with seeded() as s:
        o = s.scalar(select(Order))
        o.business_date = o.business_date - timedelta(days=1)
        s.commit()
    assert client.get("/api/admin/dashboard?period=yesterday", headers=staff[Role.OWNER]).json()["revenue_usd_cents"] == 650


# ------------------------------------------------------------------ POS
def test_pos_dine_in_needs_table_and_kitchen_gets_paid_order(client, seeded, staff):
    h = staff[Role.CASHIER]
    assert _pos_order(client, h, seeded, channel="POS_DINE_IN").status_code == 422
    with seeded() as s:
        table_id = s.scalar(select(DiningTable.id).where(DiningTable.label == "Table 07"))
    o = _pos_order(client, h, seeded, channel="POS_DINE_IN", table_id=table_id).json()
    assert o["table"] == "Table 07" and o["status"] == "PENDING_PAYMENT"
    assert client.get("/api/kds/drinks", headers=staff[Role.OWNER]).json()["active"] == []
    assert _cash(client, h, o, 500).status_code == 422  # not enough cash
    assert _cash(client, h, o, 1000).json()["change_minor"] == 350
    assert client.get("/api/kds/drinks", headers=staff[Role.OWNER]).json()["active"][0]["table"] == "Table 07"


def test_pos_discounts(client, seeded, staff):
    h = staff[Role.CASHIER]
    assert _pos_order(client, h, seeded, discount_percent=10).status_code == 422  # reason needed
    o = _pos_order(client, h, seeded, discount_percent=10, discount_reason="Regular customer").json()
    assert o["discount_usd_cents"] == 65 and o["total_usd_cents"] == 585
    assert _pos_order(client, h, seeded, discount_usd_cents=99999, discount_reason="x").status_code == 422
    assert _pos_order(client, staff[Role.KITCHEN], seeded).status_code == 403


def test_pos_idempotent(client, seeded, staff):
    key = uuid.uuid4().hex
    a = _pos_order(client, staff[Role.CASHIER], seeded, idempotency_key=key).json()
    b = _pos_order(client, staff[Role.CASHIER], seeded, idempotency_key=key).json()
    assert a["public_id"] == b["public_id"]


def test_pos_khqr_confirmed_by_aba_notice(client, seeded, staff, monkeypatch):
    from app.services import aba_notices
    s = get_settings()
    monkeypatch.setattr(s, "khqr_template", TEMPLATE)
    monkeypatch.setattr(s, "payway_chat_id", "-100777")
    monkeypatch.setattr(tg, "sent_log", [])
    o = _pos_order(client, staff[Role.CASHIER], seeded).json()
    q = client.post(f"/api/pos/orders/{o['public_id']}/khqr", headers=staff[Role.CASHIER], json={"currency": "USD"}).json()
    assert q["qr_string"].startswith("000201") and q["amount_minor"] == 650
    with seeded() as db:
        msg = {"date": None, "text": "$6.50 paid by A (*1) on Nov 16, 01:00 PM via ABA PAY at LAGOM. Trx. ID: 42, APV: 1.",
               "chat": {"id": -100777}, "from": {"is_bot": True, "username": "PayWayByABA_bot"}}
        assert aba_notices.handle(db, msg) == "matched"
    assert client.get(f"/api/admin/orders/{o['public_id']}", headers=staff[Role.CASHIER]).json()["status"] == "PAID"


def test_pos_history(client, seeded, staff):
    _pos_order(client, staff[Role.CASHIER], seeded)
    h = client.get("/api/pos/history", headers=staff[Role.CASHIER]).json()
    assert len(h["orders"]) == 1
