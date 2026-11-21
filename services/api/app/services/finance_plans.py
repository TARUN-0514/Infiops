"""EMIs and bills (reminders and marking paid), debt payoff plans and savings goals.
NEXUS never pays anything: marking paid only records what the owner already paid."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Debt, RecurringPayment, SavingsGoal, Transaction, User
from app.services import finance, notify

CENT = Decimal("0.01")


async def owned_recurring(db: AsyncSession, user_id: uuid.UUID, rid: uuid.UUID) -> RecurringPayment:
    p = await db.get(RecurringPayment, rid)
    if p is None or p.user_id != user_id:
        raise LookupError("Payment not found.")
    return p


def recurring_out(p: RecurringPayment, today: date) -> dict[str, Any]:
    due = finance.next_due(p, today) if p.active else None
    return {
        "id": str(p.id),
        "name": p.name,
        "kind": p.kind,
        "amount": p.amount,
        "category": p.category,
        "day_of_month": p.day_of_month,
        "starts_on": p.starts_on.isoformat(),
        "remaining": p.remaining,
        "account_id": str(p.account_id) if p.account_id else None,
        "remind_days": p.remind_days,
        "active": p.active,
        "last_paid_on": p.last_paid_on.isoformat() if p.last_paid_on else None,
        "next_due": due.isoformat() if due else None,
        "days_left": (due - today).days if due else None,
    }


async def mark_paid(
    db: AsyncSession, user_id: uuid.UUID, p: RecurringPayment, paid_on: date, amount: Decimal | None
) -> Transaction:
    if not p.active:
        raise ValueError("This payment is finished or paused.")
    due = finance.next_due(p, paid_on)
    tx = await finance.add_transaction(
        db,
        user_id,
        kind="expense",
        amount=amount or p.amount,
        occurred_on=paid_on,
        description=p.name,
        category=p.category,
        account_id=p.account_id,
        recurring_id=p.id,
    )
    p.last_paid_on = due if due <= paid_on else paid_on
    if p.remaining is not None:
        p.remaining = max(0, p.remaining - 1)
        if p.remaining == 0:
            p.active = False
    return tx


async def send_reminders(db: AsyncSession, user: User, today: date) -> int:
    """One reminder per payment per cycle, remind_days before it's due (or when overdue)."""
    sent = 0
    rows = await db.scalars(
        select(RecurringPayment).where(
            RecurringPayment.user_id == user.id, RecurringPayment.active.is_(True)
        )
    )
    for p in rows:
        due = finance.next_due(p, today)
        if (due - today).days > p.remind_days:
            continue
        if p.last_reminded_on and p.last_reminded_on >= due - timedelta(days=p.remind_days):
            continue  # already reminded for this cycle
        when = "today" if due == today else ("overdue" if due < today else f"on {due:%d %b}")
        await notify.notify(
            db,
            user.id,
            kind="bill",
            title=f"{p.name} due {when}",
            body=f"₹{p.amount:,.2f}. Mark it paid in Finance once you've paid it.",
            link="/finance?tab=bills",
        )
        p.last_reminded_on = today
        sent += 1
    return sent


# --- debts --------------------------------------------------------------------------

Strategy = Literal["avalanche", "snowball"]


@dataclass
class _D:
    id: str
    name: str
    balance: Decimal
    rate: Decimal
    min: Decimal
    interest: Decimal = Decimal(0)
    paid_off_month: int | None = None


def payoff_plan(
    debts: list[Debt], extra: Decimal, strategy: Strategy, max_months: int = 600
) -> dict[str, Any]:
    """Month-by-month simulation: minimums on every debt, then the extra on the target debt
    (highest rate first for avalanche, smallest balance first for snowball)."""
    state = [
        _D(str(d.id), d.name, d.balance, d.annual_rate / 100 / 12, d.min_payment)
        for d in debts
        if d.balance > 0
    ]
    if not state:
        return {"months": 0, "total_interest": Decimal(0), "order": [], "feasible": True}
    total_interest = Decimal(0)
    month = 0
    while any(s.balance > 0 for s in state):
        month += 1
        if month > max_months:
            return {
                "months": None,
                "total_interest": None,
                "order": [],
                "feasible": False,
                "reason": "At these payments the debts never get paid off. "
                "Raise the minimums or the extra amount.",
            }
        for s in state:
            if s.balance > 0:
                interest = (s.balance * s.rate).quantize(CENT, ROUND_HALF_UP)
                s.balance += interest
                s.interest += interest
                total_interest += interest
        budget = extra + sum((s.min for s in state if s.balance > 0), Decimal(0))
        for s in state:
            if s.balance > 0:
                pay = min(s.min, s.balance, budget)
                s.balance -= pay
                budget -= pay
        live = [s for s in state if s.balance > 0]
        if strategy == "avalanche":
            live.sort(key=lambda s: (-s.rate, s.balance))
        else:
            live.sort(key=lambda s: (s.balance, -s.rate))
        for s in live:
            if budget <= 0:
                break
            pay = min(budget, s.balance)
            s.balance -= pay
            budget -= pay
        for s in state:
            if s.balance <= 0 and s.paid_off_month is None:
                s.paid_off_month = month
    order = sorted(state, key=lambda s: s.paid_off_month or 0)
    return {
        "months": month,
        "total_interest": total_interest,
        "order": [
            {"id": s.id, "name": s.name, "paid_off_month": s.paid_off_month, "interest": s.interest}
            for s in order
        ],
        "feasible": True,
    }


# --- savings goals --------------------------------------------------------------------


def goal_out(g: SavingsGoal, today: date) -> dict[str, Any]:
    left = max(Decimal(0), g.target - g.saved)
    monthly = None
    if g.target_date and left > 0:
        months = max(1, (g.target_date.year - today.year) * 12 + g.target_date.month - today.month)
        monthly = (left / months).quantize(CENT, ROUND_HALF_UP)
    return {
        "id": str(g.id),
        "name": g.name,
        "target": g.target,
        "saved": g.saved,
        "left": left,
        "percent": int(min(Decimal(100), g.saved / g.target * 100)) if g.target else 0,
        "target_date": g.target_date.isoformat() if g.target_date else None,
        "monthly_needed": monthly,
    }
