# LAGOM — Architecture

> JUST THE RIGHT AMOUNT. · FOOD · DRINKS · MOMENTS

This document explains how LAGOM is built and why. It is written for the owner
(a beginner developer) as well as future engineers.

## 1. Big picture

```
 Customer phone (QR)        Staff tablets / PCs
 ┌──────────────────┐       ┌──────────────────────────────────────────┐
 │ /t/<table-token> │       │ /admin  /pos  /kds/kitchen  /kds/drinks  │
 └────────┬─────────┘       └───────────────────┬──────────────────────┘
          │   one React (Vite) PWA, split by route  │
          └──────────────┬─────────────────────────┘
                         │ HTTPS (REST)  +  WSS (live updates)
                ┌────────▼─────────┐        ┌──────────────────────┐
                │  FastAPI backend │◄──────►│ ABA PayWay (payments)│
                │  (Python)        │        └──────────────────────┘
                │                  │───────►  Telegram Bot API
                │                  │───────►  Cloudflare R2 (photos)
                └────────┬─────────┘
                         │ SQLAlchemy
                ┌────────▼─────────┐
                │ PostgreSQL (Neon)│
                └──────────────────┘
```

### Decision: one frontend app, not ten

The brief lists ten "applications" (customer, admin, POS, KDS, drinks, inventory,
staff, finance, payments, Telegram). They are built as **sections of one React
app** with separate routes and lazy-loaded code:

| Route | Who uses it | Device |
|---|---|---|
| `/t/:tableToken` | Customers | Phone |
| `/admin/*` | Owner, Admin, Inventory staff | Desktop / tablet |
| `/pos` | Cashier | Tablet / desktop |
| `/kds/:station` | Kitchen, Drinks, Dessert staff | Tablet |

Why: one codebase, one design system, one translation file, one deploy. Customers
only download the customer code (route-based code splitting), so the phone
experience stays fast. Each staff screen still feels like its own app.

### Decision: Python FastAPI backend, sync SQLAlchemy

- FastAPI is fast, typed, and produces interactive API docs at `/docs`.
- Synchronous SQLAlchemy 2.0 is simpler to read and debug than async. FastAPI
  runs it in a thread pool, which is plenty for a restaurant workload.
- WebSockets run on the async side; a small broadcaster bridges the two.

### Decision: PostgreSQL in production, SQLite allowed for local dev and tests

The production database is PostgreSQL (Neon free tier). So you can start coding
on Windows without installing PostgreSQL or Docker, the backend also runs on a
local SQLite file. Automated tests use SQLite. All models use portable types
(no Postgres-only features), and Alembic migrations are tested on both.

## 2. Money and currency rules

- All amounts are stored as **integers in the smallest unit**: USD cents
  (`total_usd_cents = 450` means $4.50). This avoids floating-point rounding.
- The menu is priced in USD (Cambodian standard). KHR amounts are calculated with
  the exchange rate set by the owner.
- Every order stores a **snapshot** of the exchange rate and the KHR total at the
  moment it was created. Changing the rate later never changes old orders.
- Prices and chosen options are **copied into the order** (name, price, options)
  when the order is created. Editing a product later never changes old orders.
- The backend always recalculates totals from the database. Prices sent by the
  phone are ignored (price-manipulation protection).

## 3. Order lifecycle

```
PENDING_PAYMENT ──(verified payment)──► PAID ──► PREPARING ──► READY ──► SERVED
       │                                   │
       └──(timeout)──► EXPIRED             └──(manager)──► CANCELLED (+ refund)
```

- QR orders start as `PENDING_PAYMENT`. They are **invisible to the kitchen**.
- Only the backend can move an order to `PAID`, and only after ABA PayWay confirms
  the transaction through the server-to-server check (never from the phone).
- Each order item is routed to a station (`KITCHEN`, `DRINKS`, `DESSERT`) based
  on its product. Items move through `QUEUED → PREPARING → READY → SERVED`
  individually. The order becomes `READY` only when every item is ready.

