# Staff accounts, permissions and languages

## Roles

| Role | Typical person | Opens |
|---|---|---|
| Owner | You | Everything, including Settings and the Audit log |
| Manager (ADMIN) | Shop manager | Everything except Settings and the Audit log |
| Cashier | Counter | POS, orders, payments (cash and bank-payment matching), menu (view) |
| Kitchen | Cooks | Kitchen and Dessert screens |
| Drinks | Barista | Drinks and Dessert screens |
| Inventory | Stock keeper | Inventory (stock, purchases, recipes), menu (view) |

Admin → Staff → **Who can do what** shows the full table. The server checks these rules on
every action, so hiding a button is never the only protection.

**Extra permissions** give one person a little more without changing their role (for example a
senior cashier who may also cancel orders).

## Everyday tasks (Admin → Staff)

- **Add staff member**: name, email, role, language, first password. Give them the password in
  person; they can change it in *My account*.
- **Edit**: change role, extra permissions or language; untick *Account active* when someone
  leaves. Changes sign that person out so they apply immediately.
- **Reset password** (key icon) if someone forgets theirs.
- Safety rules: only the owner can create owners or change an owner; you cannot deactivate or
  demote yourself; LAGOM always keeps at least one active owner.

## My account

Click your name at the bottom of the sidebar to change your **language** or **password**.
Changing the password signs you out on every device.

## Audit log (owner only)

Admin → Audit log lists sign-ins, failed sign-ins, staff changes, price changes, discounts,
cancellations, refunds, stock adjustments, expenses and settings changes, with who, when and from
which network address. It cannot be edited from the app.

## Languages

- Every screen is available in **English, ខ្មែរ and 中文**. All words live in
  `frontend/src/i18n/en.json`, `km.json` and `zh.json`; a test fails if any language misses a word.
- Customers pick their language on the menu. Staff get **their own language when they sign in**.
- Messages from the server (e.g. "This item is sold out") are translated in one place,
  `backend/app/i18n.py`; a test fails if a new message has no Khmer and Chinese translation.
- Dates follow the chosen language where the device supports it (phones do; some desktop test
  browsers show Khmer dates in English format).
- Menu names and descriptions are entered per language in Admin → Menu.
- The Khmer and Chinese text was written carefully but should be **checked by a native speaker**
  before opening.
