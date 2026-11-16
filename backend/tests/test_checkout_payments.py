"""Checkout and ABA PayWay flow, using the PayWay simulator (same API, same hash rules)."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import DiningTable, Order, Payment, PaymentEvent, Product
from app.models.base import utcnow
from app.services import payway as pw
from app.services.payments import expire_due_orders
from app.services.payway_simulator import PayWaySimulator
from scripts.seed_demo import seed


@pytest.fixture
def sim():
    s = PayWaySimulator()
    pw.set_payway_override(s.client())
    yield s
    pw.set_payway_override(None)


@pytest.fixture
def seeded(SessionTest):
    with SessionTest() as s:
        seed(s, with_staff=False)
    return SessionTest


def _session(client, SessionTest, label="Table 01"):
    with SessionTest() as s:
        qr = s.scalar(select(DiningTable.qr_token).where(DiningTable.label == label))
    tok = client.post(f"/api/public/tables/{qr}/session", json={}).json()["session_token"]
    return {"X-Table-Session": tok}


def _latte(SessionTest, qty=2):
    with SessionTest() as s:
        p = s.scalar(select(Product).where(Product.name_en == "Iced Latte"))
        g = {grp.name_en: {o.name_en: o.id for o in grp.options} for grp in p.option_groups}
    return {"product_id": p.id, "quantity": qty,
            "option_ids": [g["Size"]["Medium"], g["Sugar"]["50%"], g["Ice"]["Normal ice"]]}


def _checkout(client, h, SessionTest, key=None, qty=2):
    r = client.post("/api/public/orders", headers=h, json={
        "items": [_latte(SessionTest, qty)], "idempotency_key": key or uuid.uuid4().hex})
    assert r.status_code == 201, r.text
    return r.json()


def _pay(client, h, order, option="abapay_khqr", currency="USD"):
    return client.post(f"/api/public/orders/{order['public_id']}/pay", headers=h,
                       json={"payment_option": option, "currency": currency})


# ------------------------------------------------------------------ hashing
def test_hash_is_base64_hmac_sha512():
    import base64
    import hashlib
    import hmac
    expected = base64.b64encode(hmac.new(b"key", b"20250101000000m1t1", hashlib.sha512).digest()).decode()
    assert pw.sign("key", "20250101000000", "m1", "t1") == expected


def test_amount_formats():
    assert pw.amount_value(850, "USD") == 8.5
    assert pw.amount_value(1000, "USD") == 10
    assert pw.amount_value(34900, "KHR") == 34900
    assert pw.amount_for_hash(8.5) == "8.5" and pw.amount_for_hash(10) == "10"
    assert pw.minor_units(8.5, "USD") == 850 and pw.minor_units(34900, "KHR") == 34900


# ------------------------------------------------------------------ checkout
def test_checkout_locks_prices_and_waits_for_payment(client, seeded, sim):
    h = _session(client, seeded)
    o = _checkout(client, h, seeded)
    assert o["status"] == "PENDING_PAYMENT"
    assert o["total_usd_cents"] == 650  # (2.75 + 0.50) x 2
    assert o["number"] == "001" and o["table"] == "Table 01"
    # changing the menu price afterwards does not change the order
    with seeded() as s:
        s.scalar(select(Product).where(Product.name_en == "Iced Latte")).price_usd_cents = 999
        s.commit()
    assert client.get(f"/api/public/orders/{o['public_id']}", headers=h).json()["total_usd_cents"] == 650


def test_same_idempotency_key_returns_same_order(client, seeded, sim):
    h = _session(client, seeded)
    a = _checkout(client, h, seeded, key="k" * 20)
    b = _checkout(client, h, seeded, key="k" * 20)
    assert a["public_id"] == b["public_id"]
    with seeded() as s:
        assert len(s.scalars(select(Order)).all()) == 1


def test_order_numbers_increase(client, seeded, sim):
    h = _session(client, seeded)
    assert [_checkout(client, h, seeded)["number"] for _ in range(3)] == ["001", "002", "003"]


def test_other_phone_cannot_see_or_pay_my_order(client, seeded, sim):
    mine = _session(client, seeded)
    other = _session(client, seeded)  # same table, different phone
    o = _checkout(client, mine, seeded)
    assert client.get(f"/api/public/orders/{o['public_id']}", headers=other).status_code == 404
    assert _pay(client, other, o).status_code == 404
    assert client.get("/api/public/orders", headers=other).json() == []


def test_checkout_requires_table_session(client, seeded, sim):
    r = client.post("/api/public/orders", json={"items": [_latte(seeded)], "idempotency_key": uuid.uuid4().hex})
    assert r.status_code == 401


# ------------------------------------------------------------------ payment
def test_full_payment_flow_via_callback(client, seeded, sim):
    h = _session(client, seeded)
    o = _checkout(client, h, seeded)
    paid = _pay(client, h, o).json()
    pay = paid["payment"]
    assert pay["status"] == "PENDING" and pay["qr_string"] and pay["deeplink"].startswith("abamobilebank://")
    # PayWay received the correct amount
    path, body = next(c for c in sim.calls if c[0] == pw.GENERATE_QR)
    assert body["amount"] == 6.5 and body["currency"] == "USD" and body["merchant_id"] == sim.merchant_id

    sim.pay(pay["tran_id"])
    r = client.post("/api/payments/payway/callback", json={"tran_id": pay["tran_id"], "status": "0"})
    assert r.json() == {"received": True}
    o2 = client.get(f"/api/public/orders/{o['public_id']}", headers=h).json()
    assert o2["status"] == "PAID" and o2["paid_at"]
    assert o2["payment"]["status"] == "APPROVED" and o2["payment"]["reference"]
    assert all(i["status"] == "QUEUED" for i in o2["items"])


def test_fake_callback_without_real_payment_does_nothing(client, seeded, sim):
    h = _session(client, seeded)
    o = _checkout(client, h, seeded)
    tran = _pay(client, h, o).json()["payment"]["tran_id"]
    # Attacker posts a "success" callback, but PayWay says the transaction is still pending
    client.post("/api/payments/payway/callback", json={"tran_id": tran, "status": "0", "apv": "123456"})
    assert client.get(f"/api/public/orders/{o['public_id']}", headers=h).json()["status"] == "PENDING_PAYMENT"
    with seeded() as s:
        kinds = [e.kind for e in s.scalars(select(PaymentEvent)).all()]
    assert "CALLBACK" in kinds and "CHECK" in kinds


def test_callback_for_unknown_transaction_is_logged_and_ignored(client, seeded, sim):
    r = client.post("/api/payments/payway/callback", json={"tran_id": "999", "status": "0"})
    assert r.status_code == 200
    with seeded() as s:
        assert s.scalar(select(PaymentEvent).where(PaymentEvent.tran_id == "999")).kind == "CALLBACK"


def test_missed_callback_is_caught_by_status_polling(client, seeded, sim):
    h = _session(client, seeded)
    o = _checkout(client, h, seeded)
    tran = _pay(client, h, o).json()["payment"]["tran_id"]
    sim.pay(tran)  # paid, but PayWay's callback never arrives
    assert client.get(f"/api/public/orders/{o['public_id']}", headers=h).json()["status"] == "PAID"


def test_wrong_amount_is_not_accepted(client, seeded, sim):
    h = _session(client, seeded)
    o = _checkout(client, h, seeded)
    tran = _pay(client, h, o).json()["payment"]["tran_id"]
    sim.pay(tran, amount=0.01)
    client.post("/api/payments/payway/callback", json={"tran_id": tran})
    assert client.get(f"/api/public/orders/{o['public_id']}", headers=h).json()["status"] == "PENDING_PAYMENT"
    with seeded() as s:
        assert "mismatch" in s.scalar(select(Payment)).failure_reason.lower()


def test_repeated_callbacks_are_idempotent(client, seeded, sim):
    h = _session(client, seeded)
    o = _checkout(client, h, seeded)
    tran = _pay(client, h, o).json()["payment"]["tran_id"]
    sim.pay(tran)
    for _ in range(3):
        client.post("/api/payments/payway/callback", json={"tran_id": tran})
    with seeded() as s:
        order = s.scalar(select(Order))
        assert order.status == "PAID"
        assert [p.status for p in order.payments] == ["APPROVED"]


def test_reload_reuses_qr_and_switch_closes_old_one(client, seeded, sim):
    h = _session(client, seeded)
    o = _checkout(client, h, seeded)
    first = _pay(client, h, o).json()["payment"]["tran_id"]
    assert _pay(client, h, o).json()["payment"]["tran_id"] == first  # same QR on reload
    second = _pay(client, h, o, option="wechat").json()["payment"]["tran_id"]
    assert second != first
    assert sim.transactions[first]["status"] == "CANCELLED"  # old QR can no longer be paid


def test_khr_payment_uses_locked_khr_total(client, seeded, sim, owner_headers):
    client.patch("/api/settings", headers=owner_headers, json={"accepted_payment_currencies": ["USD", "KHR"]})
    h = _session(client, seeded)
    o = _checkout(client, h, seeded)
    pay = _pay(client, h, o, currency="KHR").json()["payment"]
    assert pay["currency"] == "KHR" and pay["amount_minor"] == o["total_khr"] == 26700  # 6.50 x 4100 = 26,650
    assert _pay(client, h, o, option="wechat", currency="KHR").status_code == 422


def test_khr_rejected_when_not_enabled(client, seeded, sim):
    h = _session(client, seeded)
    o = _checkout(client, h, seeded)
    assert _pay(client, h, o, currency="KHR").status_code == 422


def test_no_credentials_means_no_online_payment(client, seeded):
    pw.set_payway_override(None)
    h = _session(client, seeded)
    o = _checkout(client, h, seeded)
    assert _pay(client, h, o).status_code == 503
    assert client.get("/api/public/payment-options").json()["online_payment_available"] is False


def test_unpaid_order_expires_and_qr_is_closed(client, seeded, sim):
    h = _session(client, seeded)
    o = _checkout(client, h, seeded)
    tran = _pay(client, h, o).json()["payment"]["tran_id"]
    with seeded() as s:
        s.scalar(select(Order)).expires_at = utcnow() - timedelta(minutes=1)
        s.commit()
        assert expire_due_orders(s, sim.client()) == 1
    assert client.get(f"/api/public/orders/{o['public_id']}", headers=h).json()["status"] == "EXPIRED"
    assert sim.transactions[tran]["status"] == "CANCELLED"
    assert _pay(client, h, o).status_code == 409


def test_last_second_payment_is_honoured_at_expiry(client, seeded, sim):
    h = _session(client, seeded)
    o = _checkout(client, h, seeded)
    tran = _pay(client, h, o).json()["payment"]["tran_id"]
    sim.pay(tran)
    with seeded() as s:
        s.scalar(select(Order)).expires_at = utcnow() - timedelta(minutes=1)
        s.commit()
        expire_due_orders(s, sim.client())
    assert client.get(f"/api/public/orders/{o['public_id']}", headers=h).json()["status"] == "PAID"


def test_payway_error_is_reported_without_leaking_details(client, seeded):
    bad = PayWaySimulator()
    pw.set_payway_override(pw.PayWayClient(bad.merchant_id, "WRONG-KEY", "https://x.local",
                                           transport=__import__("httpx").MockTransport(bad.handle)))
    try:
        h = _session(client, seeded)
        o = _checkout(client, h, seeded)
        r = _pay(client, h, o)
        assert r.status_code == 502 and "hash" not in r.text.lower()
        with seeded() as s:
            assert s.scalar(select(Payment)).status == "FAILED"
    finally:
        pw.set_payway_override(None)


def test_simulator_endpoint_disabled_unless_switched_on(client, seeded):
    assert client.post("/api/dev/payway-simulator/pay", json={"tran_id": "1"}).status_code == 404


def test_production_refuses_simulator(monkeypatch):
    from app.config import Settings
    s = Settings(environment="production", payway_simulator=True)
    assert any("SIMULATOR" in p for p in s.validate_for_production())
