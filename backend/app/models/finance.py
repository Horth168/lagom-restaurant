from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

from app.db import Base
from app.models.base import TimestampMixin, str_enum
from app.models.enums import Currency, ExpenseCategory


class Expense(TimestampMixin, Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[ExpenseCategory] = mapped_column(str_enum(ExpenseCategory), index=True)
    spent_on: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(255))
    # The amount as entered, in its own currency…
    currency: Mapped[Currency] = mapped_column(str_enum(Currency))
    amount_minor: Mapped[int] = mapped_column(Integer)
    # …and its USD value at the rate of that day (used in reports; never recalculated)
    khr_per_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount_usd_cents: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
