"""KHQR (Cambodia's national QR payment standard, EMVCo based).

LAGOM does not need an ABA PayWay merchant licence. The owner copies the text of
the shop's own ABA KHQR (the QR printed from ABA Mobile) once into KHQR_TEMPLATE.
For every order LAGOM makes a *dynamic* copy of it: same account and ABA routing
fields, plus the exact amount, currency, an order reference and an expiry time.
Any Cambodian banking app can pay it, and ABA then posts its usual
"$X paid by …" notification into the shop's Telegram group (see aba_notices.py).
"""
import time
from decimal import Decimal

CURRENCY_CODES = {"USD": "840", "KHR": "116"}
# Fields LAGOM sets per order; everything else is kept exactly as the bank printed it
_PER_ORDER = {"00", "01", "53", "54", "62", "63", "99"}


class KhqrError(ValueError):
    pass


def tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}" if value else ""


def crc16(data: str) -> str:
    """CRC-16/CCITT-FALSE, the checksum at the end of every KHQR (tag 63)."""
    crc = 0xFFFF
    for byte in data.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def ascii_only(value: str, max_len: int) -> str:
    return "".join(ch for ch in value if 32 <= ord(ch) < 127)[:max_len]


def parse_tlv(s: str) -> list[tuple[str, str]]:
    out, i = [], 0
    while i < len(s):
        if i + 4 > len(s) or not s[i:i + 4].isdigit():
            raise KhqrError("Not a valid KHQR code")
        tag, n = s[i:i + 2], int(s[i + 2:i + 4])
        if i + 4 + n > len(s):
            raise KhqrError("Not a valid KHQR code")
        out.append((tag, s[i + 4:i + 4 + n]))
        i += 4 + n
    return out


def describe(template: str) -> dict:
    """Validate the shop's KHQR and say which account it pays into."""
    t = (template or "").strip()
    if not t.startswith("000201") or len(t) < 30 or crc16(t[:-4]) != t[-4:].upper():
        raise KhqrError("This is not a valid KHQR code (checksum mismatch)")
    fields = dict(parse_tlv(t))
    if fields.get("58") != "KH" or not ({"29", "30"} & set(fields)):
        raise KhqrError("This QR is not a Cambodian KHQR payment code")
    acct = dict(parse_tlv(fields.get("29") or fields.get("30")))
    return {"name": fields.get("59", ""), "city": fields.get("60", ""), "bakong_id": acct.get("00", ""),
            "account": acct.get("01", ""), "bank": acct.get("02", "")}


def build(template: str, *, amount_minor: int, currency: str, reference: str, store_label: str = "",
          expiry_minutes: int = 15, now_ms: int | None = None) -> str:
    """A one-order KHQR for an exact amount (USD cents or whole riel)."""
    describe(template)
    if currency not in CURRENCY_CODES:
        raise KhqrError("KHQR supports USD or KHR")
    amount = f"{Decimal(amount_minor) / 100:.2f}" if currency == "USD" else str(int(amount_minor))
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    top = dict(parse_tlv(template.strip()))
    fields = {tag: val for tag, val in top.items() if tag not in _PER_ORDER}
    # Keep the bank's additional data (ABA puts its PayWay routing in sub-tag 68: that is what makes
    # ABA send the Telegram notification). Only the bill number (01) and store label (03) are ours.
    extra = dict(parse_tlv(top["62"])) if top.get("62") else {}
    extra["01"] = ascii_only(reference, 25)
    if store_label:
        extra["03"] = ascii_only(store_label, 25)
    fields.update({
        "00": "01",
        "01": "12",  # dynamic QR: one amount, one order
        "53": CURRENCY_CODES[currency],
        "54": amount,
        "62": "".join(tlv(k, extra[k]) for k in sorted(extra) if extra[k]),
        "99": tlv("00", str(now_ms)) + tlv("01", str(now_ms + expiry_minutes * 60_000)),
    })
    payload = "".join(tlv(tag, fields[tag]) for tag in sorted(fields)) + "6304"
    return payload + crc16(payload)
