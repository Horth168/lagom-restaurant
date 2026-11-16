# ABA PayWay setup

LAGOM takes table payments with the official **ABA PayWay QR API**
(https://developer.payway.com.kh/). Customers can pay with:

| Option | Currencies | How |
|---|---|---|
| ABA Pay / KHQR | USD, KHR | Scan with ABA Mobile or any Cambodian bank app, or tap "Open ABA Mobile" |
| WeChat Pay | USD only | Scan with WeChat |
| Alipay | USD only | Scan with Alipay |

## How a payment is confirmed (why it is safe)

1. The customer checks out. The **server** calculates the total and locks the prices.
2. The server asks PayWay for a payment QR with a unique transaction ID (`tran_id`).
3. The customer pays in their banking app.
4. PayWay sends a notification to `https://YOUR-BACKEND/api/payments/payway/callback`.
5. That notification is **not signed**, so LAGOM never trusts it alone. The server calls
   PayWay's **Check Transaction** API with the secret key and only marks the order
   **PAID** if PayWay says `APPROVED` **and** the amount matches exactly.
6. If the notification never arrives, the customer's phone keeps asking the server,
   which checks PayWay directly. Unpaid orders expire after 15 minutes; just before
   expiring, the server checks one last time and then closes the QR at PayWay so it
   can no longer be paid.

Every request, notification and check is stored in the `payment_events` table
(secret values and personal details removed).

## 1. Get sandbox (test) credentials

1. Register at https://sandbox.payway.com.kh/register-sandbox/
2. ABA emails you a **Merchant ID** and an **API key** for the sandbox.
3. Ask the PayWay integration team to **whitelist** your backend's domain or IP.
   Without this, PayWay answers with error `6: wrong domain`.

## 2. Put them in `backend/.env` (never in git, never in chat)

```
ABA_PAYWAY_MERCHANT_ID=your-sandbox-merchant-id
ABA_PAYWAY_API_KEY=your-sandbox-api-key
ABA_PAYWAY_BASE_URL=https://checkout-sandbox.payway.com.kh
PAYWAY_SIMULATOR=false
BACKEND_URL=https://your-public-backend-address
```

`BACKEND_URL` must be reachable from the internet, or PayWay cannot deliver the
payment notification. LAGOM still confirms payments without it (the phone's
status checks ask PayWay directly), but the notification makes it instant. For
local testing you can use a tunnel such as Cloudflare Tunnel.

Restart the backend. The payment screen now shows "ABA sandbox — test payments only".

## 3. Test in the sandbox

1. Scan a table QR, order, choose ABA Pay / KHQR.
2. Pay the sandbox QR as described in ABA's sandbox email.
3. The phone should switch to "Payment confirmed" within a few seconds.
4. Check the transaction appears in the sandbox merchant portal.

**Still to confirm with real sandbox keys:** the exact hash format for amounts
(LAGOM sends `8.5` for $8.50 and hashes the same text). If PayWay answers
`1: Wrong Hash`, this is the place to look: `backend/app/services/payway.py`.

## 4. Going live (production)

1. Email **paywaysales@ababank.com** for production credentials.
2. Ask them to enable the payment options you want (KHQR, WeChat, Alipay) and,
   for refunds through LAGOM, the **refund feature** plus the **RSA public key**.
3. Change `.env` on the production server:

```
ENVIRONMENT=production
ABA_PAYWAY_MERCHANT_ID=production-merchant-id
ABA_PAYWAY_API_KEY=production-api-key
ABA_PAYWAY_BASE_URL=https://checkout.payway.com.kh
ABA_PAYWAY_RSA_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
PAYWAY_SIMULATOR=false
```

The server **refuses to start in production** if the simulator is on, the
credentials are missing, or the base URL still points to the sandbox.

4. Before opening, check the payment screen against ABA's
   [QR payment display guideline](https://www.figma.com/design/5AJmZJwZha5QFfpIKmREBr/Displaying-Payment-QR-Code---Integration-Guideline).

## Accepting KHR

By default customers pay in USD. To also offer riel, an owner sets
`accepted_payment_currencies` to `["USD", "KHR"]` in Settings. The KHR amount is
the order's locked riel total (at the exchange rate saved when the order was made).

## Development without any credentials: the simulator

With `PAYWAY_SIMULATOR=true` (and `ENVIRONMENT=development`), the backend uses a
built-in copy of the PayWay API that checks hashes exactly like the real one. The
payment screen shows **TEST MODE — no real money** and a "Simulate customer
payment" button. Nothing is ever approved unless you press it, and it cannot be
used in production.
