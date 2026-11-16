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


def notify(text: str) -> None:
    if sent_log is not None:
        sent_log.append(text)
        return
    if not enabled():
        return
    threading.Thread(target=_send, args=(text,), daemon=True).start()
