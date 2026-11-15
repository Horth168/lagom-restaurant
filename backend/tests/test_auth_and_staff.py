from app.models.enums import Role
from tests.conftest import PASSWORD


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_login_success_returns_permissions(client, make_user):
    make_user(Role.CASHIER)
    r = client.post("/api/auth/login", json={"email": "CASHIER@test.com", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "CASHIER"
    assert "orders.create" in body["user"]["permissions"]
    assert "staff.manage" not in body["user"]["permissions"]
    assert "password_hash" not in body["user"]


def test_login_wrong_password_and_unknown_email_look_the_same(client, make_user):
    make_user(Role.CASHIER)
    a = client.post("/api/auth/login", json={"email": "cashier@test.com", "password": "nope-nope-1A"})
    b = client.post("/api/auth/login", json={"email": "ghost@test.com", "password": "nope-nope-1A"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_login_is_rate_limited(client, make_user):
    make_user(Role.CASHIER)
    codes = [
        client.post("/api/auth/login", json={"email": "cashier@test.com", "password": "Wrong-pass-1"}).status_code
        for _ in range(12)
    ]
    assert 429 in codes


def test_inactive_user_cannot_login(client, make_user):
    make_user(Role.CASHIER, is_active=False)
    r = client.post("/api/auth/login", json={"email": "cashier@test.com", "password": PASSWORD})
    assert r.status_code == 403


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_kitchen_staff_cannot_manage_staff(client, make_user, login):
    make_user(Role.KITCHEN)
    h = login("kitchen@test.com")
    assert client.get("/api/staff", headers=h).status_code == 403


def test_owner_creates_staff_and_new_staff_can_login(client, owner_headers, login):
    r = client.post("/api/staff", headers=owner_headers, json={
        "email": "new.cashier@test.com", "full_name": "New Cashier", "role": "CASHIER", "password": "Strong-pass-99",
    })
    assert r.status_code == 201, r.text
    login("new.cashier@test.com", "Strong-pass-99")


def test_weak_password_rejected(client, owner_headers):
    r = client.post("/api/staff", headers=owner_headers, json={
        "email": "x@test.com", "full_name": "X", "role": "CASHIER", "password": "alllowercase",
    })
    assert r.status_code == 422


def test_duplicate_email_rejected(client, owner_headers):
    body = {"email": "dup@test.com", "full_name": "D", "role": "CASHIER", "password": "Strong-pass-99"}
    assert client.post("/api/staff", headers=owner_headers, json=body).status_code == 201
    assert client.post("/api/staff", headers=owner_headers, json={**body, "email": "DUP@test.com"}).status_code == 409


def test_admin_cannot_create_owner_or_grant_owner_permissions(client, make_user, login):
    make_user(Role.ADMIN)
    h = login("admin@test.com")
    r = client.post("/api/staff", headers=h, json={
        "email": "o2@test.com", "full_name": "O", "role": "OWNER", "password": "Strong-pass-99"})
    assert r.status_code == 403
    r = client.post("/api/staff", headers=h, json={
        "email": "c2@test.com", "full_name": "C", "role": "CASHIER", "password": "Strong-pass-99",
        "extra_permissions": ["settings.edit"]})
    assert r.status_code == 403


def test_deactivating_staff_revokes_their_token(client, owner_headers, make_user, login):
    u = make_user(Role.CASHIER)
    h = login("cashier@test.com")
    assert client.get("/api/auth/me", headers=h).status_code == 200
    r = client.patch(f"/api/staff/{u.id}", headers=owner_headers, json={"is_active": False})
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401


def test_last_owner_cannot_be_removed(client, make_user, login, db):
    owner = make_user(Role.OWNER)
    h = login("owner@test.com")
    # cannot deactivate self
    assert client.patch(f"/api/staff/{owner.id}", headers=h, json={"is_active": False}).status_code == 400


def test_extra_permission_grants_access(client, owner_headers, make_user, login):
    u = make_user(Role.CASHIER)
    h = login("cashier@test.com")
    assert client.get("/api/staff", headers=h).status_code == 403
    client.patch(f"/api/staff/{u.id}", headers=owner_headers, json={"extra_permissions": ["staff.manage"]})
    h = login("cashier@test.com")  # old token was revoked when permissions changed
    assert client.get("/api/staff", headers=h).status_code == 200


def test_change_password_signs_out_other_devices(client, make_user, login):
    make_user(Role.CASHIER)
    h = login("cashier@test.com")
    r = client.post("/api/auth/change-password", headers=h,
                    json={"current_password": PASSWORD, "new_password": "Brand-new-pass-1"})
    assert r.status_code == 204
    assert client.get("/api/auth/me", headers=h).status_code == 401
    login("cashier@test.com", "Brand-new-pass-1")


def test_settings_owner_only_and_validated(client, owner_headers, make_user, login):
    make_user(Role.ADMIN)
    admin = login("admin@test.com")
    assert client.patch("/api/settings", headers=admin, json={"khr_per_usd": 4000}).status_code == 403
    assert client.patch("/api/settings", headers=owner_headers, json={"khr_per_usd": 5}).status_code == 422
    r = client.patch("/api/settings", headers=owner_headers, json={"khr_per_usd": "4050", "display_currency": "KHR"})
    assert r.status_code == 200
    pub = client.get("/api/settings/public").json()
    assert pub["khr_per_usd"] == "4050" and pub["display_currency"] == "KHR"


def test_settings_never_expose_secrets(client, owner_headers):
    body = client.get("/api/settings", headers=owner_headers).json()
    text = str(body).lower()
    assert "api_key" not in text and "bot_token" not in text
