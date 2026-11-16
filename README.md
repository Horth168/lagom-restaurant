# LAGOM

**JUST THE RIGHT AMOUNT.** · FOOD · DRINKS · MOMENTS

LAGOM is a restaurant ordering, POS and business management platform built for
Cambodia. Customers scan the QR code on their table, order, pay with ABA PayWay,
and track their order on their phone. Staff work from the kitchen display, the
POS and the admin dashboard.

> Status: in active development. See the milestone list in
> [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository layout

| Folder | What it contains |
|---|---|
| `backend/` | Python FastAPI API, database models, migrations, tests |
| `frontend/` | React + Vite app (customer, admin, POS, kitchen screens) |
| `brand/` | LAGOM logo system and print templates |
| `docs/` | Architecture, setup, deployment and integration guides |

## Screens

| Address | For | What it does |
|---|---|---|
| `/t/<table QR code>` | Customers | Menu, order, pay (KHQR or cash), live order tracking |
| `/tg` | Customers in Telegram | Same menu as a Telegram Mini App, for pickup at the counter |
| `/login` | Staff | Sign in |
| `/admin` | Owner, admin, inventory staff | Overview, orders, payments, menu, inventory, finance, tables & QR, settings |
| `/pos` | Cashiers | Counter orders, discounts, cash or KHQR, 80 mm receipts |
| `/kds` | Kitchen, drinks, dessert | Live kitchen display per station |

## Guides

- [Architecture](docs/ARCHITECTURE.md)
- [Run LAGOM on Windows](docs/WINDOWS_SETUP.md)
- [Payments setup: ABA KHQR + cash](docs/PAYMENTS_SETUP.md)
- [Kitchen display (KDS)](docs/KITCHEN_DISPLAY.md)
- [Inventory and finance](docs/INVENTORY_AND_FINANCE.md)
- [Staff, permissions and languages](docs/STAFF_AND_LANGUAGES.md)
- [Telegram alerts, Mini App and installing on phones](docs/TELEGRAM_SETUP.md)
