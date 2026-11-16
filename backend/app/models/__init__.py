"""Import every model so SQLAlchemy and Alembic know about all tables."""
from app.models.users import AppSetting, AuditLog, User
from app.models.menu import Category, Option, OptionGroup, Product, Promotion, StoredPhoto
from app.models.tables import DiningTable, TableSession
from app.models.orders import DailyCounter, Order, OrderItem
from app.models.payments import BankNotice, Payment, PaymentEvent, Refund
from app.models.inventory import Ingredient, Purchase, PurchaseLine, RecipeItem, StockMovement, Supplier
from app.models.finance import Expense
from app.models.extras import CashShift, Deal, ItemRating, LoyaltyCard, OrderReview, ServiceRequest

__all__ = [
    "AppSetting", "AuditLog", "User",
    "Category", "Option", "OptionGroup", "Product", "Promotion", "StoredPhoto",
    "DiningTable", "TableSession",
    "DailyCounter", "Order", "OrderItem",
    "BankNotice", "Payment", "PaymentEvent", "Refund",
    "Ingredient", "Purchase", "PurchaseLine", "RecipeItem", "StockMovement", "Supplier",
    "Expense",
    "CashShift", "Deal", "ItemRating", "LoyaltyCard", "OrderReview", "ServiceRequest",
]
