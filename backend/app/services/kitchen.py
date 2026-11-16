"""Kitchen display logic: each station works on its own items of a shared order.

Example: Fried Rice -> KITCHEN, Iced Latte -> DRINKS, Cheesecake -> DESSERT.
The order is READY only when every item is ready, and SERVED when every item is served.
"""
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import Order, OrderItem
from app.models.base import utcnow
from app.models.enums import ItemStatus, OrderStatus, Station
from app.services import orders as order_service
from app.services.realtime import order_changed

ACTIVE = (OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY)
ACTIONS = ("accept", "start", "ready", "served", "recall")


class KitchenProblem(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def notify_after_commit(db: Session, order: Order, event_name: str = "order") -> None:
    """Send the live update only once the change is saved, so screens never reload too early."""
    @event.listens_for(db, "after_commit", once=True)
    def _send(_session):
        order_changed(order, event=event_name)


def _on_paid(db: Session, order: Order) -> None:
    notify_after_commit(db, order, "new_order")


# New paid orders appear on the kitchen screens instantly
if _on_paid not in order_service.paid_listeners:
    order_service.paid_listeners.append(_on_paid)


def recompute(order: Order) -> None:
    """Order status follows its items."""
    items = [i for i in order.items if i.status != ItemStatus.CANCELLED]
    now = utcnow()
    if not items:
        return
    if all(i.status == ItemStatus.SERVED for i in items):
        order.status = OrderStatus.SERVED
        order.served_at = order.served_at or now
    elif all(i.status in (ItemStatus.READY, ItemStatus.SERVED) for i in items):
        order.status = OrderStatus.READY
        order.ready_at = order.ready_at or now
    elif any(i.status != ItemStatus.QUEUED for i in items):
        order.status = OrderStatus.PREPARING
        order.ready_at = None
    else:
        order.status = OrderStatus.PAID
        order.ready_at = None
    if order.status != OrderStatus.PAID and order.accepted_at is None:
        order.accepted_at = now


def _set(item: OrderItem, status: ItemStatus) -> None:
    now = utcnow()
    if status == ItemStatus.PREPARING and item.started_at is None:
        item.started_at = now
    if status == ItemStatus.READY:
        item.ready_at = now
    if status == ItemStatus.PREPARING:
        item.ready_at = None
    item.status = status


def station_action(db: Session, order: Order, station: Station, action: str) -> None:
    if order.status not in ACTIVE:
        raise KitchenProblem("This order is not in the kitchen queue.")
    if action not in ACTIONS:
        raise KitchenProblem("Unknown action.", 422)
    mine = [i for i in order.items if i.station == station and i.status != ItemStatus.CANCELLED]
    if not mine:
        raise KitchenProblem("This order has nothing for this station.", 404)

    if action == "accept":
        order.accepted_at = order.accepted_at or utcnow()
    elif action == "start":
        for i in mine:
            if i.status == ItemStatus.QUEUED:
                _set(i, ItemStatus.PREPARING)
    elif action == "ready":
        for i in mine:
            if i.status in (ItemStatus.QUEUED, ItemStatus.PREPARING):
                _set(i, ItemStatus.READY)
    elif action == "served":
        if any(i.status not in (ItemStatus.READY, ItemStatus.SERVED) for i in mine):
            raise KitchenProblem("Mark the items ready before serving.")
        for i in mine:
            _set(i, ItemStatus.SERVED)
    elif action == "recall":
        for i in mine:
            if i.status == ItemStatus.READY:
                _set(i, ItemStatus.PREPARING)
    recompute(order)
    notify_after_commit(db, order)


def item_action(db: Session, item: OrderItem, status: ItemStatus) -> None:
    order = item.order
    if order.status not in ACTIVE:
        raise KitchenProblem("This order is not in the kitchen queue.")
    if status not in (ItemStatus.QUEUED, ItemStatus.PREPARING, ItemStatus.READY, ItemStatus.SERVED):
        raise KitchenProblem("Unknown status.", 422)
    if status == ItemStatus.SERVED and item.status != ItemStatus.READY:
        raise KitchenProblem("Mark the item ready before serving.")
    _set(item, status)
    recompute(order)
    notify_after_commit(db, order)
