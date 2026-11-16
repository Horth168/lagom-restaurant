"""KHQR payments confirmed from ABA's Telegram notices, and cash at the counter."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import BankNotice, DiningTable, Order, Payment, Product
from app.models.base import utcnow
from app.models.enums import Role
from app.services import aba_notices, khqr
from app.services import telegram as tg
from scripts.seed_demo import seed

CHAT = "-1001234567890"
# A shop KHQR like the one ABA Mobile prints (static, with ABA's PayWay routing in tag 62/68)
_BODY = (khqr.tlv("00", "01") + khqr.tlv("01", "11")
         + khqr.tlv("29", khqr.tlv("00", "lagom@abaa") + khqr.tlv("01", "000123456"))
         + khqr.tlv("52", "5812") + khqr.tlv("53", "840") + khqr.tlv("58", "KH")
         + khqr.tlv("59", "LAGOM") + khqr.tlv("60", "Phnom Penh")
         + khqr.tlv("62", khqr.tlv("68", "PAYWAY@ABA:LAGOM01")) + "6304")
TEMPLATE = _BODY + khqr.crc16(_BODY)


@pytest.fixture
def khqr_on(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "khqr_template", TEMPLATE)
    monkeypatch.setattr(s, "payway_chat_id", CHAT)
    sent = []
    monkeypatch.setattr(tg, "sent_log", sent)
    return sent


@pytest.fixture
def seeded(SessionTest):
    with SessionTest() as s:
        seed(s, with_staff=False)
    return SessionTest


def _session(client, SessionTest, label="Table 01"):
    with SessionTest() as s:
        qr = s.scalar(select(DiningTable.qr_token).where(DiningTable.label == label))
    return {"X-Table-Session": client.post(f"/api/public/tables/{qr}/session", json={}).json()["session_token"]}


def _latte(SessionTest, qty=2):
    with SessionTest() as s:
        p = s.scalar(select(Product).where(Product.name_en == "Iced Latte"))
        g = {grp.name_en: {o.name_en: o.id for o in grp.options} for grp in p.option_groups}
    return {"product_id": p.id, "quantity": qty,
            "option_ids": [g["Size"]["Medium"], g["Sugar"]["50%"], g["Ice"]["Normal ice"]]}


def _order(client, h, SessionTest, qty=2, method="khqr"):
    o = client.post("/api/public/orders", headers=h, json={"items": [_latte(SessionTest, qty)],
                                                          "idempotency_key": uuid.uuid4().hex}).json()
    r = client.post(f"/api/public/orders/{o['public_id']}/pay", headers=h, json={"method": method, "currency": "USD"})
    assert r.status_code == 200, r.text
    return r.json()


def _aba(text, *, sender="PayWayByABA_bot", is_bot=True, chat=CHAT, when=None):
    return {"date": int((when or utcnow()).timestamp()), "text": text,
            "chat": {"id": int(chat), "type": "supergroup"}, "from": {"is_bot": is_bot, "username": sender}}


def _paid_text(amount="$6.50", trx="179468810879402", extra=""):
    return (f"{amount} paid by SOK DARA (*291) on Nov 16, 03:28 PM via ABA PAY at LAGOM. "
            f"Trx. ID: {trx}, APV: 929857.{extra}")


def _status(client, h, o):
    return client.get(f"/api/public/orders/{o['public_id']}", headers=h).json()["status"]


# ------------------------------------------------------------------ KHQR building
def test_khqr_has_exact_amount_reference_and_valid_checksum():
    qr = khqr.build(TEMPLATE, amount_minor=650, currency="USD", reference="LG261116-001-7Q", store_label="LAGOM")
    assert khqr.crc16(qr[:-4]) == qr[-4:]
    fields = dict(khqr.parse_tlv(qr))
    assert fields["01"] == "12" and fields["54"] == "6.50" and fields["53"] == "840"
    extra = dict(khqr.parse_tlv(fields["62"]))
    assert extra["01"] == "LG261116-001-7Q" and extra["68"] == "PAYWAY@ABA:LAGOM01"  # ABA routing kept
    assert dict(khqr.parse_tlv(fields["29"]))["00"] == "lagom@abaa"
    khr = dict(khqr.parse_tlv(khqr.build(TEMPLATE, amount_minor=26700, currency="KHR", reference="X")))
    assert khr["54"] == "26700" and khr["53"] == "116"


def test_bad_template_rejected():
    with pytest.raises(khqr.KhqrError):
        khqr.describe(TEMPLATE[:-4] + "0000")
    assert khqr.describe(TEMPLATE)["bakong_id"] == "lagom@abaa"


def test_parse_aba_messages():
    n = aba_notices.parse(_paid_text())
    assert (n.currency, n.amount_minor, n.trx, n.apv, n.payer) == ("USD", 650, "179468810879402", "929857", "SOK DARA")
    k = aba_notices.parse("៛26,700 paid by DARA (*12) on Nov 16, 03:28 PM via ABA PAY at LAGOM. Trx. ID: 5, APV: 1.")
    assert (k.currency, k.amount_minor) == ("KHR", 26700)
    assert aba_notices.parse("Hello, how are you?") is None


# ------------------------------------------------------------------ automatic confirmation
def test_khqr_order_paid_from_aba_notice(client, seeded, khqr_on):
    h = _session(client, seeded)
    o = _order(client, h, seeded)
    assert o["payment"]["method"] == "khqr" and o["payment"]["qr_string"].startswith("000201")
    assert dict(khqr.parse_tlv(o["payment"]["qr_string"]))["54"] == "6.50"
    with seeded() as db:
        assert aba_notices.handle(db, _aba(_paid_text())) == "matched"
    after = client.get(f"/api/public/orders/{o['public_id']}", headers=h).json()
    assert after["status"] == "PAID" and after["payment"]["reference"] == "179468810879402"
    assert any("Paid" in m for m in khqr_on)


def test_same_aba_transaction_cannot_pay_twice(client, seeded, khqr_on):
    h = _session(client, seeded)
    _order(client, h, seeded)
    o2 = _order(client, h, seeded)
    with seeded() as db:
        assert aba_notices.handle(db, _aba(_paid_text())) == "ambiguous"  # two $6.50 orders: no guessing
        assert aba_notices.handle(db, _aba(_paid_text())) == "duplicate"
    assert _status(client, h, o2) == "PENDING_PAYMENT"


def test_only_payway_bot_in_payment_group_is_trusted(client, seeded, khqr_on):
    h = _session(client, seeded)
    o = _order(client, h, seeded)
    with seeded() as db:
        assert aba_notices.handle(db, _aba(_paid_text(), sender="Sok", is_bot=False)) == "ignored"
        assert aba_notices.handle(db, _aba(_paid_text(), sender="FakePayWayBot")) == "ignored"
        assert aba_notices.handle(db, _aba(_paid_text(), chat="-100999")) == "ignored"
    assert _status(client, h, o) == "PENDING_PAYMENT"


def test_wrong_amount_does_not_confirm(client, seeded, khqr_on):
    h = _session(client, seeded)
    o = _order(client, h, seeded)
    with seeded() as db:
        assert aba_notices.handle(db, _aba(_paid_text(amount="$6.49"))) == "unmatched"
    assert _status(client, h, o) == "PENDING_PAYMENT"
    assert any("no waiting KHQR order" in m for m in khqr_on)


def test_reference_in_message_picks_the_right_order(client, seeded, khqr_on):
    h = _session(client, seeded)
    a = _order(client, h, seeded)
    b = _order(client, h, seeded)
    with seeded() as db:
        ref = db.scalar(select(Payment).join(Order).where(Order.public_id == b["public_id"])).tran_id
        assert aba_notices.handle(db, _aba(_paid_text(extra=f" Remark: {ref}"))) == "matched"
    assert _status(client, h, a) == "PENDING_PAYMENT" and _status(client, h, b) == "PAID"


def test_staff_resolve_ambiguous_payment(client, seeded, khqr_on, make_user, login):
    h = _session(client, seeded)
    a = _order(client, h, seeded)
    _order(client, h, seeded)
    with seeded() as db:
        aba_notices.handle(db, _aba(_paid_text()))
        notice_id = db.scalar(select(BankNotice.id))
    make_user(Role.KITCHEN)
    assert client.post(f"/api/admin/bank-notices/{notice_id}/assign", headers=login("kitchen@test.com"),
                       json={"order_public_id": a["public_id"]}).status_code == 403
    make_user(Role.CASHIER)
    cashier = login("cashier@test.com")
    r = client.post(f"/api/admin/bank-notices/{notice_id}/assign", headers=cashier, json={"order_public_id": a["public_id"]})
    assert r.status_code == 200, r.text
    assert _status(client, h, a) == "PAID"
    again = client.post(f"/api/admin/bank-notices/{notice_id}/assign", headers=cashier, json={"order_public_id": a["public_id"]})
    assert again.status_code == 409


def test_replaced_qr_is_not_matched(client, seeded, khqr_on):
    h = _session(client, seeded)
    o = _order(client, h, seeded)
    client.post(f"/api/public/orders/{o['public_id']}/pay", headers=h, json={"method": "cash", "currency": "USD"})
    with seeded() as db:
        assert aba_notices.handle(db, _aba(_paid_text())) == "unmatched"  # staff are told instead


def test_late_payment_within_grace_still_counts(client, seeded, khqr_on):
    h = _session(client, seeded)
    o = _order(client, h, seeded)
    with seeded() as db:
        order = db.scalar(select(Order))
        order.expires_at = utcnow() - timedelta(minutes=2)
        for p in order.payments:
            p.expires_at = order.expires_at
        db.commit()
    assert _status(client, h, o) == "EXPIRED"
    with seeded() as db:
        assert aba_notices.handle(db, _aba(_paid_text())) == "matched"
    assert _status(client, h, o) == "PAID"


def test_payment_long_after_expiry_needs_staff(client, seeded, khqr_on):
    h = _session(client, seeded)
    _order(client, h, seeded)
    with seeded() as db:
        assert aba_notices.handle(db, _aba(_paid_text(), when=utcnow() + timedelta(hours=3))) == "unmatched"


def test_khqr_unavailable_without_template(client, seeded):
    h = _session(client, seeded)
    o = client.post("/api/public/orders", headers=h, json={"items": [_latte(seeded)], "idempotency_key": uuid.uuid4().hex}).json()
    r = client.post(f"/api/public/orders/{o['public_id']}/pay", headers=h, json={"method": "khqr", "currency": "USD"})
    assert r.status_code == 503
    assert client.get("/api/public/payment-options").json()["khqr_available"] is False


def test_wechat_and_alipay_are_not_offered(client, seeded, khqr_on):
    h = _session(client, seeded)
    o = client.post("/api/public/orders", headers=h, json={"items": [_latte(seeded)], "idempotency_key": uuid.uuid4().hex}).json()
    for m in ("wechat", "alipay", "abapay_khqr"):
        assert client.post(f"/api/public/orders/{o['public_id']}/pay", headers=h,
                           json={"method": m, "currency": "USD"}).status_code == 422


# ------------------------------------------------------------------ cash
def test_cash_at_counter_confirmed_by_cashier(client, seeded, khqr_on, make_user, login):
    h = _session(client, seeded)
    o = _order(client, h, seeded, method="cash")
    assert o["status"] == "PENDING_PAYMENT" and o["payment"]["method"] == "cash"
    make_user(Role.KITCHEN)
    assert client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=login("kitchen@test.com"),
                       json={"received_minor": 1000}).status_code == 403
    make_user(Role.CASHIER)
    cashier = login("cashier@test.com")
    waiting = client.get("/api/admin/payments/waiting", headers=cashier).json()
    assert [w["number"] for w in waiting] == [o["number"]]
    assert client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=cashier,
                       json={"received_minor": 500}).status_code == 422  # not enough
    r = client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=cashier, json={"received_minor": 1000})
    assert r.json() == {"status": "PAID", "change_minor": 350, "currency": "USD"}
    assert _status(client, h, o) == "PAID"
    assert client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=cashier,
                       json={"received_minor": 1000}).status_code == 409


def test_cash_gives_more_time_than_khqr(client, seeded, khqr_on):
    h = _session(client, seeded)
    o = _order(client, h, seeded, method="cash")
    with seeded() as db:
        order = db.scalar(select(Order).where(Order.public_id == o["public_id"]))
        assert order.expires_at - order.created_at >= timedelta(minutes=55)


def test_cash_in_riel(client, seeded, khqr_on, owner_headers):
    h = _session(client, seeded)
    o = _order(client, h, seeded, method="cash")
    r = client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=owner_headers,
                    json={"currency": "KHR", "received_minor": 30000})
    assert r.json()["change_minor"] == 30000 - o["total_khr"]


# ------------------------------------------------------------------ test mode
def test_test_mode_endpoint_off_by_default(client, seeded, khqr_on):
    h = _session(client, seeded)
    o = _order(client, h, seeded)
    assert client.post("/api/dev/khqr/simulate-payment", headers=h, json={"public_id": o["public_id"]}).status_code == 404


def test_test_mode_uses_the_real_matcher(client, seeded, khqr_on, monkeypatch):
    monkeypatch.setattr(get_settings(), "khqr_test_mode", True)
    h = _session(client, seeded)
    o = _order(client, h, seeded)
    r = client.post("/api/dev/khqr/simulate-payment", headers=h, json={"public_id": o["public_id"]})
    assert r.json() == {"outcome": "matched"}
    assert _status(client, h, o) == "PAID"


def test_production_refuses_test_mode():
    from app.config import Settings
    assert any("TEST_MODE" in p for p in Settings(environment="production", khqr_test_mode=True).validate_for_production())
