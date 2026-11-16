"""ABA PayWay client (official API, https://developer.payway.com.kh/).

Used endpoints:
- QR API            POST /api/payment-gateway/v1/payments/generate-qr
- Check transaction POST /api/payment-gateway/v1/payments/check-transaction-2
- Close transaction POST /api/payment-gateway/v1/payments/close-transaction
- Refund            POST /api/merchant-portal/merchant-access/online-transaction/refund

Security notes
- The API key never leaves the backend.
- PayWay's payment notification (callback) is NOT signed, so it is never trusted
  by itself: every payment is confirmed with the Check Transaction API, as
  PayWay's documentation requires.
"""
import base64
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import httpx

from app.config import get_settings

log = logging.getLogger("lagom.payway")

GENERATE_QR = "/api/payment-gateway/v1/payments/generate-qr"
CHECK_TRANSACTION = "/api/payment-gateway/v1/payments/check-transaction-2"
CLOSE_TRANSACTION = "/api/payment-gateway/v1/payments/close-transaction"
REFUND = "/api/merchant-portal/merchant-access/online-transaction/refund"

QR_OPTIONS = {"abapay_khqr", "wechat", "alipay"}
USD_ONLY_OPTIONS = {"wechat", "alipay"}


class PayWayError(Exception):
    def __init__(self, message: str, code: str | None = None, payload: dict | None = None):
        super().__init__(message)
        self.code = code
        self.payload = payload or {}


@dataclass
class QrResult:
    qr_string: str
    abapay_deeplink: str
    app_store: str
    play_store: str
    raw: dict


@dataclass
class CheckResult:
    found: bool
    status: str  # APPROVED, PRE-AUTH, PENDING, DECLINED, REFUNDED, CANCELLED, NOT_FOUND
    total_amount: Decimal | None
    payment_currency: str
    apv: str
    refund_amount: Decimal
    raw: dict


def req_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def sign(api_key: str, *values: str) -> str:
    """Base64( HMAC-SHA512( concatenated values, api_key ) ) – PayWay's hash format."""
    msg = "".join(values).encode("utf-8")
    return base64.b64encode(hmac.new(api_key.encode("utf-8"), msg, hashlib.sha512).digest()).decode()


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode()


def amount_value(amount_minor: int, currency: str) -> int | float:
    """Amount as PayWay expects it: USD in dollars (e.g. 8.5), KHR in whole riel."""
    if currency == "KHR":
        return int(amount_minor)
    value = Decimal(amount_minor) / 100
    return int(value) if value == value.to_integral() else float(value)


def amount_for_hash(value: int | float) -> str:
    """The amount exactly as it appears in the JSON body (e.g. 8.5, 10, 0.01)."""
    return json.dumps(value)


def minor_units(amount, currency: str) -> int:
    d = Decimal(str(amount))
    return int(d) if currency == "KHR" else int((d * 100).to_integral_value())


def scrub(payload: dict) -> dict:
    """Remove secrets/personal data before storing request/response logs."""
    hidden = {"hash", "merchant_auth", "qrImage", "email", "phone", "first_name", "last_name", "payer_account"}
    return {k: ("***" if k in hidden and v else v) for k, v in payload.items()}