## 4. Payments (ABA PayWay)

1. Customer checks out → backend creates the order, calculates the total, locks prices.
2. Backend creates a `payment` row with a unique `tran_id` and calls PayWay.
3. Customer pays (ABA KHQR / cards / ABA Pay deeplink).
4. PayWay calls our **callback URL**. We log it, but we do **not** trust it alone:
   we call PayWay's *Check Transaction* API with our secret key to confirm.
5. If confirmed and the amount matches, the order becomes `PAID` in a single
   database transaction. Repeating steps 4–5 is safe (idempotent).
6. Kitchen screens and the customer screen update instantly over WebSocket.

Secrets (`ABA_PAYWAY_API_KEY`, merchant ID) live only in backend environment
variables. See `docs/ABA_PAYWAY_SETUP.md`.

## 5. Security model

| Concern | Protection |
|---|---|
| Staff login | Argon2 password hashing, JWT access tokens, rate-limited login |
| Permissions | Roles checked on **every** backend endpoint (not just hidden buttons) |
| Table QR | Each table has a random 32-byte token; table numbers are never trusted |
| Customer privacy | Each phone gets a private table-session token; orders are only visible with it |
| Duplicate orders | Checkout requires an idempotency key; resubmits return the same order |
| Payments | Server-side verification, unique `tran_id`, amount check, full event log |
| Inventory | Deduction recorded once per order (database unique constraint) |
| Audit | Sensitive actions (refunds, cancels, price edits, role changes) are logged |

## 6. Real time

FastAPI WebSockets with channels:
- `station:<KITCHEN|DRINKS|DESSERT>` → KDS screens (staff token required)
- `orders` → admin / POS
- `session:<token>` → a customer's phone

Free-tier hosting runs a single backend instance, so an in-memory broadcaster is
enough. If LAGOM later runs several backend instances, swap it for Redis pub/sub
(one file: `app/services/realtime.py`). Clients reconnect automatically and also
re-fetch on reconnect, so a missed message never leaves a screen stale.

## 7. Folder structure

```
backend/
  app/
    main.py            FastAPI app, routers, startup
    config.py          Settings from environment variables
    db.py              Database engine and sessions
    core/              Security (hashing, JWT), permissions, rate limiting
    models/            Database tables (SQLAlchemy)
    schemas/           Request/response shapes (Pydantic)
    api/               HTTP + WebSocket endpoints
    services/          Business logic (pricing, orders, payments, inventory…)
  alembic/             Database migrations
  tests/               Automated tests (pytest)
  scripts/             Seed demo data, create owner account
frontend/
  src/
    apps/customer|admin|pos|kds   Route sections
    components/        Shared UI
    i18n/              en.json, km.json, zh.json
    lib/               API client, money formatting, websocket
  public/              PWA icons, manifest
brand/                 Logo system (SVG) and print templates
docs/                  Guides (setup, deployment, PayWay, Telegram)
```

## 8. Hosting plan (free tier first)

| Part | Service | Free-tier notes |
|---|---|---|
| Frontend | Cloudflare Pages | Free, fast in Asia, HTTPS automatic |
| Backend | Render web service | Free tier **sleeps after ~15 min idle** (~30–60 s cold start). For a live restaurant use the paid "Starter" plan (~$7/mo) so payment callbacks are never delayed |
| Database | Neon PostgreSQL | Free 0.5 GB, auto-suspends when idle (fast resume) |
| Photos | Cloudflare R2 | Free 10 GB, no download fees |

Details and step-by-step instructions: `docs/DEPLOYMENT.md`.

## 9. Milestones

1. Repository inspection and architecture ← this document
2. Project setup, database, backend, authentication
3. Customer application and QR table ordering
4. Cart, checkout, ABA PayWay sandbox
5. Real-time tracking and KDS
6. Admin dashboard and POS
7. Inventory, expenses, financial reports
8. Staff permissions and multi-language
9. PWA and Telegram
10. Testing, security review, deployment
