import pytest
from sqlalchemy import select

from app.models import DiningTable, Option, Product, TableSession
from app.models.base import utcnow
from app.models.enums import Role
from scripts.seed_demo import seed


@pytest.fixture
def seeded(SessionTest):
    with SessionTest() as s:
        seed(s, with_staff=False)
    return SessionTest


def _product(SessionTest, name):
    with SessionTest() as s:
        p = s.scalar(select(Product).where(Product.name_en == name))
        groups = {g.name_en: {o.name_en: o.id for o in g.options} for g in p.option_groups}
        return p.id, groups, p.price_usd_cents


def _latte_line(SessionTest, size="Medium", extras=(), qty=1):
    pid, g, _ = _product(SessionTest, "Iced Latte")
    ids = [g["Size"][size], g["Sugar"]["50%"], g["Ice"]["Normal ice"], *[g["Extras"][e] for e in extras]]
    return {"product_id": pid, "option_ids": ids, "quantity": qty}


# ------------------------------------------------------------------ menu
def test_menu_has_three_languages_and_options(client, seeded):
    m = client.get("/api/public/menu").json()
    assert len(m["categories"]) == 11
    latte = next(p for p in m["products"] if p["name"]["en"] == "Iced Latte")
    assert latte["name"]["km"] and latte["name"]["zh"]
    assert [g["name"]["en"] for g in latte["option_groups"]] == ["Size", "Sugar", "Ice", "Extras"]
    assert latte["station"] == "DRINKS"


def test_archived_products_hidden_from_menu(client, seeded):
    with seeded() as s:
        s.scalar(select(Product).where(Product.name_en == "Cola")).is_archived = True
        s.commit()
    names = [p["name"]["en"] for p in client.get("/api/public/menu").json()["products"]]
    assert "Cola" not in names


# ------------------------------------------------------------------ pricing
def test_quote_calculates_price_on_server(client, seeded):
    # Medium (+0.50) + extra shot (+0.50) on a $2.75 latte, x2  = $3.75 x 2
    r = client.post("/api/public/cart/quote", json={"items": [_latte_line(seeded, "Medium", ["Extra espresso shot"], 2)]})
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["lines"][0]["unit_price_usd_cents"] == 375
    assert q["subtotal_usd_cents"] == 750
    assert q["subtotal_khr"] == 30800  # 7.50 * 4100 = 30,750 -> 30,800


def test_quote_ignores_client_prices(client, seeded):
    line = {**_latte_line(seeded), "unit_price_usd_cents": 1, "price": 0}
    q = client.post("/api/public/cart/quote", json={"items": [line]}).json()
    assert q["subtotal_usd_cents"] == 325


def test_missing_required_option_rejected(client, seeded):
    pid, g, _ = _product(seeded, "Iced Latte")
    r = client.post("/api/public/cart/quote", json={"items": [{"product_id": pid, "option_ids": [g["Size"]["Small"]], "quantity": 1}]})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "missing_option"


def test_two_sizes_rejected(client, seeded):
    line = _latte_line(seeded)
    _, g, _ = _product(seeded, "Iced Latte")
    line["option_ids"].append(g["Size"]["Large"])
    assert client.post("/api/public/cart/quote", json={"items": [line]}).status_code == 422


def test_option_from_another_product_rejected(client, seeded):
    line = _latte_line(seeded)
    _, tea, _ = _product(seeded, "Brown Sugar Boba Milk Tea")
    line["option_ids"].append(tea["Toppings"]["Extra pearls"])
    assert client.post("/api/public/cart/quote", json={"items": [line]}).status_code == 422


