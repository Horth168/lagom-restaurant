# Telegram: staff alerts and ordering for pickup

Telegram is **optional**. LAGOM works fully without it: customers order with the table QR code
and staff use the dashboard. Telegram adds two things:

1. **Staff alerts** in your staff group: new paid orders, KHQR orders that were not paid in
   time, cancellations, low stock, and a daily summary.
2. **The LAGOM Mini App**: customers open LAGOM inside Telegram and order for **pickup at the
   counter**. They get a Telegram message when their payment is received and when the order is
   ready.

> This bot is separate from ABA's payment bot and from the payment *listener* account in
> [PAYMENTS_SETUP.md](PAYMENTS_SETUP.md). KHQR payments are still confirmed only by ABA's
> message, never by Telegram users.

## Step 1: Create your bot

1. In Telegram, open **@BotFather** and send `/newbot`.
2. Choose a name (e.g. `LAGOM`) and a username ending in `bot` (e.g. `lagom_pp_bot`).
3. BotFather replies with a **token** like `123456789:AA...`. **Treat it like a password.**
   Never put it in the frontend, in a screenshot, or in Git.

## Step 2: The staff group

1. Create a Telegram group, e.g. "LAGOM Staff" (it can be the same group as the ABA payment group).
2. Add your bot to the group.
3. Find the group's chat ID: send any message in the group, then open
   `https://api.telegram.org/bot<YOUR TOKEN>/getUpdates` in your browser and look for
   `"chat":{"id":-100...`. That negative number is the chat ID.

## Step 3: Tell the server

In `backend/.env` on your computer (or in Render's *Environment* page in production):

```
TELEGRAM_BOT_TOKEN=123456789:AA...
TELEGRAM_CHAT_ID=-100...
```

Restart the backend. In **Admin → Settings → Telegram alerts**:

- tick the alerts you want,
- choose when the daily summary is sent (restaurant time, default 22:00),
- press **Send test message**. A message should appear in your staff group within a few seconds.

What staff receive (examples):

```
🧾 New order #014 · Table 05
• 2× Fish Amok
• 1× Iced Latte
$15.75 · ABA KHQR · Trx 833269097398360

⌛ Order #015 expired unpaid · Table 02 · $4.50
No KHQR payment arrived. Nothing was sent to the kitchen.

📊 LAGOM · Mon 16 Nov 2026
Sales: $412.50 from 63 orders (average $6.54)
ABA KHQR $301.00 · Cash $111.50
...
```

Messages never contain secrets, card numbers or full account numbers.

## Step 4 (optional): The Mini App for pickup orders

The Mini App is the normal LAGOM menu at the address `/tg` on your website.

1. Your website must be online with **https** (e.g. `https://order.lagom.example/tg`).
   Telegram does not open Mini Apps from `localhost`.
2. In @BotFather send `/mybots` → choose your bot → **Bot Settings → Menu Button →
   Configure menu button**, and enter `https://<your website>/tg` with the title `Order`.
3. Open a chat with your bot. Tap **Order**. The LAGOM menu opens inside Telegram.

How it stays safe:

- When the Mini App opens, Telegram gives it a **signed login**. LAGOM's server checks that
  signature with your bot token, and refuses it if it is fake, changed, or older than 24 hours.
  Nobody can pretend to be another Telegram user.
- Each customer only sees their own orders.
- Prices and payment status come from the server, exactly like the table QR app. Orders go to the
  kitchen only after the payment is confirmed (ABA's message for KHQR, or the cashier for cash).
- Orders show to staff as **"Pickup · Dara"** (the customer's Telegram first name).
- The customer gets "payment received" and "your order is ready" messages in the language they
  chose in the app (English, Khmer or Chinese).

If the bot token is not set, `/tg` shows "Ordering in Telegram is not available right now" and
nothing else changes.

## Install LAGOM on a phone (PWA)

LAGOM is also an installable web app; no app store is needed.

- **Android (Chrome):** open the website → menu ⋮ → **Install app** / **Add to Home screen**.
- **iPhone (Safari):** open the website → Share → **Add to Home Screen**.

Installed, it opens full screen with the LAGOM icon and splash screen. The menu, prices and
photos are kept on the phone, so if the internet drops a customer can still read the menu
(a banner says they are offline). **Ordering and paying always need internet**, so nothing is
sent or paid twice.

The kitchen display and the POS can be installed the same way on a tablet.

## Testing

`backend/tests/test_telegram.py` checks real and fake Telegram logins, pickup orders end to end,
the customer messages in Khmer, every staff alert, switching alerts off, the daily summary being
sent once per day after the chosen time, and that a Telegram outage never breaks a payment.
The tests never contact Telegram.
