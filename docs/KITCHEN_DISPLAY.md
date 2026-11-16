# Kitchen display (KDS)

Open **`/kds`** on each kitchen tablet and sign in with that station's staff account.

| Station | Address | Who can open it |
|---|---|---|
| Kitchen | `/kds/kitchen` | KITCHEN role, owners, admins |
| Drinks | `/kds/drinks` | DRINKS role, owners, admins |
| Dessert | `/kds/dessert` | KITCHEN and DRINKS roles, owners, admins |

## How orders arrive

- Only **paid** orders appear (KHQR confirmed by ABA's notice, or cash confirmed by a cashier).
- Each item goes to its station automatically. One order with Fried Rice, an Iced Latte and a
  Cheesecake shows Fried Rice on Kitchen, the latte on Drinks and the cheesecake on Dessert.
  Every ticket shows the same order number and "Also: 1 Drinks · 1 Dessert".
- New tickets appear instantly (live connection) and play a short chime. Tap the yellow bar once
  after opening the screen to allow sound (browsers require one tap). The bell button mutes it.
- The badge top right says **Live**. If the network drops it says **Reconnecting…**; the screen
  keeps working and checks for new orders every 15 seconds until the connection is back.

## Buttons

| Ticket shows | Big button | What it means for the customer |
|---|---|---|
| NEW (gold) | **Accept** | "Order received" |
| ACCEPTED | **Start preparing** | "Preparing" |
| PREPARING (blue) | **Mark ready** | When *every* station is ready: "Ready" |
| READY (green) | **Served** | When every station has served: "Served" |

- Tap a single item to tick it off when part of a ticket is done.
- **Not ready yet** puts a ready ticket back to preparing (e.g. pressed by mistake).
- The timer shows how long the customer has waited since paying. It turns gold after the item's
  preparation time and red after twice that.
- Use **Full screen** on tablets. Served tickets are listed at the bottom for 30 minutes.

## Tips for tablets

- Keep the tablet plugged in and set the screen to never sleep.
- Add the page to the home screen for a full-screen app (the PWA milestone improves this further).