def test_sold_out_product_and_option_rejected(client, seeded):
    with seeded() as s:
        s.scalar(select(Option).where(Option.name_en == "Oat milk")).is_available = False
        s.commit()
    r = client.post("/api/public/cart/quote", json={"items": [_latte_line(seeded, extras=["Oat milk"])]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "sold_out"
    with seeded() as s:
        s.scalar(select(Product).where(Product.name_en == "Iced Latte")).is_available = False
        s.commit()
    r = client.post("/api/public/cart/quote", json={"items": [_latte_line(seeded)]})
    assert r.json()["detail"]["code"] == "sold_out"


@pytest.mark.parametrize("qty", [0, -1, 51])
def test_bad_quantities_rejected(client, seeded, qty):
    assert client.post("/api/public/cart/quote", json={"items": [_latte_line(seeded, qty=1) | {"quantity": qty}]}).status_code == 422


def test_unknown_product_rejected(client, seeded):
    r = client.post("/api/public/cart/quote", json={"items": [{"product_id": 99999, "option_ids": [], "quantity": 1}]})
    assert r.status_code == 422


# ------------------------------------------------------------------ table sessions
def _token(SessionTest, label="Table 01"):
    with SessionTest() as s:
        return s.scalar(select(DiningTable.qr_token).where(DiningTable.label == label))


def test_scan_creates_private_session_and_recovers_it(client, seeded):
    qr = _token(seeded)
    a = client.post(f"/api/public/tables/{qr}/session", json={}).json()
    assert a["table"]["label"] == "Table 01" and len(a["session_token"]) >= 40
    again = client.post(f"/api/public/tables/{qr}/session", json={"previous_session_token": a["session_token"]}).json()
    assert again["session_token"] == a["session_token"]
    # another phone at the same table gets a different session
    other = client.post(f"/api/public/tables/{qr}/session", json={}).json()
    assert other["session_token"] != a["session_token"]
    assert client.get("/api/public/session", headers={"X-Table-Session": a["session_token"]}).json()["table"]["label"] == "Table 01"


def test_session_from_other_table_not_reused(client, seeded):
    a = client.post(f"/api/public/tables/{_token(seeded)}/session", json={}).json()
    b = client.post(f"/api/public/tables/{_token(seeded, 'Table 02')}/session",
                    json={"previous_session_token": a["session_token"]}).json()
    assert b["session_token"] != a["session_token"] and b["table"]["label"] == "Table 02"


def test_invalid_or_inactive_qr_rejected(client, seeded):
    assert client.post("/api/public/tables/not-a-real-token/session", json={}).status_code == 404
    with seeded() as s:
        s.scalar(select(DiningTable).where(DiningTable.label == "Table 03")).is_active = False
        s.commit()
    assert client.post(f"/api/public/tables/{_token(seeded, 'Table 03')}/session", json={}).status_code == 404


def test_expired_session_rejected(client, seeded):
    a = client.post(f"/api/public/tables/{_token(seeded)}/session", json={}).json()
    with seeded() as s:
        ts = s.scalar(select(TableSession).where(TableSession.token == a["session_token"]))
        ts.last_seen_at = utcnow().replace(year=2020)
        s.commit()
    assert client.get("/api/public/session", headers={"X-Table-Session": a["session_token"]}).status_code == 401


# ------------------------------------------------------------------ table admin + QR
def test_table_admin_requires_permission(client, seeded, make_user, login):
    make_user(Role.CASHIER)
    assert client.get("/api/admin/tables", headers=login("cashier@test.com")).status_code == 403


def test_create_rename_deactivate_table(client, seeded, owner_headers):
    r = client.post("/api/admin/tables", headers=owner_headers, json={"label": "Table 13", "seats": 2})
    assert r.status_code == 201
    t = r.json()
    assert t["qr_url"].endswith("/t/" + t["qr_url"].rsplit("/", 1)[1])
    assert client.post("/api/admin/tables", headers=owner_headers, json={"label": "Table 13"}).status_code == 409
    r = client.patch(f"/api/admin/tables/{t['id']}", headers=owner_headers, json={"is_active": False})
    assert r.json()["is_active"] is False


def test_rotate_qr_invalidates_old_code_and_sessions(client, seeded, owner_headers):
    old = _token(seeded)
    sess = client.post(f"/api/public/tables/{old}/session", json={}).json()["session_token"]
    tid = client.get("/api/admin/tables", headers=owner_headers).json()[0]["id"]
    client.post(f"/api/admin/tables/{tid}/rotate-qr", headers=owner_headers)
    assert client.post(f"/api/public/tables/{old}/session", json={}).status_code == 404
    assert client.get("/api/public/session", headers={"X-Table-Session": sess}).status_code == 401


def test_qr_png_and_a4_cards(client, seeded, owner_headers):
    tid = client.get("/api/admin/tables", headers=owner_headers).json()[0]["id"]
    png = client.get(f"/api/admin/tables/{tid}/qr.png", headers=owner_headers)
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    pdf = client.get("/api/admin/tables/cards.pdf", headers=owner_headers)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert pdf.content.count(b"/Type /Page\n") + pdf.content.count(b"/Type /Page ") >= 3  # 12 tables, 4 per page
