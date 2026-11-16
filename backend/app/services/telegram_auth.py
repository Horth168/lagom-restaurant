"""Check that a Telegram Mini App login really comes from Telegram.

Telegram gives the Mini App a signed text ("initData"). The signature is an
HMAC-SHA256 made with a key derived from our bot token, so only Telegram (which
knows the token) can produce it. We recompute it on the server and also refuse
old data, so a copied login cannot be reused days later.
Spec: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_AGE_SECONDS = 24 * 3600


class TelegramAuthError(ValueError):
    pass


def validate_init_data(init_data: str, bot_token: str, now: float | None = None) -> dict:
    """Returns the Telegram user ({'id', 'first_name', …}) or raises TelegramAuthError."""
    if not init_data or not bot_token:
        raise TelegramAuthError("missing data")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received = pairs.pop("hash", "")
    if not received:
        raise TelegramAuthError("no signature")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise TelegramAuthError("bad signature")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        raise TelegramAuthError("bad date")
    if (now or time.time()) - auth_date > MAX_AGE_SECONDS:
        raise TelegramAuthError("expired")
    try:
        user = json.loads(pairs.get("user", "{}"))
    except ValueError:
        raise TelegramAuthError("bad user")
    if not isinstance(user, dict) or not user.get("id"):
        raise TelegramAuthError("no user")
    return user


def sign_for_tests(fields: dict, bot_token: str) -> str:
    """Build valid initData the way Telegram does (used by automated tests only)."""
    from urllib.parse import urlencode

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return urlencode({**fields, "hash": hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()})
