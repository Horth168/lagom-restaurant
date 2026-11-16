"""Live updates over WebSockets.

Channels:
    station:KITCHEN / station:DRINKS / station:DESSERT   kitchen display screens
    staff                                                 admin / POS screens (every order change)
    session:<id>                                          one customer's phone

Messages are small "something changed" notices ({"type": "order", "order": "<public id>"}).
Screens then reload the data through the normal API, which checks permissions. So a
missed message is never a problem: every screen also re-checks every few seconds.

One backend instance (free hosting) keeps subscribers in memory. With several
instances, replace `publish` with Redis pub/sub; nothing else needs to change.
"""
import asyncio
import json
import logging
import threading
from collections import defaultdict

from fastapi import WebSocket

log = logging.getLogger("lagom.realtime")


class Hub:
    def __init__(self):
        self._subs: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = threading.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.sent: list[tuple[str, dict]] = []  # recent messages (tests and debugging)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def subscribe(self, channel: str, ws: WebSocket) -> None:
        with self._lock:
            self._subs[channel].add(ws)

    def unsubscribe(self, ws: WebSocket) -> None:
        with self._lock:
            for subs in self._subs.values():
                subs.discard(ws)

    def count(self, channel: str) -> int:
        return len(self._subs.get(channel, ()))

    async def _deliver(self, channel: str, text: str) -> None:
        with self._lock:
            targets = list(self._subs.get(channel, ()))
        for ws in targets:
            try:
                await ws.send_text(text)
            except Exception:
                self.unsubscribe(ws)

    def publish(self, channel: str, message: dict) -> None:
        """Safe to call from normal (non-async) request code."""
        self.sent.append((channel, message))
        del self.sent[:-200]
        if self.loop is None or self.loop.is_closed():
            return
        text = json.dumps(message)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            self.loop.create_task(self._deliver(channel, text))
        else:
            asyncio.run_coroutine_threadsafe(self._deliver(channel, text), self.loop)


hub = Hub()


def order_changed(order, *, event: str = "order") -> None:
    """Tell every screen that cares about this order."""
    msg = {"type": event, "order": order.public_id, "status": order.status}
    stations = {i.station for i in order.items}
    for st in stations:
        hub.publish(f"station:{st}", msg)
    hub.publish("staff", msg)
    if order.table_session_id:
        hub.publish(f"session:{order.table_session_id}", msg)
