"""Telegram: staff alerts, daily summary, Mini App login and pickup orders."""
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import DiningTable, Order, Product
from app.models.base import utcnow
from app.models.enums import Role
from app.services import notifications
from app.services import telegram as tg
from app.services.payments import expire_due_orders
from app.services.telegram_auth import TelegramAuthError, sign_for_tests, validate_init_data
from scripts.seed_demo import seed
from tests.test_khqr_payments import TEMPLATE

BOT = "123456:TEST-bot-token"


@pytest.fixture
def sent(monkeypatch):
    log = []
    monkeypatch.setattr(tg, "sent_log", log)
    s = get_settings()
    monkeypatch.setattr(s, "telegram_bot_token", BOT)
    monkeypatch.setattr(s, "telegram_chat_id", "-100555")
    monkeypatch.setattr(s, "khqr_template", TEMPLATE)
    return log


@pytest.fixture
def seeded(SessionTest):
    with SessionTest() as s:
        seed(s, with_staff=False)
    return SessionTest


@pytest.fixture
def staff(make_user, login):
    out = {}
    for role in (Role.OWNER, Role.CASHIER, Role.KITCHEN):
        make_user(role)
        out[role] = login(f"{role.value.lower()}@test.com")
    return out


def init_data(user_id=777, first_name="Dara", auth_date=None, token=BOT):
    return sign_for_tests({"auth_date": str(auth_date or int(time.time())), "query_id": "AAH",
                           "user": json.dumps({"id": user_id, "first_name": first_name, "language_code": "km"})}, token)


def rice(SessionTest):
    with SessionTest() as s:
        p = s.scalar(select(Product).where(Product.name_en == "Fried Rice"))
        chicken = next(o.id for g in p.option_groups for o in g.options if o.name_en == "Chicken")
    return {"product_id": p.id, "quantity": 1, "option_ids": [chicken]}


def table_qr(SessionTest):
    with SessionTest() as s:
        return s.scalar(select(DiningTable.qr_token).where(DiningTable.label == "Table 01"))


# ------------------------------------------------------------------ login check
def test_valid_telegram_login():
    user = validate_init_data(init_data(), BOT)
    assert user["id"] == 777 and user["first_name"] == "Dara"


@pytest.mark.parametrize("bad", ["wrong-token", "tampered", "old", "no-hash"])
def test_fake_or_old_telegram_login_rejected(bad):
    data = init_data()
    if bad == "wrong-token":
        data = init_data(token="999:someone-else")
    elif bad == "tampered":
        data = data.replace("Dara", "Hacker")
    elif bad == "old":
        data = init_data(auth_date=int(time.time()) - 2 * 24 * 3600)
    elif bad == "no-hash":
        data = data.split("&hash=")[0]
    with pytest.raises(TelegramAuthError):
        validate_init_data(data, BOT)


# ------------------------------------------------------------------ Mini App pickup orders
def test_mini_app_off_without_bot(client, seeded):
    assert client.post("/api/public/telegram/session", json={"init_data": init_data()}).status_code == 503


def test_pickup_order_flow(client, seeded, staff, sent):
    r = client.post("/api/public/telegram/session", json={"init_data": init_data(), "language": "km"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pickup"] is True and body["table"]["label"] == "Pickup · Dara"
    again = client.post("/api/public/telegram/session", json={"init_data": init_data()}).json()
    assert again["session_token"] == body["session_token"]  # same person, same session
    h = {"X-Table-Session": body["session_token"]}
    o = client.post("/api/public/orders", headers=h,
                    json={"items": [rice(seeded)], "idempotency_key": uuid.uuid4().hex}).json()
    assert o["table"] == "Pickup · Dara" and o["channel"] == "TELEGRAM"
    client.post(f"/api/public/orders/{o['public_id']}/pay", headers=h, json={"method": "cash", "currency": "USD"})
    client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=staff[Role.CASHIER], json={"received_minor": 1000})
    assert any(m.startswith("to 777:") and "បានទទួលការបង់ប្រាក់" in m for m in sent)  # customer told, in Khmer
    assert client.get("/api/kds/kitchen", headers=staff[Role.KITCHEN]).json()["active"][0]["table"] == "Pickup · Dara"
    client.post(f"/api/kds/kitchen/orders/{o['public_id']}/ready", headers=staff[Role.KITCHEN])
    assert any(m.startswith("to 777:") and "#001" in m and "រួចរាល់" in m for m in sent)


def test_fake_login_cannot_open_session(client, seeded, sent):
    r = client.post("/api/public/telegram/session", json={"init_data": init_data().replace("Dara", "Mallory")})
    assert r.status_code == 401


def test_other_telegram_user_cannot_see_my_order(client, seeded, sent):
    me = client.post("/api/public/telegram/session", json={"init_data": init_data(1)}).json()["session_token"]
    other = client.post("/api/public/telegram/session", json={"init_data": init_data(2)}).json()["session_token"]
    o = client.post("/api/public/orders", headers={"X-Table-Session": me},
                    json={"items": [rice(seeded)], "idempotency_key": uuid.uuid4().hex}).json()
    assert client.get(f"/api/public/orders/{o['public_id']}", headers={"X-Table-Session": other}).status_code == 404


# ------------------------------------------------------------------ staff alerts
def _pos_paid(client, staff, SessionTest):
    o = client.post("/api/pos/orders", headers=staff[Role.CASHIER], json={
        "channel": "POS_TAKEAWAY", "items": [rice(SessionTest)], "idempotency_key": uuid.uuid4().hex}).json()
    client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=staff[Role.CASHIER], json={"received_minor": 1000})
    return o


