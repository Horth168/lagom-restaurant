"""Kitchen display: station routing, item tracking, order status, live updates."""
import uuid

import pytest
from sqlalchemy import select

from app.models import DiningTable, Product
from app.models.enums import Role
from scripts.seed_demo import seed


@pytest.fixture
def seeded(SessionTest):
    with SessionTest() as s:
        seed(s, with_staff=False)
    return SessionTest


@pytest.fixture
def staff(make_user, login):
    """Login headers for each role."""
    out = {}
    for role in (Role.OWNER, Role.CASHIER, Role.KITCHEN, Role.DRINKS):
        make_user(role)
        out[role] = login(f"{role.value.lower()}@test.com")
    return out


def _session(client, SessionTest, label="Table 01"):
    with SessionTest() as s:
        qr = s.scalar(select(DiningTable.qr_token).where(DiningTable.label == label))
    body = client.post(f"/api/public/tables/{qr}/session", json={}).json()
    return {"X-Table-Session": body["session_token"]}, body["session_token"]


def _line(SessionTest, name, picks=()):
    with SessionTest() as s:
        p = s.scalar(select(Product).where(Product.name_en == name))
        groups = {g.name_en: {o.name_en: o.id for o in g.options} for g in p.option_groups}
    return {"product_id": p.id, "quantity": 1, "option_ids": [groups[g][o] for g, o in picks]}


MIXED = [("Fried Rice", [("Protein", "Chicken")]),
         ("Iced Latte", [("Size", "Medium"), ("Sugar", "50%"), ("Ice", "Normal ice")]),
         ("Basque Cheesecake", [])]


def _paid_order(client, SessionTest, staff, h, items=MIXED):
    o = client.post("/api/public/orders", headers=h, json={
        "items": [_line(SessionTest, n, p) for n, p in items], "idempotency_key": uuid.uuid4().hex}).json()
    client.post(f"/api/public/orders/{o['public_id']}/pay", headers=h, json={"method": "cash", "currency": "USD"})
    r = client.post(f"/api/admin/orders/{o['public_id']}/cash", headers=staff[Role.CASHIER], json={"received_minor": 100000})
    assert r.status_code == 200, r.text
    return o


def _queue(client, staff_h, station):
    r = client.get(f"/api/kds/{station}", headers=staff_h)
    assert r.status_code == 200, r.text
    return r.json()["active"]


def _act(client, staff_h, station, o, action):
    return client.post(f"/api/kds/{station}/orders/{o['public_id']}/{action}", headers=staff_h)


def _customer(client, h, o):
    return client.get(f"/api/public/orders/{o['public_id']}", headers=h).json()


def test_items_are_routed_to_their_station(client, seeded, staff):
    h, _ = _session(client, seeded)
    _paid_order(client, seeded, staff, h)
    kitchen = _queue(client, staff[Role.KITCHEN], "kitchen")
    drinks = _queue(client, staff[Role.DRINKS], "drinks")
    dessert = _queue(client, staff[Role.KITCHEN], "dessert")
    assert [i["name"] for i in kitchen[0]["items"]] == ["Fried Rice"]
    assert kitchen[0]["items"][0]["options"] == ["Chicken"]
    assert [i["name"] for i in drinks[0]["items"]] == ["Iced Latte"]
    assert [i["name"] for i in dessert[0]["items"]] == ["Basque Cheesecake"]
    assert kitchen[0]["other_stations"] == {"DRINKS": 1, "DESSERT": 1}
    assert kitchen[0]["number"] == drinks[0]["number"]  # one original order


def test_unpaid_orders_never_reach_the_kitchen(client, seeded, staff):
    h, _ = _session(client, seeded)
    client.post("/api/public/orders", headers=h, json={"items": [_line(seeded, "Fried Rice", [("Protein", "Pork")])],
                                                       "idempotency_key": uuid.uuid4().hex})
    assert _queue(client, staff[Role.KITCHEN], "kitchen") == []


def test_station_permissions(client, seeded, staff):
    assert client.get("/api/kds/drinks", headers=staff[Role.KITCHEN]).status_code == 403
    assert client.get("/api/kds/kitchen", headers=staff[Role.DRINKS]).status_code == 403
    assert client.get("/api/kds/kitchen", headers=staff[Role.CASHIER]).status_code == 403
    assert client.get("/api/kds/kitchen").status_code == 401
    assert client.get("/api/kds/nowhere", headers=staff[Role.OWNER]).status_code == 404


