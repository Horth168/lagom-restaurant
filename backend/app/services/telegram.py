"""Messages to the owner/staff Telegram chat (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID).

Sending happens in a background thread and never raises: a Telegram problem must
never block an order or a payment. Messages never contain secrets or full payer
account numbers.
"""
import html
import logging
import threading

import httpx

from app.config import get_settings

log = logging.getLogger("lagom.telegram")

# Tests replace this list to capture messages instead of sending them
sent_log: list[str] | None = None


def enabled() -> bool:
    s = get_settings()
    return bool(s.telegram_bot_token and s.telegram_chat_id)


def esc(text: object) -> str:
    return html.escape(str(text), quote=False)


def _send(text: str) -> None:
    s = get_settings()
    try:
        httpx.post(
            f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage",
            json={"chat_id": s.telegram_chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15,
        )
    except httpx.HTTPError as e:
        log.warning("Telegram send failed: %s", e.__class__.__name__)


def send_now(text: str, chat_id: str | None = None) -> tuple[bool, str]:
    """Send and wait for Telegram's answer (used by the 'send test message' button)."""
    s = get_settings()
    if sent_log is not None:
        sent_log.append(text)
        return True, ""
    try:
        r = httpx.post(f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage",
                       json={"chat_id": chat_id or s.telegram_chat_id, "text": text, "parse_mode": "HTML"}, timeout=15)
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        return False, e.__class__.__name__
    return bool(data.get("ok")), str(data.get("description", ""))[:200]


def send_to_user(user_id: str, text: str) -> None:
    """Message one Telegram user (e.g. 'your order is ready'). Background, never raises."""
    if sent_log is not None:
        sent_log.append(f"to {user_id}: {text}")
        return
    if not get_settings().telegram_bot_token:
        return
    threading.Thread(target=lambda: send_now(text, chat_id=user_id), daemon=True).start()


def notify(text: str) -> None:
    if sent_log is not None:
        sent_log.append(text)
        return
    if not enabled():
        return
    threading.Thread(target=_send, args=(text,), daemon=True).start()