def test_new_order_and_cancellation_alerts(client, seeded, staff, sent):
    o = _pos_paid(client, staff, seeded)
    alert = next(m for m in sent if "New order #001" in m)
    assert "Fried Rice" in alert and "$4.50" in alert and "Cash" in alert
    client.post(f"/api/admin/orders/{o['public_id']}/cancel", headers=staff[Role.OWNER], json={"reason": "Wrong table"})
    assert any("cancelled" in m and "Wrong table" in m and "Refund" in m for m in sent)


def test_alerts_can_be_switched_off(client, seeded, staff, sent):
    client.patch("/api/settings", headers=staff[Role.OWNER], json={"telegram_notify_new_orders": False})
    _pos_paid(client, staff, seeded)
    assert not any("New order" in m for m in sent)


def test_expired_khqr_alert(client, seeded, sent, SessionTest):
    tok = client.post(f"/api/public/tables/{table_qr(SessionTest)}/session", json={}).json()["session_token"]
    h = {"X-Table-Session": tok}
    o = client.post("/api/public/orders", headers=h,
                    json={"items": [rice(seeded)], "idempotency_key": uuid.uuid4().hex}).json()
    client.post(f"/api/public/orders/{o['public_id']}/pay", headers=h, json={"method": "khqr", "currency": "USD"})
    with SessionTest() as db:
        db.scalar(select(Order)).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
        expire_due_orders(db)
    assert any("expired unpaid" in m for m in sent)


def test_daily_summary_once_after_closing(client, seeded, staff, sent, SessionTest):
    _pos_paid(client, staff, seeded)
    sent.clear()
    noon = datetime.now(timezone.utc).replace(hour=5, minute=0)  # 12:00 in Phnom Penh
    late = datetime.now(timezone.utc).replace(hour=15, minute=30)  # 22:30 in Phnom Penh
    with SessionTest() as db:
        assert notifications.maybe_send_daily_summary(db, noon) is False
        assert notifications.maybe_send_daily_summary(db, late) is True
        assert notifications.maybe_send_daily_summary(db, late + timedelta(minutes=5)) is False
    summary = sent[0]
    assert "LAGOM" in summary and "Sales:" in summary and "Fried Rice" in summary


def test_summary_time_setting_validated(client, staff):
    assert client.patch("/api/settings", headers=staff[Role.OWNER], json={"daily_summary_time": "25:00"}).status_code == 422
    assert client.patch("/api/settings", headers=staff[Role.OWNER], json={"daily_summary_time": "21:30"}).status_code == 200
    assert client.patch("/api/settings", headers=staff[Role.OWNER], json={"daily_summary_last_sent": "x"}).status_code == 422


def test_send_test_message(client, staff, sent):
    r = client.post("/api/settings/telegram/test", headers=staff[Role.OWNER])
    assert r.json() == {"sent": True} and "test message" in sent[-1]
    assert client.post("/api/settings/telegram/test", headers=staff[Role.CASHIER]).status_code == 403


def test_test_message_without_bot(client, staff):
    assert client.post("/api/settings/telegram/test", headers=staff[Role.OWNER]).status_code == 409


def test_broken_alert_never_breaks_payment(client, seeded, staff, sent, monkeypatch):
    def boom(_text):
        raise RuntimeError("telegram down")
    monkeypatch.setattr(tg, "notify", boom)
    o = client.post("/api/pos/orders", headers=staff[Role.CASHIER], json={
        "channel": "POS_TAKEAWAY", "items": [rice(seeded)], "idempotency_key": uuid.uuid4().hex}).json()
    r = client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=staff[Role.CASHIER], json={"received_minor": 1000})
    assert r.status_code == 200 and r.json()["status"] == "PAID"
