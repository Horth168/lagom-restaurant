"""Role-based permissions.

Every protected endpoint declares the permission it needs, e.g.
`Depends(require("menu.edit"))`. The backend checks it on every request, so
hiding a button in the frontend is never the only protection.
"""
from app.models.enums import Role

ALL_PERMISSIONS: dict[str, str] = {
    "dashboard.view": "See the dashboard overview",
    "menu.view": "See products and categories in admin",
    "menu.edit": "Create and edit products, categories, options, promotions",
    "tables.manage": "Create tables and print QR codes",
    "orders.view": "See all orders",
    "orders.create": "Create orders at the POS",
    "orders.cancel": "Cancel orders",
    "orders.discount": "Give discounts at the POS",
    "payments.view": "See payment records",
    "payments.cash": "Take cash payments",
    "payments.refund": "Refund payments",
    "kds.kitchen": "Use the kitchen display",
    "kds.drinks": "Use the drinks display",
    "kds.dessert": "Use the dessert display",
    "inventory.view": "See stock levels",
    "inventory.edit": "Record purchases and stock adjustments, edit recipes",
    "finance.view": "See financial reports",
    "finance.edit": "Record expenses",
    "staff.manage": "Create and edit staff accounts",
    "settings.edit": "Change exchange rate, currency and integrations",
    "audit.view": "See the audit log",
}

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.OWNER: set(ALL_PERMISSIONS),
    Role.ADMIN: set(ALL_PERMISSIONS) - {"settings.edit", "audit.view"},
    Role.CASHIER: {
        "menu.view", "orders.view", "orders.create", "orders.discount",
        "payments.view", "payments.cash",
    },
    Role.KITCHEN: {"kds.kitchen", "kds.dessert"},
    Role.DRINKS: {"kds.drinks", "kds.dessert"},
    Role.INVENTORY: {"menu.view", "inventory.view", "inventory.edit"},
}

# Only the owner may create other owners or give out these permissions
OWNER_ONLY = {"settings.edit", "audit.view"}


def permissions_for(role: Role, extra: list[str] | None = None) -> set[str]:
    perms = set(ROLE_PERMISSIONS.get(role, set()))
    for p in extra or []:
        if p in ALL_PERMISSIONS:
            perms.add(p)
    return perms


def station_permission(station: str) -> str:
    return f"kds.{station.lower()}"

