# Running LAGOM day to day

The everyday tools for staff and the owner. Each one is tested automatically
(`backend/tests/test_extras.py`).

## Cash drawer shifts (cashiers)

1. At the start: **POS → Open shift**, type the cash already in the drawer (dollars and riel).
2. Sell as usual. Cash orders, cash refunds and ABA KHQR are counted automatically.
3. At the end: **POS → Shift since …** → count **all** the cash in the drawer, type it, **Close shift**.

LAGOM shows **what should be in the drawer** (start cash + cash sales − cash refunds) and the
**difference**. The owner gets a Telegram message for every closed shift, and every shift is listed in
**Admin → Payments → Cash drawer shifts**. If the drawer is short, check for a cash payment that was
not entered, wrong change, or a refund that was not recorded.

Only one drawer can be open at a time. KHQR money goes to the bank, so it is shown for information only.

## "Call waiter" and "Request the bill" (customers at a table)

The bell in the table menu lets a customer call a waiter or ask for the bill. Staff see it at the top
of the **POS** and every **Admin** page (with a chime) and in the Telegram group. Press **Done** when
handled; the customer's screen updates. Pressing the bell twice does not ring twice. Pickup
(Telegram) customers do not have the bell.

## Ratings

When an order is **ready**, the customer can give 1–5 stars, optional stars per dish and a comment
(once per order). **Admin → Reviews** shows the average per dish and the latest comments. Ratings of
1–2 stars are also sent to the Telegram group so you can react the same day.

## Deals (happy hour)

**Admin → Deals → New deal**: a name customers see, a percentage, what it applies to (whole menu, a
category or one dish), days and hours (restaurant time; e.g. 22:00–02:00 works over midnight).

* Customers see a badge and the old price crossed out; the POS shows it too.
* The **server** applies the price when the order is placed, so the price is always correct even if
  a phone still shows the menu from a few seconds earlier (menus refresh within 30 seconds).
* If two deals match a dish, the bigger discount is used. Switch a deal off any time.

## Telegram stamp card

**Admin → Settings → Telegram stamp card**: switch it on, choose how many stamps give one free item
(e.g. 9 = "buy 9, the 10th is free") and which categories collect stamps.

* Only customers who order in the **Telegram Mini App** collect stamps (Telegram tells us who they are).
* Stamps are given only when the order is **paid**. Cancelling a paid order takes them back.
* In the cart they tick **Use my free item**: the cheapest stamp-card item in that order becomes free.
  If the order is then not paid in time, the free item goes back on their card.
* An order that becomes completely free goes straight to the kitchen (no payment step).
* After each payment the customer gets a Telegram message showing their card.

## Dishes sold out automatically

If a dish has a recipe in **Admin → Inventory** and an ingredient is lower than one portion needs, the
dish shows **Sold out** and cannot be ordered. It comes back by itself after you record a purchase.
Turn this off in **Settings → General**. Dishes without a recipe are never affected.

## Busiest hours

**Admin → Overview → Busiest hours**: paid orders by day of the week and hour (last 4 weeks or 90 days).
Darker squares = more orders; tap a square for the number of orders and sales. Use it to plan shifts.

## Kitchen ticket printer

On the kitchen screen each ticket has a **printer button**. The **printer icon at the top** prints every
new order automatically on that device (remembered on that tablet/PC only).

Any 80 mm receipt printer that the tablet/PC can print to works. Normally the browser shows a print
window each time. To print without the window, start Chrome on the kitchen PC like this (Windows):

```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk-printing https://lagom-web.onrender.com/kds
```

and set the receipt printer as the **default printer** in Windows.

## View-only menu link

**https://lagom-web.onrender.com/menu** shows the whole menu with photos, prices and current deals, in
English, Khmer and Chinese, but cannot take orders. Share it on Facebook, Google Maps and Instagram.
The home page has a **See our menu** button too.

## Weekly backup

**Admin → Settings → Backup → Download backup** gives one Excel file with every table (one sheet per
table). Passwords, login keys and photo files are never included. Every Monday after 10:00 the
Telegram group gets a reminder. Keep the files somewhere safe (e.g. Google Drive), not only on one phone.
