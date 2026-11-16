"""Kitchen Display System API and the live-update WebSockets."""
import asyncio
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import CurrentStaff, get_current_staff, user_from_token
from app.core.permissions import permissions_for, station_permission
from app.db import get_db
from app.models import Order, OrderItem, TableSession
from app.models.base import utcnow
from app.models.enums import ItemStatus, OrderStatus, Station
from app.services.kitchen import ACTIVE, KitchenProblem, item_action, station_action
from app.services.realtime import hub

router = APIRouter(tags=["kitchen"])


def _station(value: str) -> Station:
    try:
        return Station(value.upper())
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown station.")


def _require_station(staff: CurrentStaff, station: Station) -> None:
    if not staff.can(station_permission(station)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this station.")


def ticket(order: Order, station: Station) -> dict:
    mine = [i for i in order.items if i.station == station and i.status != ItemStatus.CANCELLED]
    others: dict[str, int] = {}
    for i in order.items:
        if i.station != station and i.status not in (ItemStatus.CANCELLED, ItemStatus.SERVED):
            others[i.station] = others.get(i.station, 0) + i.quantity
    states = {i.status for i in mine}
    if states <= {ItemStatus.SERVED}:
        stage = "served"
    elif states <= {ItemStatus.READY, ItemStatus.SERVED}:
        stage = "ready"
    elif ItemStatus.PREPARING in states or ItemStatus.READY in states:
        stage = "preparing"
    elif order.accepted_at:
        stage = "accepted"
    else:
        stage = "new"
    return {
        "public_id": order.public_id,
        "number": order.display_number,
        "table": order.table_label,
        "channel": order.channel,
        "order_status": order.status,
        "stage": stage,
        "paid_at": order.paid_at,
        "accepted_at": order.accepted_at,
        "customer_note": order.customer_note,
        "items": [
            {"id": i.id, "name": i.name_en, "name_km": i.name_km, "name_zh": i.name_zh, "quantity": i.quantity,
             "options": [o["name_en"] for o in i.options], "special_instructions": i.special_instructions,
             "status": i.status, "prep_minutes": i.prep_minutes}
            for i in mine
        ],
        "other_stations": others,
    }


@router.get("/api/kds/{station}")
def station_queue(station: str, done_minutes: int = Query(30, ge=0, le=240), db: Session = Depends(get_db),
                  staff: CurrentStaff = Depends(get_current_staff)):
    """Paid orders with items for this station, oldest first. Served tickets stay a short while (for recall)."""
    st = _station(station)
    _require_station(staff, st)
    since = utcnow() - timedelta(minutes=done_minutes)
    orders = db.scalars(
        select(Order)
        .join(OrderItem)
        .where(OrderItem.station == st,
               (Order.status.in_(ACTIVE)) | ((Order.status == OrderStatus.SERVED) & (Order.served_at >= since)))
        .options(selectinload(Order.items))
        .distinct()
        .order_by(Order.paid_at)
    ).all()
    tickets = [ticket(o, st) for o in orders]
    active = [t for t in tickets if t["stage"] != "served"]
    done = [t for t in tickets if t["stage"] == "served"][-20:]
    return {"station": st, "server_time": utcnow(), "active": active, "done": done}


class ItemStatusIn(BaseModel):
    status: ItemStatus


@router.post("/api/kds/{station}/orders/{public_id}/{action}")
def do_station_action(station: str, public_id: str, action: str, db: Session = Depends(get_db),
                      staff: CurrentStaff = Depends(get_current_staff)):
    st = _station(station)
    _require_station(staff, st)
    order = db.scalar(select(Order).where(Order.public_id == public_id))
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    try:
        station_action(db, order, st, action)
    except KitchenProblem as e:
        raise HTTPException(e.status_code, e.message)
    db.commit()
    return ticket(order, st)


@router.post("/api/kds/items/{item_id}/status")
def set_item_status(item_id: int, body: ItemStatusIn, db: Session = Depends(get_db),
                    staff: CurrentStaff = Depends(get_current_staff)):
    item = db.get(OrderItem, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found.")
    _require_station(staff, item.station)
    try:
        item_action(db, item, body.status)
    except KitchenProblem as e:
        raise HTTPException(e.status_code, e.message)
    db.commit()
    return ticket(item.order, item.station)


# ---------------------------------------------------------------- WebSockets
AUTH_TIMEOUT = 10


async def _first_message(ws: WebSocket) -> dict | None:
    try:
        return await asyncio.wait_for(ws.receive_json(), timeout=AUTH_TIMEOUT)
    except Exception:
        return None


async def _hold(ws: WebSocket) -> None:
    """Keep the connection open; the browser sends small 'ping' messages."""
    try:
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(ws)


@router.websocket("/api/ws/customer")
async def customer_socket(ws: WebSocket, db: Session = Depends(get_db)):
    """A customer's phone. First message: {"session": "<table session token>"}."""
    await ws.accept()
    hello = await _first_message(ws)
    token = (hello or {}).get("session") if isinstance(hello, dict) else None
    s = db.scalar(select(TableSession).where(TableSession.token == token)) if token else None
    if not s or s.closed_at is not None:
        await ws.close(code=4401)
        return
    channel = f"session:{s.id}"
    db.close()
    hub.subscribe(channel, ws)
    await ws.send_json({"type": "ready"})
    await _hold(ws)


@router.websocket("/api/ws/staff")
async def staff_socket(ws: WebSocket, db: Session = Depends(get_db)):
    """Staff screens. First message: {"token": "<login token>", "station": "KITCHEN" | null}."""
    await ws.accept()
    hello = await _first_message(ws)
    if not isinstance(hello, dict):
        await ws.close(code=4401)
        return
    user = user_from_token(db, hello.get("token"))
    if not user:
        await ws.close(code=4401)
        return
    perms = permissions_for(user.role, user.extra_permissions)
    station = hello.get("station")
    if station:
        try:
            st = Station(str(station).upper())
        except ValueError:
            await ws.close(code=4404)
            return
        if station_permission(st) not in perms:
            await ws.close(code=4403)
            return
        channel = f"station:{st}"
    else:
        if "orders.view" not in perms:
            await ws.close(code=4403)
            return
        channel = "staff"
    db.close()
    hub.subscribe(channel, ws)
    await ws.send_json({"type": "ready", "channel": channel})
    await _hold(ws)
