"""Finance: transactions, balances, budgets and monthly summaries. Amounts are always positive;
the kind (expense, income, transfer) gives the direction. Everything is computed from stored
rows; nothing is estimated or invented."""

from __future__ import annotations

import calendar
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Budget, FinancialAccount, RecurringPayment, Transaction

EXPENSE_CATEGORIES = [
    "Food",
    "Groceries",
    "Transport",
    "Fuel",
    "Rent",
    "Bills",
    "Shopping",
    "Health",
    "Fitness",
    "Entertainment",
    "Travel",
    "Education",
    "EMI",
    "Family",
    "Gifts",
    "Investments",
    "Fees",
    "Other",
]
INCOME_CATEGORIES = ["Salary", "Bonus", "Interest", "Refund", "Other income"]
CATEGORIES = EXPENSE_CATEGORIES + INCOME_CATEGORIES

# Simple keyword rules for imported rows and quick entry. The owner can change any category.
KEYWORDS: list[tuple[str, str]] = [
    (r"swiggy|zomato|restaurant|cafe|domino|pizza|mcdonald|kfc|starbucks", "Food"),
    (
        r"bigbasket|blinkit|zepto|dmart|grocer|instamart|more retail|bazaar|reliance fresh"
        r"|supermarket|kirana",
        "Groceries",
    ),
    (r"uber|\bola\b|rapido|\bmetro\b|irctc|\bbus\b|taxi|\bauto\b", "Transport"),
    (r"petrol|fuel|hpcl|bpcl|indian oil|shell", "Fuel"),
    (r"rent\b", "Rent"),
    (
        r"electric|bescom|tneb|water bill|broadband|airtel|jio|vodafone|vi |gas bill|recharge",
        "Bills",
    ),
    (r"amazon|flipkart|myntra|ajio|nykaa|croma", "Shopping"),
    (r"pharma|apollo|medplus|hospital|clinic|doctor|1mg|netmeds", "Health"),
    (r"gym|cult\.?fit|decathlon", "Fitness"),
    (r"netflix|prime video|hotstar|spotify|bookmyshow|pvr|inox|steam", "Entertainment"),
    (r"makemytrip|goibibo|indigo|air india|vistara|oyo|airbnb|hotel", "Travel"),
    (r"udemy|coursera|offsec|book|course|exam", "Education"),
    (r"\bemi\b|loan", "EMI"),
    (r"mutual fund|sip|zerodha|groww|ppf|nps", "Investments"),
    (r"salary|payroll", "Salary"),
    (r"interest", "Interest"),
    (r"refund|cashback|reversal", "Refund"),
]


def guess_category(text: str, kind: str = "expense") -> str:
    low = text.lower()
    for pattern, cat in KEYWORDS:
        if re.search(pattern, low):
            if (cat in INCOME_CATEGORIES) == (kind == "income"):
                return cat
    return "Other income" if kind == "income" else "Other"


def parse_amount(raw: str | float | int | Decimal) -> Decimal:
    """'₹1,250.50', '1.2k', '2 lakh', '(450)' -> positive Decimal. ValueError if not a number."""
    if isinstance(raw, int | float | Decimal):
        value = Decimal(str(raw))
    else:
        s = (
            raw.strip()
            .lower()
            .replace("₹", "")
            .replace("rs.", "")
            .replace("rs", "")
            .replace("inr", "")
        )
        s = s.replace(",", "").replace(" ", "").strip("()+-")
        mult = Decimal(1)
        for suffix, m in (("lakh", 100_000), ("lac", 100_000), ("cr", 10_000_000), ("k", 1000)):
            if s.endswith(suffix):
                s, mult = s[: -len(suffix)], Decimal(m)
                break
        try:
            value = Decimal(s) * mult
        except InvalidOperation as exc:
            raise ValueError(f"'{raw}' isn't an amount.") from exc
    value = abs(value).quantize(Decimal("0.01"))
    if value == 0 or value > Decimal("1000000000"):
        raise ValueError("Use an amount above 0 and below 100 crore.")
    return value


INCOME_WORDS = re.compile(r"\b(salary|received|got|income|refund|cashback|interest|bonus)\b", re.I)