def test_order_ready_only_when_every_station_is_ready(client, seeded, staff):
    h, _ = _session(client, seeded)
    o = _paid_order(client, seeded, staff, h)
    k, d = staff[Role.KITCHEN], staff[Role.DRINKS]

    assert _act(client, k, "kitchen", o, "accept").json()["stage"] == "accepted"
    assert _customer(client, h, o)["accepted_at"]  # customer sees "Order received"
    assert _act(client, k, "kitchen", o, "start").json()["stage"] == "preparing"
    assert _customer(client, h, o)["status"] == "PREPARING"

    _act(client, k, "kitchen", o, "ready")
    _act(client, d, "drinks", o, "ready")
    assert _customer(client, h, o)["status"] == "PREPARING"  # cheesecake still waiting
    _act(client, k, "dessert", o, "ready")
    after = _customer(client, h, o)
    assert after["status"] == "READY" and after["ready_at"]


def test_serving_requires_ready_and_completes_order(client, seeded, staff):
    h, _ = _session(client, seeded)
    o = _paid_order(client, seeded, staff, h)
    k, d = staff[Role.KITCHEN], staff[Role.DRINKS]
    assert _act(client, k, "kitchen", o, "served").status_code == 409
    for st, who in (("kitchen", k), ("drinks", d), ("dessert", k)):
        _act(client, who, st, o, "ready")
    _act(client, d, "drinks", o, "served")  # drinks go out first
    assert _customer(client, h, o)["status"] == "READY"
    _act(client, k, "kitchen", o, "served")
    _act(client, k, "dessert", o, "served")
    assert _customer(client, h, o)["status"] == "SERVED"
    q = client.get("/api/kds/kitchen", headers=k).json()
    assert q["active"] == [] and q["done"][0]["public_id"] == o["public_id"]


def test_recall_and_item_level_tracking(client, seeded, staff):
    h, _ = _session(client, seeded)
    o = _paid_order(client, seeded, staff, h, items=[("Fried Rice", [("Protein", "Beef")]), ("French Fries", [])])
    k = staff[Role.KITCHEN]
    items = _queue(client, k, "kitchen")[0]["items"]
    assert len(items) == 2
    r = client.post(f"/api/kds/items/{items[0]['id']}/status", headers=k, json={"status": "READY"})
    assert r.json()["stage"] == "preparing"  # one of two ready
    r = client.post(f"/api/kds/items/{items[1]['id']}/status", headers=k, json={"status": "READY"})
    assert r.json()["stage"] == "ready" and _customer(client, h, o)["status"] == "READY"
    assert _act(client, k, "kitchen", o, "recall").json()["stage"] == "preparing"
    assert _customer(client, h, o)["status"] == "PREPARING"
    # a drinks-only user cannot touch kitchen items
    assert client.post(f"/api/kds/items/{items[0]['id']}/status", headers=staff[Role.DRINKS],
                       json={"status": "READY"}).status_code == 403


# ------------------------------------------------------------------ WebSockets
def test_kitchen_screen_gets_live_new_order(client, seeded, staff):
    token = staff[Role.KITCHEN]["Authorization"].split()[1]
    with client.websocket_connect("/api/ws/staff") as ws:
        ws.send_json({"token": token, "station": "KITCHEN"})
        assert ws.receive_json() == {"type": "ready", "channel": "station:KITCHEN"}
        h, _ = _session(client, seeded)
        o = _paid_order(client, seeded, staff, h)
        msg = ws.receive_json()
        assert msg["type"] == "new_order" and msg["order"] == o["public_id"]


def test_staff_socket_rejects_bad_token_and_wrong_station(client, seeded, staff):
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/api/ws/staff") as ws:
        ws.send_json({"token": "nonsense", "station": "KITCHEN"})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401
    with client.websocket_connect("/api/ws/staff") as ws:
        ws.send_json({"token": staff[Role.KITCHEN]["Authorization"].split()[1], "station": "DRINKS"})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4403


def test_customer_phone_gets_only_its_own_updates(client, seeded, staff):
    mine_h, mine_token = _session(client, seeded)
    other_h, other_token = _session(client, seeded)
    with client.websocket_connect("/api/ws/customer") as mine, client.websocket_connect("/api/ws/customer") as other:
        mine.send_json({"session": mine_token})
        other.send_json({"session": other_token})
        assert mine.receive_json()["type"] == "ready" and other.receive_json()["type"] == "ready"
        o = _paid_order(client, seeded, staff, mine_h)
        assert mine.receive_json()["order"] == o["public_id"]
        _act(client, staff[Role.KITCHEN], "kitchen", o, "start")
        msg = mine.receive_json()
        assert msg["status"] == "PREPARING"
        # the other phone heard nothing: the next thing it receives is its own pong
        other.send_text("ping")
        assert other.receive_json() == {"type": "pong"}


def test_customer_socket_rejects_unknown_session(client, seeded):
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/api/ws/customer") as ws:
        ws.send_json({"session": "not-a-session"})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401
