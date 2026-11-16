"""Automatic KHQR confirmation from ABA's Telegram payment notifications.

ABA's "PayWay by ABA" bot posts a message for every payment into a Telegram group
linked in ABA Mobile, for example:

    $3.25 paid by SOK DARA (*291) on Nov 16, 03:28 PM via ABA PAY at LAGOM.
    Trx. ID: 179468810879402, APV: 929857.

A listener account (tg_listener.py) passes those messages here. Safety rules:

* Only the configured group (PAYWAY_CHAT_ID) counts, and only messages sent by
  ABA's PayWay bot itself. A person typing "$3.25 paid by …" is ignored.
* Every ABA transaction ID is stored once (database unique key): one payment can
  never confirm two orders, even if the message is read again after a restart.
* An order is confirmed only if EXACTLY ONE waiting KHQR order asks for that exact
  amount and currency and its QR was live when the money arrived. If ABA's message
  contains the order reference from the QR, only that order is considered.
* Several possible orders, or none: nothing is guessed. Staff are told on Telegram
  and decide in the dashboard.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import BankNotice, Order, Payment
from app.models.base import utcnow
from app.models.enums import Currency, OrderStatus, PaymentProvider, PaymentStatus
from app.services import telegram as tg
from app.services.orders import log_event, mark_order_paid, run_paid_listeners

log = logging.getLogger("lagom.aba")

PATTERN = re.compile(
    r"(?P<cur>\$|USD|៛|KHR)\s?(?P<amount>\d[\d,]*(?:\.\d{1,2})?)\s+paid\s+by\s+(?P<payer>.+?)"
    r"(?:\s+\((?P<account>[^)]*)\))?\s+on\s+(?P<when>.+?)\s+via\s+(?P<via>.+?)\s+at\s+(?P<merchant>.+?)\.?\s*"
    r"Trx\.?\s*ID:?\s*(?P<trx>\d+)(?:\s*,\s*APV:?\s*(?P<apv>\d+))?",
    re.IGNORECASE | re.DOTALL,
)
REFERENCE = re.compile(r"\bLG\d{6}-\d{3}-[A-Z0-9]{2}\b")
GRACE = timedelta(minutes=10)  # money that lands a little after the QR's countdown still counts


@dataclass
class Notice:
    currency: Currency
    amount_minor: int
    payer: str
    account: str
    trx: str
    apv: str
    text: str


def parse(text: str) -> Notice | None:
    m = PATTERN.search(text or "")
    if not m:
        return None
    try:
        amount = Decimal(m["amount"].replace(",", ""))
    except InvalidOperation:
        return None
    currency = Currency.KHR if m["cur"].upper() in ("៛", "KHR") else Currency.USD
    minor = int(amount) if currency == Currency.KHR else int((amount * 100).to_integral_value())
    return Notice(currency, minor, " ".join(m["payer"].split())[:120], (m["account"] or "").strip()[:40],
                  m["trx"], m["apv"] or "", text[:2000])


def from_payway(msg: dict) -> bool:
    """True only for a genuine PayWay-bot message in our payment group."""
    s = get_settings()
    chat = msg.get("chat") or {}
    if not s.payway_chat_id.strip() or str(chat.get("id")) != s.payway_chat_id.strip():
        return False
    sender = msg.get("from") or {}
    want = s.payway_bot_username.lstrip("@").lower()
    return bool(sender.get("is_bot")) and (sender.get("username") or "").lower() == want


def _money(currency: Currency, minor: int) -> str:
    return f"${minor / 100:,.2f}" if currency == Currency.USD else f"{minor:,}៛"


def candidates(db: Session, notice: Notice, received_at: datetime) -> list[Payment]:
    rows = db.scalars(
        select(Payment).join(Order).where(
            Payment.provider == PaymentProvider.ABA_KHQR,
            Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.EXPIRED]),
            Payment.currency == notice.currency,
            Payment.amount_minor == notice.amount_minor,
            Order.status.in_([OrderStatus.PENDING_PAYMENT, OrderStatus.EXPIRED]),
        )
    ).all()
    refs = set(REFERENCE.findall(notice.text))
    if refs:
        rows = [p for p in rows if p.tran_id in refs]
    out = []
    for p in rows:
        latest = max(p.order.payments, key=lambda x: x.id)
        if latest.id != p.id:
            continue  # an older QR the customer replaced
        start = p.created_at - timedelta(minutes=1)
        end = (p.expires_at or p.created_at + timedelta(hours=1)) + GRACE
        if start <= received_at <= end:
            out.append(p)
    return out


def confirm(db: Session, payment: Payment, *, trx: str, note: str, source: str) -> bool:
    """Mark a KHQR payment approved and its order PAID (exactly once)."""
    payment.status = PaymentStatus.APPROVED
    payment.approved_at = utcnow()
    payment.provider_reference = trx
    log_event(db, payment, "VERIFY", {"trx": trx, "source": source}, verified=True, note=note)
    if mark_order_paid(db, payment.order, payment):
        run_paid_listeners(db, payment.order)
        return True
    return False


def handle(db: Session, msg: dict) -> str:
    """Process one Telegram message. Returns what happened (for logs and tests)."""
    if not from_payway(msg):
        return "ignored"
    received_at = datetime.fromtimestamp(msg.get("date") or utcnow().timestamp(), tz=timezone.utc)
    return process(db, msg.get("text") or msg.get("caption") or "", received_at)


def process(db: Session, text: str, received_at: datetime) -> str:
    """Match one ABA payment text (already known to come from ABA's bot) to an order."""
    notice = parse(text)
    if notice is None:
        return "not_a_payment"
    if db.scalar(select(BankNotice.id).where(BankNotice.trx_id == notice.trx)):
        return "duplicate"

    found = candidates(db, notice, received_at)
    outcome = "matched" if len(found) == 1 else "ambiguous" if found else "unmatched"
    record = BankNotice(trx_id=notice.trx, apv=notice.apv, currency=notice.currency, amount_minor=notice.amount_minor,
                        payer=notice.payer, payer_account=notice.account, received_at=received_at,
                        text=notice.text, outcome=outcome)
    db.add(record)
    try:
        db.flush()  # the unique trx_id makes a second copy of this payment fail right here
    except IntegrityError:
        db.rollback()
        return "duplicate"

    money = _money(notice.currency, notice.amount_minor)
    who = tg.esc(notice.payer) + (f" ({tg.esc(notice.account)})" if notice.account else "")
    if outcome == "matched":
        payment = found[0]
        db.refresh(payment.order, with_for_update=True)  # lock, then re-check
        record.payment_id = payment.id
        if not confirm(db, payment, trx=notice.trx, source="aba-telegram",
                       note=f"{money} paid by {notice.payer} {notice.account} · ABA Trx {notice.trx}".strip()):
            record.outcome = "unmatched"
            outcome = "unmatched"
        else:
            o = payment.order
            tg.notify(f"✅ <b>Paid</b> · Order #{o.display_number} · {tg.esc(o.table_label)}\n"
                      f"{money} from {who}\nABA Trx {tg.esc(notice.trx)} · sent to the kitchen")
    if outcome == "ambiguous":
        lines = "\n".join(f"• #{p.order.display_number} · {tg.esc(p.order.table_label)}" for p in found)
        tg.notify(f"⚠️ <b>{money} received from {who}</b>, but {len(found)} orders are waiting for that exact "
                  f"amount, so LAGOM did not guess.\n{lines}\nABA Trx {tg.esc(notice.trx)}\n"
                  "Confirm the right order in the dashboard (Payments → Bank notices).")
    elif outcome == "unmatched":
        tg.notify(f"ℹ️ <b>{money} received from {who}</b>, but no waiting KHQR order matches "
                  f"(ABA Trx {tg.esc(notice.trx)}). If it belongs to an order, assign it in the dashboard.")
    db.commit()
    log.info("ABA notice %s %s Trx %s -> %s", notice.currency, notice.amount_minor, notice.trx, outcome)
    return outcome


def assign(db: Session, notice: BankNotice, payment: Payment, user_id: int) -> None:
    """Staff decision for an ambiguous/unmatched notice. Amount and currency must still match."""
    if notice.outcome not in ("ambiguous", "unmatched"):
        raise ValueError("This bank payment is already linked to an order.")
    if payment.provider != PaymentProvider.ABA_KHQR or payment.status not in (PaymentStatus.PENDING, PaymentStatus.EXPIRED):
        raise ValueError("That order is not waiting for a KHQR payment.")
    if payment.currency != notice.currency or payment.amount_minor != notice.amount_minor:
        raise ValueError("The amount does not match this order.")
    if not confirm(db, payment, trx=notice.trx_id, source=f"staff:{user_id}",
                   note=f"Assigned by staff from ABA Trx {notice.trx_id}"):
        raise ValueError("That order was already paid.")
    notice.outcome = "resolved"
    notice.payment_id = payment.id
    notice.resolved_by_user_id = user_id


def simulated_text(payment: Payment) -> str:
    """DEVELOPMENT ONLY (KHQR_TEST_MODE): a payment text shaped exactly like ABA's."""
    import secrets

    amount = f"${payment.amount_minor / 100:,.2f}" if payment.currency == Currency.USD else f"KHR {payment.amount_minor:,}"
    return (f"{amount} paid by TEST CUSTOMER (*000) on {utcnow():%b %d, %I:%M %p} via ABA PAY at LAGOM. "
            f"Trx. ID: {secrets.randbelow(10**15):015d}, APV: {secrets.randbelow(10**6):06d}.")
