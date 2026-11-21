"""Money: accounts, transactions, budgets, EMIs and bills, debts and savings goals.
Amounts and free text are encrypted; dates, kinds and categories stay plain for filtering."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPk
from app.db.encrypted import EncryptedDecimal, EncryptedText


def _user() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )


class FinancialAccount(UUIDPk, CreatedAt, Base):
    __tablename__ = "financial_accounts"
    __table_args__ = (
        CheckConstraint("kind IN ('bank','cash','card','wallet','loan')", name="kind"),
    )

    user_id: Mapped[uuid.UUID] = _user()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="bank")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    opening_balance: Mapped[Decimal] = mapped_column(
        EncryptedDecimal("financial_accounts.opening_balance"), nullable=False
    )
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Transaction(UUIDPk, CreatedAt, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("kind IN ('expense','income','transfer')", name="kind"),
        CheckConstraint("source IN ('manual','voice','chat','csv')", name="source"),
        Index("ix_transactions_user_day", "user_id", "occurred_on"),
        UniqueConstraint("user_id", "import_hash", name="uq_transactions_user_import"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="SET NULL"), index=True
    )
    to_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="SET NULL")
    )
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(EncryptedDecimal("transactions.amount"), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="Other")
    description: Mapped[str] = mapped_column(
        EncryptedText("transactions.description"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(EncryptedText("transactions.notes"))
    source: Mapped[str] = mapped_column(String(8), nullable=False, default="manual")
    # Keyed hash of date, amount and description, so the same CSV row isn't imported twice.
    import_hash: Mapped[str | None] = mapped_column(String(64))
    recurring_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recurring_payments.id", ondelete="SET NULL")
    )


class Budget(UUIDPk, CreatedAt, Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_budgets_user_category"),)

    user_id: Mapped[uuid.UUID] = _user()
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    monthly_limit: Mapped[Decimal] = mapped_column(
        EncryptedDecimal("budgets.monthly_limit"), nullable=False
    )


class RecurringPayment(UUIDPk, CreatedAt, Base):
    """EMIs, bills and subscriptions. Reminders only: NEXUS never pays anything."""

    __tablename__ = "recurring_payments"
    __table_args__ = (
        CheckConstraint("kind IN ('emi','bill','subscription','rent','other')", name="kind"),
        CheckConstraint("day_of_month BETWEEN 1 AND 31", name="day"),
    )

    user_id: Mapped[uuid.UUID] = _user()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="bill")
    amount: Mapped[Decimal] = mapped_column(
        EncryptedDecimal("recurring_payments.amount"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="Bills")
    day_of_month: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    # For EMIs: how many instalments are left; null for open-ended bills.
    remaining: Mapped[int | None] = mapped_column(Integer)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_accounts.id", ondelete="SET NULL")
    )
    remind_days: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_paid_on: Mapped[date | None] = mapped_column(Date)
    last_reminded_on: Mapped[date | None] = mapped_column(Date)


class Debt(UUIDPk, CreatedAt, Base):
    __tablename__ = "debts"

    user_id: Mapped[uuid.UUID] = _user()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    balance: Mapped[Decimal] = mapped_column(EncryptedDecimal("debts.balance"), nullable=False)
    annual_rate: Mapped[Decimal] = mapped_column(
        EncryptedDecimal("debts.annual_rate"), nullable=False
    )
    min_payment: Mapped[Decimal] = mapped_column(
        EncryptedDecimal("debts.min_payment"), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SavingsGoal(UUIDPk, CreatedAt, Base):
    __tablename__ = "savings_goals"

    user_id: Mapped[uuid.UUID] = _user()
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    target: Mapped[Decimal] = mapped_column(
        EncryptedDecimal("savings_goals.target"), nullable=False
    )
    saved: Mapped[Decimal] = mapped_column(EncryptedDecimal("savings_goals.saved"), nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
