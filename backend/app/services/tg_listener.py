"""Reads ABA's PayWay bot messages from the shop's Telegram payment group.

Telegram never shows one bot's messages to another bot inside a group, so a normal
Telegram *user* account (a spare account or the owner's) signs in here (Telethon)
and passes every PayWay message to aba_notices.handle. It only reads that one
group and never sends anything.

Setup once: `python -m scripts.telegram_login`, then set TG_LISTENER_API_ID,
TG_LISTENER_API_HASH, TG_LISTENER_SESSION and PAYWAY_CHAT_ID. Off until all are set.

Reliability: on start and every few minutes it re-reads the group's recent messages,
so a payment that arrived while the server restarted is still picked up. Re-reading
is safe because each ABA transaction ID is processed only once.
"""
import asyncio
import logging
import threading
import time
from datetime import timezone

from app.config import get_settings

log = logging.getLogger("lagom.listener")
logging.getLogger("telethon").setLevel(logging.WARNING)

RESCAN_EVERY = 300  # seconds between safety re-reads
RESCAN_LIMIT = 40   # recent messages checked on each re-read
MAX_AGE = 6 * 3600  # older payments are left alone
STATUS: dict = {"state": "off", "account": "", "since": None, "last_payment": None, "error": ""}
_started = False


def clean_session(raw: str) -> str:
    """Forgive copy-paste damage (spaces, line breaks, quotes, a pasted 'TG_LISTENER_SESSION=')."""
    s = "".join((raw or "").split())
    if s.upper().startswith("TG_LISTENER_SESSION") and "=" in s[:30]:
        s = s.split("=", 1)[1]
    return s.strip("'\"`")


def to_message(*, chat_id: int, username: str | None, is_bot: bool, text: str, date) -> dict:
    ts = date.replace(tzinfo=date.tzinfo or timezone.utc).timestamp() if date else time.time()
    return {"date": int(ts), "text": text or "", "chat": {"id": chat_id, "type": "supergroup"},
            "from": {"is_bot": bool(is_bot), "username": username or ""}}


def process(msg: dict) -> str:
    from app.db import SessionLocal
    from app.services import aba_notices

    with SessionLocal() as db:
        try:
            result = aba_notices.handle(db, msg)
        except Exception:  # one bad message must never stop the listener
            db.rollback()
            log.exception("Listener: could not process a PayWay message")
            return "error"
    if result not in ("ignored", "not_a_payment", "duplicate"):
        STATUS["last_payment"] = {"result": result, "at": int(time.time())}
    return result


async def _run() -> None:
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

    s = get_settings()
    chat_id = int(s.payway_chat_id.strip())
    want = s.payway_bot_username.lstrip("@").lower()
    try:
        session = StringSession(clean_session(s.tg_listener_session))
        api_id = int(str(s.tg_listener_api_id).strip())
    except Exception:
        STATUS.update(state="error", error="TG_LISTENER_SESSION or TG_LISTENER_API_ID is not valid - run telegram_login again")
        log.error("Listener: %s", STATUS["error"])
        return
    client = TelegramClient(session, api_id, s.tg_listener_api_hash, catch_up=True, auto_reconnect=True,
                            connection_retries=None, retry_delay=5)

    async def handle(message) -> None:
        if not message or not (message.message or "").strip():
            return
        if message.date and time.time() - message.date.timestamp() > MAX_AGE:
            return
        sender = await message.get_sender()
        username = getattr(sender, "username", None) or ""
        if username.lower() != want:
            return
        msg = to_message(chat_id=chat_id, username=username, is_bot=bool(getattr(sender, "bot", False)),
                         text=message.message, date=message.date)
        await asyncio.to_thread(process, msg)

    @client.on(events.NewMessage(chats=chat_id))
    async def on_new(event):
        await handle(event.message)

    await client.connect()
    if not await client.is_user_authorized():
        STATUS.update(state="error", error="Session expired or invalid - run telegram_login again")
        log.error("Listener: %s", STATUS["error"])
        return
    me = await client.get_me()
    STATUS.update(state="connected", account=(f"@{me.username}" if me.username else me.first_name or "account"),
                  since=int(time.time()), error="")
    log.info("Payment listener connected as %s", STATUS["account"])
    await client.get_dialogs()

    async def rescan() -> None:
        while True:
            try:
                async for m in client.iter_messages(chat_id, limit=RESCAN_LIMIT):
                    await handle(m)
            except Exception as e:
                log.warning("Listener re-read failed: %s", e.__class__.__name__)
            await asyncio.sleep(RESCAN_EVERY)

    asyncio.create_task(rescan())
    await client.run_until_disconnected()


def _thread_main() -> None:
    while True:
        try:
            asyncio.run(_run())
        except Exception as e:
            STATUS.update(state="reconnecting", error=f"{e.__class__.__name__}: {str(e)[:200]}")
            log.warning("Listener stopped (%s), restarting in 30 s", e.__class__.__name__)
        if STATUS.get("state") == "error":
            return  # a bad session needs a new login; retrying would not help
        time.sleep(30)


def start() -> None:
    """Called at startup; does nothing unless the listener is configured."""
    global _started
    if _started or not get_settings().listener_enabled:
        return
    _started = True
    STATUS["state"] = "starting"
    threading.Thread(target=_thread_main, name="payway-listener", daemon=True).start()
