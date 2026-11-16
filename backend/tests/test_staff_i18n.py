"""Staff self-service, audit log and translated server messages."""
import re
from pathlib import Path

from sqlalchemy import select

from app.i18n import MESSAGES, PATTERNS, pick_language, translate
from app.models import Product
from app.models.enums import Role
from scripts.seed_demo import seed
from tests.conftest import PASSWORD

APP = Path(__file__).resolve().parents[1] / "app"


def test_language_choice_from_header():
    assert pick_language("km-KH,km;q=0.9,en;q=0.8") == "km"
    assert pick_language("zh-CN,zh;q=0.9") == "zh"
    assert pick_language("fr-FR,de;q=0.5") == "en"
    assert pick_language(None) == "en"


def test_every_translation_is_complete():
    for en, (km, zh) in MESSAGES.items():
        assert km.strip() and zh.strip() and km != en and zh != en, en
    for _, (km, zh) in PATTERNS:
        assert km and zh


def test_every_server_message_is_in_the_catalog():
    """Fails if someone adds an error message in English without a Khmer/Chinese translation."""
    found = set()
    for f in APP.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        found |= set(re.findall(r'HTTPException\([^,()]+,\s*"([^"{}]+)"', text))
        found |= set(re.findall(r'(?:PaymentProblem|KitchenProblem|PricingError)\("([^"{}]+)"', text))
    developer_only = {"Use ADJUSTMENT or WASTE.", "Unknown station.", "Unknown action.", "Unknown status.",
                      "Unknown ingredient.", "Give a change or the counted quantity.", "Option not found.",
                      "Item not found.", "Category not found.", "Table not found.", "Product not found.",
                      "Supplier not found.", "Ingredient not found.", "Expense not found.", "Refund not found.",
                      "Bank payment not found.", "No KHQR payment is waiting for this order.",
                      "display_currency must be USD or KHR", "inventory_deduct_on must be PAID or READY"}
    missing = sorted(m for m in found - developer_only if m.strip() and translate(m, "km") == m)
    assert missing == []


def test_customer_errors_come_back_in_their_language(client, SessionTest):
    with SessionTest() as s:
        seed(s, with_staff=False)
        cola = s.scalar(select(Product).where(Product.name_en == "Cola"))
        cola.is_available = False
        cola_id = cola.id
        s.commit()
    r = client.post("/api/public/tables/nope/session", json={}, headers={"Accept-Language": "zh-CN"})
    assert r.json()["detail"] == "此二维码无效，请联系店员。"
    r = client.post("/api/public/cart/quote", headers={"Accept-Language": "km"},
                    json={"items": [{"product_id": cola_id, "quantity": 1, "option_ids": []}]})
    assert r.json()["detail"]["message"] == "មុខម្ហូបនេះអស់ហើយពេលនេះ។" and r.json()["detail"]["code"] == "sold_out"
    r = client.post("/api/public/cart/quote", json={"items": [{"product_id": cola_id, "quantity": 1, "option_ids": []}]})
    assert r.json()["detail"]["message"] == "Cola is sold out right now."


def test_staff_errors_translated(client, owner_headers):
    r = client.post("/api/staff", headers={**owner_headers, "Accept-Language": "km"}, json={
        "email": "x@test.com", "full_name": "X", "role": "CASHIER", "password": "alllowercase"})
    assert r.status_code == 422
    assert "ប្រើអក្សរធំ និងអក្សរតូច" in r.json()["detail"] and "ដាក់លេខយ៉ាងហោចណាស់មួយ" in r.json()["detail"]


def test_staff_choose_their_language(client, make_user, login):
    make_user(Role.KITCHEN)
    h = login("kitchen@test.com")
    assert client.patch("/api/auth/me", headers=h, json={"preferred_language": "km"}).json()["preferred_language"] == "km"
    assert client.patch("/api/auth/me", headers=h, json={"preferred_language": "fr"}).status_code == 422
    r = client.post("/api/auth/login", json={"email": "kitchen@test.com", "password": PASSWORD})
    assert r.json()["user"]["preferred_language"] == "km"


def test_audit_log_owner_only_and_filtered(client, owner_headers, make_user, login):
    client.post("/api/staff", headers=owner_headers, json={
        "email": "c@test.com", "full_name": "C", "role": "CASHIER", "password": "Strong-pass-99"})
    client.patch("/api/settings", headers=owner_headers, json={"khr_per_usd": "4050"})
    r = client.get("/api/admin/audit?action=staff.", headers=owner_headers).json()
    assert [e["action"] for e in r["entries"]] == ["staff.created"] and r["entries"][0]["user"] == "Owner Person"
    assert client.get("/api/admin/audit", headers=owner_headers).json()["total"] >= 3  # logins too
    make_user(Role.ADMIN)
    assert client.get("/api/admin/audit", headers=login("admin@test.com")).status_code == 403


def test_full_role_matrix(client, SessionTest, make_user, login):
    """What each role can open (the backend enforces this, not only the menus)."""
    with SessionTest() as s:
        seed(s, with_staff=False)
    checks = {
        "/api/admin/dashboard": {Role.OWNER, Role.ADMIN},
        "/api/admin/orders": {Role.OWNER, Role.ADMIN, Role.CASHIER},
        "/api/admin/menu": {Role.OWNER, Role.ADMIN, Role.CASHIER, Role.INVENTORY},
        "/api/admin/inventory/ingredients": {Role.OWNER, Role.ADMIN, Role.INVENTORY},
        "/api/admin/finance/report": {Role.OWNER, Role.ADMIN},
        "/api/staff": {Role.OWNER, Role.ADMIN},
        "/api/settings": {Role.OWNER},
        "/api/admin/audit": {Role.OWNER},
        "/api/admin/tables": {Role.OWNER, Role.ADMIN},
        "/api/kds/kitchen": {Role.OWNER, Role.ADMIN, Role.KITCHEN},
        "/api/kds/drinks": {Role.OWNER, Role.ADMIN, Role.DRINKS},
        "/api/kds/dessert": {Role.OWNER, Role.ADMIN, Role.KITCHEN, Role.DRINKS},
        "/api/pos/tables": {Role.OWNER, Role.ADMIN, Role.CASHIER},
    }
    heads = {}
    for role in Role:
        make_user(role)
        heads[role] = login(f"{role.value.lower()}@test.com")
    for path, allowed in checks.items():
        for role in Role:
            code = client.get(path, headers=heads[role]).status_code
            assert (code == 200) == (role in allowed), f"{role} {path} -> {code}"


def test_audit_log_search(client, make_user, login):
    make_user(Role.OWNER)
    h = login("owner@test.com")
    client.post("/api/auth/login", json={"email": "nobody@test.com", "password": "Wrong-password-1"})
    found = client.get("/api/admin/audit?q=login_failed", headers=h).json()
    assert found["total"] >= 1 and all("login_failed" in e["action"] for e in found["entries"])
    by_person = client.get("/api/admin/audit?q=owner person", headers=h).json()
    assert by_person["total"] >= 1 and all(e["user"] == "Owner Person" for e in by_person["entries"])
    assert client.get("/api/admin/audit?q=zzz-nothing", headers=h).json()["total"] == 0
