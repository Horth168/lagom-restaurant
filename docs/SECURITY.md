# Security in LAGOM

How LAGOM protects money, accounts and data, and what the milestone 10 review checked.
Automated tests for every point marked ✔︎ run on each push (GitHub Actions, on SQLite and PostgreSQL).

## Money and orders

- ✔︎ **Prices come only from the server.** The phone sends product and option IDs; the server
  calculates every price, discount and total. A changed price in the browser is ignored.
- ✔︎ **Only verified payments reach the kitchen.** KHQR orders are confirmed only by a message
  from ABA's own PayWay bot, in your payment group, with a never-seen-before transaction ID and the
  exact amount. Cash is confirmed only by a signed-in cashier. The customer's phone can never mark
  an order paid.
- ✔︎ **No guessing.** If two orders wait for the same amount, or none matches, staff decide in
  the dashboard.
- ✔︎ **One payment, one order.** Each ABA transaction ID is stored once (database unique key).
- ✔︎ **Test payments cannot reach production.** `KHQR_TEST_MODE` is refused at start-up when
  `ENVIRONMENT=production`, and the test endpoint answers 404 there.

## Accounts and access

- ✔︎ Passwords are hashed with Argon2 and must be 10+ characters with mixed case and a number.
- ✔︎ Staff see only what their role allows (owner, admin, cashier, kitchen, drinks, inventory).
  Every staff action is checked on the server, not just hidden in the screen.
- ✔︎ Wrong logins are limited per visitor and per email. The visitor's IP is taken only from
  the part of `X-Forwarded-For` written by our own host (`TRUSTED_PROXY_HOPS`), so typing a fake
  IP does not get around the limit.
- ✔︎ Disabling a staff member or changing their role signs them out everywhere.
- ✔︎ Important actions (logins, refunds, cancellations, price and setting changes) are kept in
  the audit log.

## Customers

- ✔︎ Each phone at a table gets its own private session; another phone at the same table, or
  another Telegram user, cannot see its orders.
- ✔︎ Telegram Mini App logins are checked with the bot token's signature and refused if fake,
  changed or older than 24 hours.
- ✔︎ Table QR codes contain long random tokens (not guessable) and can be replaced from the admin.

## Data and secrets

- ✔︎ No secrets in Git: `.env`, databases, Telegram sessions and keys are git-ignored. The whole
  Git history was scanned on 16 Nov 2026: only placeholder examples were found.
- ✔︎ Secrets live only in Render's environment settings; the website contains no keys.
- ✔︎ Telegram alerts never include secrets or full account numbers, and a failed alert never
  breaks a payment.
- ✔︎ Uploaded photos are re-encoded (fake image files are rejected, hidden GPS/EXIF data removed).
- ✔︎ Excel exports write staff-typed text as plain text, never as a formula.

## Website and server hardening

- ✔︎ The server only accepts browser requests from your website (`CORS_ORIGINS`).
- ✔︎ Production refuses to start with a weak `SECRET_KEY`, SQLite, test mode, or non-https addresses.
- ✔︎ https is enforced (HSTS) on both the server and the website.
- The website sends a strict Content-Security-Policy (`frontend/public/_headers`): only its own
  scripts plus Telegram's Mini App script, no inline scripts, and no framing except the Mini App
  inside Telegram.

## Review of 16 November 2026: problems found and fixed

| Problem | Risk | Fix |
|---|---|---|
| Login limit trusted the first `X-Forwarded-For` value | Password guessing by faking a new IP on every try | Trust only proxy-written entries (`TRUSTED_PROXY_HOPS`) |
| Expense descriptions exported as typed | A text starting with `=` would run as an Excel formula on the owner's computer | Always written as text |
| Starlette, python-multipart and PyJWT had published security fixes | Known weaknesses in uploads, request handling and login tokens | Upgraded; `pip-audit` and `npm audit` now report none |
| `CORS_ORIGINS` given as a normal environment variable crashed the server | Live server would not start on Render | Comma-separated list now read correctly (tested) |
| A failed Telegram alert could turn a successful payment into an error message | Customer confusion, retries | Alerts can no longer break a request (tested) |
| One inline script in the page | Blocked a strict security policy | Moved to its own file |

## Known limits (by design, for a single small restaurant)

- One server instance: login limits and live updates are kept in memory.
- KHQR confirmation depends on ABA's Telegram message. If ABA's bot is late, the order waits;
  staff can always check ABA Mobile and confirm by hand in Payments.
- Two customers paying the exact same amount within the same few minutes need a staff click.

## Reporting a problem

If you find a security problem, do not post it publicly. Contact the owner directly.
