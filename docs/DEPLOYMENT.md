# Put LAGOM online

## What is live now (free, 24/7)

| Part | Where | Address |
|---|---|---|
| Website | Render static site `lagom-web` (workspace **LAGOM**) | https://lagom-web.onrender.com |
| Server | Render free web service `lagom-api` (workspace **LAGOM**, Singapore) | https://lagom-api.onrender.com |
| Database | Supabase project `lagom` (Singapore), schema `lagom`, login `lagom_app` | Supabase session pooler |
| Menu photos | Inside the database (`PHOTO_STORAGE=database`) | `/api/public/photos/…` |
| Keep-awake | Supabase pg_cron job `lagom-keep-awake` (every 5 min) + GitHub Action `Keep API awake` (every 10 min) | pings `/api/health` |

Why it stays up for free: LAGOM has **its own Render workspace**, so its 750 free server-hours a
month are not shared with IceQ Sole or other projects, and the pings stop the free server from
sleeping. Supabase's free database has no monthly compute-hour limit. Render may still restart a
free server now and then (it is back within about a minute). For guaranteed uptime later,
switch `lagom-api` to the Starter plan (about $7/month); nothing else changes.

The LAGOM tables live in their own schema (`lagom`), which Supabase's public Data API does not
expose. The `lagom_app` login is not a superuser and only owns that schema.

The sections below describe the general setup (Cloudflare Pages / Neon / R2 alternatives).

---

LAGOM runs on four services. Each has a free tier except Render, where the small paid plan is
needed so payments are confirmed at all hours.

| Part | Service | What it holds | Cost (Nov 2026) |
|---|---|---|---|
| Website (menu, admin, POS, kitchen screen) | **Cloudflare Pages** | The built React app | Free |
| Server (API, live updates, ABA payment listener) | **Render** (web service) | Python backend | Starter plan, about $7 / month |
| Database | **Neon** (PostgreSQL) | Orders, menu, staff, money | Free plan to start |
| Menu photos you upload | **Cloudflare R2** | Photos | Free up to 10 GB |

> **Why not Render's free plan?** It goes to sleep after 15 minutes with no visitors. While it
> sleeps, ABA payment messages are not read, so KHQR orders wait until someone opens the site.
> The Starter plan never sleeps.

Keep **one** Render instance. Login limits, live updates and the payment listener run inside
that one server.

Before you start, everything must be on the `main` branch: Render and Cloudflare build from it,
and every later push to `main` updates the live site automatically.

---

## Step 1: Database (Neon)

1. Sign up at https://neon.tech and create a project. Region: **Asia Pacific (Singapore)**,
   Postgres 16 or newer.
2. On the project dashboard press **Connect**, turn **Connection pooling OFF**, and copy the
   connection string. It looks like
   `postgresql://user:password@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`.
3. Keep it private: it contains the database password. You will paste it into Render (step 2)
   and use it once on your computer (step 3).

## Step 2: Server (Render)

1. Sign up at https://render.com with your GitHub account.
2. **New + → Blueprint**, choose the `lagom-restaurant` repository. Render reads `render.yaml`
   and proposes the service **lagom-api** (Singapore, Starter).
3. Render asks for the values marked "sync: false". For the first deploy fill in:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string from step 1 |
   | `FRONTEND_URL` | leave `https://example.invalid` for now (step 5 replaces it) |
   | `BACKEND_URL` | `https://lagom-api.onrender.com` (the address Render shows for the service) |
   | `CORS_ORIGINS` | same as `FRONTEND_URL` for now |

   Leave the KHQR, Telegram and R2 values empty for now. `SECRET_KEY` is created by Render.
4. Press **Apply**. The first deploy creates all database tables (`alembic upgrade head` runs
   before the server starts).
5. Open `https://lagom-api.onrender.com/api/health`. You should see
   `{"status":"ok","environment":"production"}`.

If the deploy fails with "Production configuration problems: …", the message says which value
is wrong (for example a missing `https://`). The server refuses to start rather than run unsafely.

## Step 3: Create the owner account

From your own computer, in the `backend` folder (PowerShell):

```powershell
.venv\Scripts\activate
$env:DATABASE_URL = "postgresql://...the Neon string..."
python -m scripts.create_owner
Remove-Item Env:DATABASE_URL
```

Type your email, name and a strong password (at least 10 characters, with upper- and lower-case letters and a number). Do **not** load the demo
data: it refuses to run in production, and the live menu should be your real one.