def parse_quick(text: str) -> dict[str, Any]:
    """'450 swiggy dinner', 'swiggy 450', 'salary 85,000', 'got 2k refund' -> a transaction."""
    m = re.search(r"(?:₹|rs\.?\s*)?(\d[\d,]*(?:\.\d+)?\s*(?:k|lakh|lac|cr)?)\b", text, re.I)
    if not m:
        raise ValueError("Include an amount, like '450 swiggy dinner'.")
    amount = parse_amount(m.group(1))
    desc = (text[: m.start()] + " " + text[m.end() :]).strip(" -,:")
    desc = re.sub(
        r"\s+", " ", re.sub(r"(?i)\b(rs\.?|inr|₹|spent|paid|for|on)\b", " ", desc)
    ).strip()
    kind = "income" if INCOME_WORDS.search(text) else "expense"
    desc = desc or ("Income" if kind == "income" else "Expense")
    return {
        "kind": kind,
        "amount": amount,
        "description": desc[:1].upper() + desc[1:],
        "category": guess_category(desc, kind),
        "source": "manual",
    }


def month_bounds(month: str) -> tuple[date, date]:
    """'2026-11' -> first and last day."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", month)
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise ValueError("Use a month like 2026-11.")
    y, mo = int(m.group(1)), int(m.group(2))
    return date(y, mo, 1), date(y, mo, calendar.monthrange(y, mo)[1])


def shift_month(d: date, months: int) -> date:
    idx = d.year * 12 + d.month - 1 + months
    return date(idx // 12, idx % 12 + 1, 1)


async def owned_account(
    db: AsyncSession, user_id: uuid.UUID, account_id: uuid.UUID
) -> FinancialAccount:
    acc = await db.get(FinancialAccount, account_id)
    if acc is None or acc.user_id != user_id:
        raise LookupError("Account not found.")
    return acc


async def owned_transaction(db: AsyncSession, user_id: uuid.UUID, tx_id: uuid.UUID) -> Transaction:
    tx = await db.get(Transaction, tx_id)
    if tx is None or tx.user_id != user_id:
        raise LookupError("Transaction not found.")
    return tx


async def accounts(db: AsyncSession, user_id: uuid.UUID) -> list[FinancialAccount]:
    return list(
        await db.scalars(
            select(FinancialAccount)
            .where(FinancialAccount.user_id == user_id)
            .order_by(FinancialAccount.archived, FinancialAccount.created_at)
        )
    )


async def transactions_between(
    db: AsyncSession, user_id: uuid.UUID, start: date, end: date
) -> list[Transaction]:
    return list(
        await db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.occurred_on >= start,
                Transaction.occurred_on <= end,
            )
            .order_by(Transaction.occurred_on.desc(), Transaction.created_at.desc())
        )
    )


async def add_transaction(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    kind: str,
    amount: Decimal,
    occurred_on: date,
    description: str,
    category: str | None = None,
    account_id: uuid.UUID | None = None,
    to_account_id: uuid.UUID | None = None,
    notes: str | None = None,
    source: str = "manual",
    import_hash: str | None = None,
    recurring_id: uuid.UUID | None = None,
) -> Transaction:
    if kind not in ("expense", "income", "transfer"):
        raise ValueError("Kind must be expense, income or transfer.")
    if account_id:
        await owned_account(db, user_id, account_id)
    if kind == "transfer":
        if not (account_id and to_account_id) or account_id == to_account_id:
            raise ValueError("A transfer needs two different accounts.")
        await owned_account(db, user_id, to_account_id)
        category = "Transfer"
    else:
        to_account_id = None
        category = category or guess_category(description, kind)
        allowed = INCOME_CATEGORIES if kind == "income" else EXPENSE_CATEGORIES
        if category not in allowed:
            raise ValueError(f"Pick a category from: {', '.join(allowed)}.")
    tx = Transaction(
        user_id=user_id,
        kind=kind,
        amount=amount,
        occurred_on=occurred_on,
        description=description.strip()[:300] or category,
        category=category,
        account_id=account_id,
        to_account_id=to_account_id,
        notes=(notes or "").strip() or None,
        source=source,
        import_hash=import_hash,
        recurring_id=recurring_id,
    )
    db.add(tx)
    await db.flush()
    return tx


def balances(accs: list[FinancialAccount], txs: list[Transaction]) -> dict[uuid.UUID, Decimal]:
    out = {a.id: a.opening_balance for a in accs}
    for t in txs:
        if t.kind == "expense" and t.account_id in out:
            out[t.account_id] -= t.amount
        elif t.kind == "income" and t.account_id in out:
            out[t.account_id] += t.amount
        elif t.kind == "transfer":
            if t.account_id in out:
                out[t.account_id] -= t.amount
            if t.to_account_id in out:
                out[t.to_account_id] += t.amount
    return out


async def all_transactions(db: AsyncSession, user_id: uuid.UUID) -> list[Transaction]:
    return list(await db.scalars(select(Transaction).where(Transaction.user_id == user_id)))


@dataclass
class CategoryLine:
    category: str
    spent: Decimal
    budget: Decimal | None


async def month_summary(
    db: AsyncSession, user_id: uuid.UUID, month: str, today: date
) -> dict[str, Any]:
    start, end = month_bounds(month)
    txs = await transactions_between(db, user_id, start, end)
    income = sum((t.amount for t in txs if t.kind == "income"), Decimal(0))
    expense = sum((t.amount for t in txs if t.kind == "expense"), Decimal(0))
    by_cat: dict[str, Decimal] = defaultdict(Decimal)
    daily: dict[date, Decimal] = defaultdict(Decimal)
    for t in txs:
        if t.kind == "expense":
            by_cat[t.category] += t.amount
            daily[t.occurred_on] += t.amount
    budgets = {
        b.category: b.monthly_limit
        for b in await db.scalars(select(Budget).where(Budget.user_id == user_id))
    }
    cats = sorted(set(by_cat) | set(budgets), key=lambda c: -by_cat.get(c, Decimal(0)))
    lines = [
        {
            "category": c,
            "spent": by_cat.get(c, Decimal(0)),
            "budget": budgets.get(c),
            "left": (budgets[c] - by_cat.get(c, Decimal(0))) if c in budgets else None,
        }
        for c in cats
    ]
    days_in = (end - start).days + 1
    elapsed = days_in if today > end else max(0, (today - start).days + 1) if today >= start else 0
    return {
        "month": month,
        "income": income,
        "expense": expense,
        "net": income - expense,
        "count": len(txs),
        "categories": lines,
        "daily": [
            {
                "day": (start.replace(day=d)).isoformat(),
                "spent": daily.get(start.replace(day=d), Decimal(0)),
            }
            for d in range(1, days_in + 1)
        ],
        "days_tracked": len({t.occurred_on for t in txs}),
        "days_elapsed": elapsed,
        "over_budget": [c for c, lim in budgets.items() if by_cat.get(c, Decimal(0)) > lim],
    }


async def cash_flow(
    db: AsyncSession, user_id: uuid.UUID, months: int, today: date
) -> list[dict[str, Any]]:
    first = shift_month(today.replace(day=1), -(months - 1))
    txs = await transactions_between(
        db, user_id, first, today.replace(day=calendar.monthrange(today.year, today.month)[1])
    )
    buckets: dict[str, dict[str, Decimal]] = {}
    for i in range(months):
        m = shift_month(first, i)
        buckets[f"{m.year}-{m.month:02d}"] = {"income": Decimal(0), "expense": Decimal(0)}
    for t in txs:
        key = f"{t.occurred_on.year}-{t.occurred_on.month:02d}"
        if key in buckets and t.kind in ("income", "expense"):
            buckets[key][t.kind] += t.amount
    return [
        {
            "month": k,
            "income": v["income"],
            "expense": v["expense"],
            "net": v["income"] - v["expense"],
        }
        for k, v in buckets.items()
    ]


def next_due(p: RecurringPayment, today: date) -> date:
    """The earliest unpaid due date: may be before today (overdue), but never more than a month
    back, so an old unpaid month doesn't nag forever."""
    if p.last_paid_on:
        month = shift_month(p.last_paid_on.replace(day=1), 1)
    else:
        month = p.starts_on.replace(day=1)
    floor = shift_month(today.replace(day=1), -1)
    month = max(month, floor)
    for i in range(24):
        m = shift_month(month, i)
        due = m.replace(day=min(p.day_of_month, calendar.monthrange(m.year, m.month)[1]))
        if due >= p.starts_on and (today - due).days <= 31:
            return due
    return today