class PayWayClient:
    def __init__(self, merchant_id: str, api_key: str, base_url: str, rsa_public_key: str = "",
                 transport: httpx.BaseTransport | None = None):
        self.merchant_id = merchant_id
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.rsa_public_key = rsa_public_key
        self._transport = transport

    def _post(self, path: str, body: dict) -> dict:
        try:
            with httpx.Client(base_url=self.base_url, timeout=20, transport=self._transport) as c:
                r = c.post(path, json=body, headers={"Content-Type": "application/json"})
        except httpx.HTTPError as e:
            raise PayWayError(f"Cannot reach ABA PayWay: {e.__class__.__name__}") from e
        try:
            data = r.json()
        except ValueError:
            raise PayWayError(f"Unexpected PayWay response (HTTP {r.status_code})")
        if r.status_code >= 400 and "status" not in data:
            raise PayWayError(f"PayWay HTTP {r.status_code}", payload=data)
        return data

    # -------------------------------------------------------------- QR payment
    def generate_qr(self, *, tran_id: str, amount_minor: int, currency: str, payment_option: str,
                    items: list[dict], callback_url: str, lifetime_minutes: int,
                    return_params: str = "") -> tuple[QrResult, dict]:
        if payment_option not in QR_OPTIONS:
            raise PayWayError("Unsupported payment option")
        if currency == "KHR" and payment_option in USD_ONLY_OPTIONS:
            raise PayWayError("WeChat Pay and Alipay only accept USD")
        t = req_time()
        amount = amount_value(amount_minor, currency)
        fields = {
            "req_time": t,
            "merchant_id": self.merchant_id,
            "tran_id": tran_id,
            "amount": amount,
            "items": b64(json.dumps(items, ensure_ascii=False)),
            "first_name": "", "last_name": "", "email": "", "phone": "",
            "purchase_type": "purchase",
            "payment_option": payment_option,
            "callback_url": b64(callback_url),
            "return_deeplink": "",
            "currency": currency,
            "custom_fields": "",
            "return_params": return_params,
            "payout": "",
            "lifetime": max(3, lifetime_minutes),
            "qr_image_template": "template3_color",
        }
        order = ["req_time", "merchant_id", "tran_id", "amount", "items", "first_name", "last_name", "email",
                 "phone", "purchase_type", "payment_option", "callback_url", "return_deeplink", "currency",
                 "custom_fields", "return_params", "payout", "lifetime", "qr_image_template"]
        values = [amount_for_hash(amount) if k == "amount" else str(fields[k]) for k in order]
        body = {**fields, "hash": sign(self.api_key, *values)}
        data = self._post(GENERATE_QR, body)
        status = data.get("status") or {}
        if str(status.get("code")) != "0":
            raise PayWayError(status.get("message") or "PayWay refused the payment request",
                              code=str(status.get("code")), payload=scrub(data))
        return (QrResult(qr_string=data["qrString"], abapay_deeplink=data.get("abapay_deeplink", ""),
                         app_store=data.get("app_store", ""), play_store=data.get("play_store", ""),
                         raw=scrub(data)), scrub(body))

    # -------------------------------------------------------------- verification
    def check_transaction(self, tran_id: str) -> CheckResult:
        t = req_time()
        body = {"req_time": t, "merchant_id": self.merchant_id, "tran_id": tran_id,
                "hash": sign(self.api_key, t, self.merchant_id, tran_id)}
        data = self._post(CHECK_TRANSACTION, body)
        status = data.get("status") or {}
        code = str(status.get("code"))
        if code == "6":
            return CheckResult(False, "NOT_FOUND", None, "", "", Decimal(0), scrub(data))
        if code != "00":
            raise PayWayError(status.get("message") or "Check transaction failed", code=code, payload=scrub(data))
        d = data.get("data") or {}
        return CheckResult(
            found=True,
            status=str(d.get("payment_status", "")).upper(),
            total_amount=Decimal(str(d["total_amount"])) if d.get("total_amount") is not None else None,
            payment_currency=str(d.get("payment_currency", "")).upper(),
            apv=str(d.get("apv") or ""),
            refund_amount=Decimal(str(d.get("refund_amount") or 0)),
            raw=scrub(d),
        )

    def close_transaction(self, tran_id: str) -> dict:
        t = req_time()
        body = {"req_time": t, "merchant_id": self.merchant_id, "tran_id": tran_id,
                "hash": sign(self.api_key, t, self.merchant_id, tran_id)}
        return scrub(self._post(CLOSE_TRANSACTION, body))

    # -------------------------------------------------------------- refunds
    def refund(self, tran_id: str, amount_minor: int, currency: str) -> dict:
        if not self.rsa_public_key:
            raise PayWayError("Refunds need the RSA public key from ABA (ABA_PAYWAY_RSA_PUBLIC_KEY).")
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        key = serialization.load_pem_public_key(self.rsa_public_key.encode())
        payload = json.dumps({"mc_id": self.merchant_id, "tran_id": tran_id,
                              "refund_amount": amount_value(amount_minor, currency)}).encode()
        # PayWay encrypts in 117-byte chunks (RSA-1024 with PKCS#1 v1.5 padding)
        encrypted = b"".join(key.encrypt(payload[i:i + 117], padding.PKCS1v15()) for i in range(0, len(payload), 117))
        merchant_auth = base64.b64encode(encrypted).decode()
        t = req_time()
        body = {"request_time": t, "merchant_id": self.merchant_id, "merchant_auth": merchant_auth,
                "hash": sign(self.api_key, t, self.merchant_id, merchant_auth)}
        data = self._post(REFUND, body)
        status = data.get("status") or {}
        if str(status.get("code")) not in ("0", "00"):
            raise PayWayError(status.get("message") or "Refund failed", code=str(status.get("code")), payload=scrub(data))
        return scrub(data)


_override: PayWayClient | None = None


def get_payway() -> PayWayClient | None:
    """The configured client, or None when PayWay credentials are not set."""
    if _override is not None:
        return _override
    s = get_settings()
    if s.payway_simulator and not s.is_production:
        from app.services.payway_simulator import get_simulator

        return get_simulator().client()
    if not s.payway_enabled:
        return None
    return PayWayClient(s.aba_payway_merchant_id, s.aba_payway_api_key, s.aba_payway_base_url,
                        s.aba_payway_rsa_public_key)


def set_payway_override(client: PayWayClient | None) -> None:
    """Tests only: use a client that talks to a fake PayWay."""
    global _override
    _override = client
