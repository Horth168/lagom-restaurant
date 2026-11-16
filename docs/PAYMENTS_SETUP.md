# Payments setup: ABA KHQR + cash

LAGOM accepts two ways to pay. **No ABA PayWay merchant licence is needed.**

| Method | How the customer pays | How LAGOM knows it is paid |
|---|---|---|
| **ABA KHQR** | Scans the QR on their phone with ABA Mobile or any Cambodian bank app | ABA's own Telegram bot posts "$X paid by …" in your payment group; LAGOM reads it and confirms the order automatically |
| **Cash at the counter** | Shows the order number to the cashier | The cashier confirms it in the POS (or `POST /api/admin/orders/{id}/cash`) |

Only confirmed orders go to the kitchen. The customer's phone never decides that an order is paid.

## How automatic KHQR confirmation works

1. At checkout LAGOM makes a QR **for that order only**: your ABA account, the exact amount,
   and an order reference (e.g. `LG261116-001-7Q`). It is built from your shop's own ABA QR,
   keeping ABA's routing fields, so ABA treats it like your normal shop QR.
2. The customer pays. ABA's bot (**@PayWayByABA_bot**) posts the payment in your Telegram group.
3. A Telegram account you choose (the *listener*) reads that group for LAGOM. Telegram does not
   let one bot read another bot's messages, which is why a normal account is needed.
4. LAGOM confirms the order **only if all of these are true**:
   - the message is in your payment group **and** was sent by ABA's PayWay bot itself;
   - its ABA transaction ID has never been used before;
   - exactly one waiting order asks for that exact amount, and its QR was valid at that time
     (if ABA's message includes the order reference, only that order is considered).
5. If two orders could match (e.g. two tables each owe $3.25), LAGOM **does not guess**: you get a
   Telegram message and confirm the right one in the dashboard (Payments → Bank notices).
   The same happens for a payment that matches nothing. Money is never lost silently.

## Step 1 — Your shop QR text

1. In ABA Mobile, open your merchant/shop KHQR (the QR you would print for customers).
2. Scan it with any QR-reader app (or Google Lens) and **copy the text** — it starts with `000201`.
3. Put it in `backend/.env` on the server:

```
KHQR_TEMPLATE=000201010211...the whole text...6304ABCD
KHQR_STORE_LABEL=LAGOM
```

LAGOM checks the QR's checksum and refuses a damaged one. This text is printed on your shop QR
anyway, so it is not a secret, but keep it in `.env` rather than in the code.

## Step 2 — The Telegram payment group

1. Create a private Telegram group, e.g. "LAGOM Payments".
2. In ABA Mobile, link ABA's payment notifications (PayWay bot) to that group, the same way
   you did for IceQ Sole. Make a small test payment and check "$… paid by …" appears.
3. Add the **listener account** to the group (a spare Telegram account is best).

## Step 3 — Sign in the listener (once, on your computer)

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m scripts.telegram_login
```

It asks for the API ID and API hash (create them at https://my.telegram.org → API development
tools), the listener's phone number and the code Telegram sends. Choose the payment group from
the list. It writes `backend/.env.listener` (ignored by git) containing:

```
TG_LISTENER_API_ID=...
TG_LISTENER_API_HASH=...
TG_LISTENER_SESSION=...      # works like a password: never share or commit it
PAYWAY_CHAT_ID=-100...
```

Copy those four lines into the server's environment and restart the backend. Check the status at
`GET /api/admin/payments/status` (shows `connected` and the account name; never the secret).

To sign the listener out later: Telegram → Settings → Devices → end "LAGOM payment listener".

## Step 4 (optional) — Staff notifications

To receive "✅ Paid", "⚠️ two orders match" and "ℹ️ unmatched payment" messages, create a bot with
@BotFather and set:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...         # the owner/staff group, can be the same payment group
```

## Accepting riel

By default customers pay in USD. To also offer riel, an owner sets
`accepted_payment_currencies` to `["USD", "KHR"]` in Settings. The riel amount is the order's
locked riel total (at the exchange rate saved when the order was made).

## Testing without real money (development only)

In `backend/.env`:

```
KHQR_TEST_MODE=true
KHQR_TEMPLATE=...any valid KHQR text...
```

The payment screen then shows **TEST MODE — no real money** and a "Simulate ABA payment notice"
button. It sends a message shaped exactly like ABA's through the same matching code. The server
**refuses to start in production** while test mode is on.

## Limits to know

- Confirmation depends on ABA's Telegram message. If ABA's bot is delayed, the order waits
  (customers see "Waiting for payment…"); staff can always confirm it by hand.
- Unpaid KHQR orders expire after 15 minutes, cash orders after 60. A KHQR payment that arrives
  up to 10 minutes late is still matched automatically.
- Refunds are made from ABA Mobile; record them in LAGOM (admin, coming in the next milestones).
