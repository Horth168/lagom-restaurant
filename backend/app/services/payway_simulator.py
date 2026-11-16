"""A local stand-in for ABA PayWay — DEVELOPMENT AND TESTS ONLY.

It implements the same endpoints, request fields and HMAC-SHA512 hash checks as
the real API, so the real PayWayClient code is exercised end to end. It can never
be used in production (the server refuses to start with PAYWAY_SIMULATOR=true).
A transaction only becomes APPROVED when a developer explicitly simulates the
customer's payment; there is no automatic success.
"""
import json
import threading
from decimal import Decimal

import httpx

from app.services import payway as pw

SIM_MERCHANT = "lagom-simulator"
SIM_KEY = "simulator-api-key-not-a-secret"


class PayWaySimulator:
    def __init__(self, merchant_id: str = SIM_MERCHANT, api_key: str = SIM_KEY):
        self.merchant_id = merchant_id
        self.api_key = api_key
        self.transactions: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ helpers for developers/tests
    def pay(self, tran_id: str, amount=None) -> None:
        """Simulate the customer completing payment in ABA Mobile."""
        with self._lock:
            t = self.transactions[tran_id]
            if t["status"] != "PENDING":
                raise ValueError(f"Transaction is {t['status']}")
            t["status"] = "APPROVED"
            t["paid_amount"] = Decimal(str(amount)) if amount is not None else t["amount"]
            t["apv"] = f"{abs(hash(tran_id)) % 1_000_000:06d}"

    def decline(self, tran_id: str) -> None:
        self.transactions[tran_id]["status"] = "DECLINED"

    def client(self) -> pw.PayWayClient:
        return pw.PayWayClient(self.merchant_id, self.api_key, "https://payway-simulator.local",
                               transport=httpx.MockTransport(self.handle))

    # ------------------------------------------------------------------ fake HTTP API
    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        path = request.url.path
        self.calls.append((path, body))
        if path == pw.GENERATE_QR:
            return self._generate_qr(body)
        if path == pw.CHECK_TRANSACTION:
            return self._check(body)
        if path == pw.CLOSE_TRANSACTION:
            return self._close(body)
        return httpx.Response(404, json={"status": {"code": "404", "message": "Not found"}})

    def _bad_hash(self, body: dict, *values) -> bool:
        return body.get("merchant_id") != self.merchant_id or body.get("hash") != pw.sign(self.api_key, *values)

    def _generate_qr(self, b: dict) -> httpx.Response:
        order = ["req_time", "merchant_id", "tran_id", "amount", "items", "first_name", "last_name", "email",
                 "phone", "purchase_type", "payment_option", "callback_url", "return_deeplink", "currency",
                 "custom_fields", "return_params", "payout", "lifetime", "qr_image_template"]
        values = [pw.amount_for_hash(b["amount"]) if k == "amount" else str(b.get(k, "")) for k in order]
        if self._bad_hash(b, *values):
            return httpx.Response(200, json={"status": {"code": "1", "message": "Wrong Hash", "trace_id": "sim"}})
        with self._lock:
            if b["tran_id"] in self.transactions:
                return httpx.Response(200, json={"status": {"code": "403", "message": "Duplicated Transaction ID"}})
            amount = Decimal(str(b["amount"]))
            self.transactions[b["tran_id"]] = {"amount": amount, "currency": b["currency"].upper(),
                                               "status": "PENDING", "apv": "", "paid_amount": None}
        qr = f"00020101021230SIMULATED-KHQR-{b['tran_id']}-{amount}{b['currency']}"
        return httpx.Response(200, json={
            "qrString": qr, "qrImage": "",
            "abapay_deeplink": f"abamobilebank://ababank.com?type=payway&qrcode={qr}",
            "app_store": "https://itunes.apple.com/al/app/aba-mobile-bank/id968860649?mt=8",
            "play_store": "https://play.google.com/store/apps/details?id=com.paygo24.ibank",
            "amount": float(amount), "currency": b["currency"],
            "status": {"code": "0", "message": "Success.", "trace_id": "sim"},
        })

    def _check(self, b: dict) -> httpx.Response:
        if self._bad_hash(b, b.get("req_time", ""), b.get("merchant_id", ""), b.get("tran_id", "")):
            return httpx.Response(200, json={"status": {"code": "5", "message": "Invalid hash"}})
        t = self.transactions.get(b["tran_id"])
        if not t:
            return httpx.Response(200, json={"status": {"code": 6, "message": "Transaction not found",
                                                        "tran_id": b["tran_id"]}})
        amount = t["paid_amount"] if t["paid_amount"] is not None else t["amount"]
        codes = {"APPROVED": 0, "PENDING": 2, "DECLINED": 3, "REFUNDED": 4, "CANCELLED": 7}
        return httpx.Response(200, json={
            "data": {"payment_status_code": codes[t["status"]], "total_amount": float(amount),
                     "original_amount": float(t["amount"]), "refund_amount": 0, "discount_amount": 0,
                     "payment_amount": float(amount), "payment_currency": t["currency"], "apv": t["apv"],
                     "payment_status": t["status"], "transaction_date": "2026-01-01 00:00:00"},
            "status": {"code": "00", "message": "Success!", "tran_id": b["tran_id"]},
        })

    def _close(self, b: dict) -> httpx.Response:
        if self._bad_hash(b, b.get("req_time", ""), b.get("merchant_id", ""), b.get("tran_id", "")):
            return httpx.Response(200, json={"status": {"code": "5", "message": "Invalid hash"}})
        t = self.transactions.get(b["tran_id"])
        if t and t["status"] == "PENDING":
            t["status"] = "CANCELLED"
        return httpx.Response(200, json={"status": {"code": "00", "message": "Success!"}})


_simulator: PayWaySimulator | None = None


def get_simulator() -> PayWaySimulator:
    global _simulator
    if _simulator is None:
        _simulator = PayWaySimulator()
    return _simulator