## Step 4: Menu photos (Cloudflare R2)

Render's disk is wiped on every deploy, so uploaded photos must live in R2.

1. Cloudflare dashboard → **R2** → **Create bucket** `lagom-photos`.
2. Bucket → **Settings → Public access → R2.dev subdomain → Allow**. Copy the public URL
   (`https://pub-xxxx.r2.dev`).
3. R2 → **Manage API tokens → Create API token**: permission **Object Read & Write**, only
   this bucket. Copy the Access Key ID and Secret Access Key (shown once).
4. In Render → lagom-api → **Environment**, set `R2_ACCOUNT_ID` (top right of the R2 page),
   `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET=lagom-photos` and
   `R2_PUBLIC_BASE_URL=https://pub-xxxx.r2.dev`. Save (Render redeploys).

Admin → Settings → Connections then shows **Photo storage (R2): connected**.

## Step 5: Website (Cloudflare Pages)

1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git** → choose
   `lagom-restaurant`.
2. Settings:

   | Setting | Value |
   |---|---|
   | Production branch | `main` |
   | Framework preset | None |
   | Root directory | `frontend` |
   | Build command | `npm run build` |
   | Build output directory | `dist` |
   | Environment variable `VITE_API_URL` | `https://lagom-api.onrender.com` |
   | Environment variable `NODE_VERSION` | `22` |

3. Deploy. You get an address like `https://lagom-restaurant.pages.dev`.
4. Back in Render, set `FRONTEND_URL` and `CORS_ORIGINS` to that address (no `/` at the end)
   and save.
5. Open the website and sign in at `/login` with the owner account from step 3.

The security headers in `frontend/public/_headers` (content security policy, https only,
no framing except the Telegram Mini App) are applied by Cloudflare automatically.

## Step 6: Check the real visitor IP

LAGOM limits wrong logins per visitor and records IPs in the audit log. Render passes the real
address in a header, and `TRUSTED_PROXY_HOPS=1` tells LAGOM which part of that header to trust.

1. Sign out and sign in again.
2. Admin → **Audit log**: the newest "auth.login" row shows an IP.
3. Compare it with your phone or computer's public IP (search "what is my IP").

If they match, you are done. If the audit log shows an address starting with `10.` or one
that is the same for every staff member, tell your developer: the hop count must be adjusted.

## Step 7: Payments, Telegram and your own address

- **ABA KHQR and the payment listener:** follow [PAYMENTS_SETUP.md](PAYMENTS_SETUP.md) and put
  the values in Render → Environment. Then pay one small real order (for example a $0.50 drink)
  from your own ABA account and check that it is confirmed automatically.
- **Telegram alerts and the Mini App:** [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md). The Mini App
  address is `https://<your website>/tg`.
- **Your own domain (optional):** Cloudflare Pages → Custom domains (e.g. `order.lagom.com.kh`)
  and Render → Settings → Custom domains (e.g. `api.lagom.com.kh`). Then update `FRONTEND_URL`,
  `CORS_ORIGINS`, `BACKEND_URL` in Render and `VITE_API_URL` in Cloudflare (and redeploy Pages).

## Step 8: Print the table QR codes (last!)

The QR codes point to `FRONTEND_URL`. Print them only after the final address is set:
Admin → **Tables** → **Print all QR cards**. If you change the address later, print them again.

---

## Before opening day

- [ ] `/api/health` says `production`
- [ ] Owner can sign in; staff accounts created with their own passwords (Admin → Staff)
- [ ] Real menu, prices and photos entered; exchange rate set (Admin → Settings)
- [ ] One real KHQR payment confirmed automatically; one cash order confirmed by the cashier
- [ ] Kitchen and drinks screens open on their tablets and beep on a new order
- [ ] 80 mm receipt prints from the POS
- [ ] Telegram test message arrives (if used)
- [ ] Audit log shows real IPs (step 6)
- [ ] Table QR cards printed from the final address

## Updating LAGOM later

Changes are made on `develop`, tested (GitHub runs all tests automatically, including on
PostgreSQL), then merged into `main`. Render and Cloudflare deploy `main` by themselves within a
few minutes. Database changes are applied automatically by `alembic upgrade head` on start.

## Backups

Neon keeps a history of the database and can restore it to an earlier moment (how far back
depends on your Neon plan: check **Settings → Storage** in Neon). For extra safety, download the
monthly finance report (Excel) from Admin → Finance.
