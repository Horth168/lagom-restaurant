from enum import StrEnum


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    CASHIER = "CASHIER"
    KITCHEN = "KITCHEN"
    DRINKS = "DRINKS"
    INVENTORY = "INVENTORY"


class Station(StrEnum):
    KITCHEN = "KITCHEN"
    DRINKS = "DRINKS"
    DESSERT = "DESSERT"


class OrderChannel(StrEnum):
    QR = "QR"  # customer scanned the table QR code
    POS_DINE_IN = "POS_DINE_IN"
    POS_TAKEAWAY = "POS_TAKEAWAY"
    TELEGRAM = "TELEGRAM"


class OrderStatus(StrEnum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"  # payment verified, waiting for the kitchen to accept
    PREPARING = "PREPARING"
    READY = "READY"
    SERVED = "SERVED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"  # never paid


# Statuses where the kitchen can see the order
KITCHEN_VISIBLE = (OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY)


class ItemStatus(StrEnum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    READY = "READY"
    SERVED = "SERVED"
    CANCELLED = "CANCELLED"


class PaymentProvider(StrEnum):
    ABA_PAYWAY = "ABA_PAYWAY"
    CASH = "CASH"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


class Currency(StrEnum):
    USD = "USD"
    KHR = "KHR"


class StockMovementKind(StrEnum):
    PURCHASE = "PURCHASE"
    ADJUSTMENT = "ADJUSTMENT"
    SALE = "SALE"  # deducted by an order
    SALE_REVERSAL = "SALE_REVERSAL"  # order cancelled after deduction
    WASTE = "WASTE"


class ExpenseCategory(StrEnum):
    INGREDIENTS = "INGREDIENTS"
    SALARIES = "SALARIES"
    RENT = "RENT"
    ELECTRICITY = "ELECTRICITY"
    WATER = "WATER"
    PACKAGING = "PACKAGING"
    MARKETING = "MARKETING"
    EQUIPMENT = "EQUIPMENT"
    OTHER = "OTHER"


class OptionSelection(StrEnum):
    SINGLE = "SINGLE"  # e.g. size, sugar level
    MULTIPLE = "MULTIPLE"  # e.g. toppings, extras
