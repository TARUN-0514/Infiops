"""Finance: accounts, transactions, CSV import, budgets, EMIs and bills, debts, savings goals.
Reminders only; NEXUS never moves money."""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.ai.timeutil import now_local
from app.api.deps import DB, Auth
from app.api.routes.common import bad_request, not_found
from app.models import Budget, Debt, RecurringPayment, SavingsGoal, Transaction
from app.services import audit, finance, finance_csv, finance_plans

router = APIRouter(prefix="/finance", tags=["finance"])
MAX_CSV = 5 * 1024 * 1024
Money = Annotated[Decimal, Field(gt=0, le=Decimal("1000000000"), decimal_places=2)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _today(auth: Auth) -> date:
    return now_local(auth.user.timezone).date()


# --- accounts -----------------------------------------------------------------------


class AccountIn(_In):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["bank", "cash", "card", "wallet", "loan"] = "bank"
    opening_balance: Decimal = Field(
        Decimal(0), ge=Decimal("-1000000000"), le=Decimal("1000000000")
    )
    archived: bool = False


@router.get("/meta")
async def meta(auth: Auth) -> dict[str, Any]:
    t = _today(auth)
    return {
        "expense_categories": finance.EXPENSE_CATEGORIES,
        "income_categories": finance.INCOME_CATEGORIES,
        "month": f"{t.year}-{t.month:02d}",
        "today": t.isoformat(),
        "currency": "INR",
    }


@router.get("/accounts")
async def list_accounts(db: DB, auth: Auth) -> list[dict[str, Any]]:
    accs = await finance.accounts(db, auth.user.id)
    bal = finance.balances(accs, await finance.all_transactions(db, auth.user.id))
    return [
        {
            "id": str(a.id),
            "name": a.name,
            "kind": a.kind,
            "currency": a.currency,
            "opening_balance": a.opening_balance,
            "balance": bal[a.id],
            "archived": a.archived,
        }
        for a in accs
    ]


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(body: AccountIn, db: DB, auth: Auth) -> dict[str, str]:
    from app.models import FinancialAccount

    acc = FinancialAccount(user_id=auth.user.id, **body.model_dump())
    db.add(acc)
    await db.commit()
    return {"id": str(acc.id)}


async def _acc(db: DB, auth: Auth, account_id: uuid.UUID) -> Any:
    try:
        return await finance.owned_account(db, auth.user.id, account_id)
    except LookupError:
        not_found("Account not found.")


@router.patch("/accounts/{account_id}")
async def update_account(
    account_id: uuid.UUID, body: AccountIn, db: DB, auth: Auth
) -> dict[str, str]:
    acc = await _acc(db, auth, account_id)
    for k, v in body.model_dump().items():
        setattr(acc, k, v)
    await db.commit()
    return {"id": str(acc.id)}


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: uuid.UUID, db: DB, auth: Auth) -> None:
    acc = await _acc(db, auth, account_id)
    audit.record(db, "finance.account_deleted", user_id=auth.user.id, target=str(acc.id))
    await db.delete(acc)
    await db.commit()


# --- transactions -------------------------------------------------------------------


class TxIn(_In):
    kind: Literal["expense", "income", "transfer"]
    amount: Money
    occurred_on: date
    description: str = Field(min_length=1, max_length=300)
    category: str | None = Field(None, max_length=40)
    account_id: uuid.UUID | None = None
    to_account_id: uuid.UUID | None = None
    notes: str | None = Field(None, max_length=2000)


def tx_out(t: Transaction) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "kind": t.kind,
        "amount": t.amount,
        "occurred_on": t.occurred_on.isoformat(),
        "description": t.description,
        "category": t.category,
        "account_id": str(t.account_id) if t.account_id else None,
        "to_account_id": str(t.to_account_id) if t.to_account_id else None,
        "notes": t.notes,
        "source": t.source,
    }


@router.get("/transactions")
async def list_transactions(
    db: DB,
    auth: Auth,
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    category: str | None = None,
    account_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=100),
) -> list[dict[str, Any]]:
    try:
        start, end = finance.month_bounds(month)
    except ValueError as exc:
        bad_request(str(exc))
    rows = await finance.transactions_between(db, auth.user.id, start, end)
    if category:
        rows = [t for t in rows if t.category == category]
    if account_id:
        rows = [t for t in rows if account_id in (t.account_id, t.to_account_id)]
    if q:
        low = q.lower()  # descriptions are encrypted, so search after decrypting
        rows = [t for t in rows if low in t.description.lower() or low in (t.notes or "").lower()]
    return [tx_out(t) for t in rows]


@router.post("/transactions", status_code=status.HTTP_201_CREATED)
async def create_transaction(body: TxIn, db: DB, auth: Auth) -> dict[str, Any]:
    try:
        tx = await finance.add_transaction(db, auth.user.id, **body.model_dump())
    except (ValueError, LookupError) as exc:
        bad_request(str(exc))
    await db.commit()
    return tx_out(tx)


class QuickIn(_In):
    text: str = Field(min_length=2, max_length=200)
    occurred_on: date | None = None
    account_id: uuid.UUID | None = None


@router.post("/transactions/quick", status_code=status.HTTP_201_CREATED)
async def quick_add(body: QuickIn, db: DB, auth: Auth) -> dict[str, Any]:
    """'450 swiggy dinner' or 'salary 85000': parsed on the server, no model needed."""
    try:
        parsed = finance.parse_quick(body.text)
        tx = await finance.add_transaction(
            db,
            auth.user.id,
            occurred_on=body.occurred_on or _today(auth),
            account_id=body.account_id,
            **parsed,
        )
    except (ValueError, LookupError) as exc:
        bad_request(str(exc))
    await db.commit()
    return tx_out(tx)


async def _tx(db: DB, auth: Auth, tx_id: uuid.UUID) -> Transaction:
    try:
        return await finance.owned_transaction(db, auth.user.id, tx_id)
    except LookupError:
        not_found("Transaction not found.")


@router.patch("/transactions/{tx_id}")
async def update_transaction(tx_id: uuid.UUID, body: TxIn, db: DB, auth: Auth) -> dict[str, Any]:
    old = await _tx(db, auth, tx_id)
    source, import_hash, recurring_id = old.source, old.import_hash, old.recurring_id
    await db.delete(old)
    await db.flush()
    try:
        tx = await finance.add_transaction(
            db,
            auth.user.id,
            **body.model_dump(),
            source=source,
            import_hash=import_hash,
            recurring_id=recurring_id,
        )
    except (ValueError, LookupError) as exc:
        await db.rollback()
        bad_request(str(exc))
    await db.commit()
    return tx_out(tx)


@router.delete("/transactions/{tx_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(tx_id: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _tx(db, auth, tx_id))
    await db.commit()


@router.get("/summary")
async def summary(
    db: DB, auth: Auth, month: str = Query(..., pattern=r"^\d{4}-\d{2}$")
) -> dict[str, Any]:
    try:
        out = await finance.month_summary(db, auth.user.id, month, _today(auth))
    except ValueError as exc:
        bad_request(str(exc))
    rec = await db.scalars(
        select(RecurringPayment).where(
            RecurringPayment.user_id == auth.user.id, RecurringPayment.active.is_(True)
        )
    )
    today = _today(auth)
    upcoming = sorted(
        (finance_plans.recurring_out(p, today) for p in rec), key=lambda r: r["next_due"] or ""
    )
    return {
        **out,
        "upcoming": [u for u in upcoming if u["days_left"] is not None and u["days_left"] <= 14],
    }


@router.get("/cashflow")
async def cashflow(db: DB, auth: Auth, months: int = Query(6, ge=2, le=24)) -> list[dict[str, Any]]:
    return await finance.cash_flow(db, auth.user.id, months, _today(auth))


# --- CSV import ---------------------------------------------------------------------


async def _read_csv(file: UploadFile) -> bytes:
    raw = await file.read(MAX_CSV + 1)
    if len(raw) > MAX_CSV:
        bad_request("That file is over 5 MB. Export one month at a time.")
    if b"\x00" in raw[:4096]:
        bad_request("That isn't a CSV file. Export the statement as CSV from your bank.")
    return raw


def _mapping(raw: str | None) -> finance_csv.Mapping | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return finance_csv.Mapping(
            **{
                k: data.get(k) for k in ("date", "description", "amount", "debit", "credit", "drcr")
            },
            day_first=bool(data.get("day_first", True)),
        )
    except (ValueError, TypeError) as exc:
        bad_request(f"Column choice isn't valid: {exc}")


@router.post("/import/preview")
async def import_preview(
    db: DB,
    auth: Auth,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    try:
        parsed = finance_csv.parse(await _read_csv(file), _mapping(mapping))
    except (ValueError, IndexError) as exc:
        bad_request(str(exc) or "Couldn't read that file.")
    dupes = await finance_csv.mark_duplicates(db, auth.user.id, parsed)
    m = parsed.mapping
    return {
        "header": parsed.header,
        "mapping": m.__dict__ if m else None,
        "rows": [{**r, "hash": None} for r in parsed.rows[:200]],
        "total": len(parsed.rows),
        "duplicates": dupes,
        "expense": sum((r["amount"] for r in parsed.rows if r["kind"] == "expense"), Decimal(0)),
        "income": sum((r["amount"] for r in parsed.rows if r["kind"] == "income"), Decimal(0)),
        "errors": parsed.errors,
    }


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_csv(
    db: DB,
    auth: Auth,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
    account_id: Annotated[uuid.UUID | None, Form()] = None,
) -> dict[str, Any]:
    if account_id:
        await _acc(db, auth, account_id)
    try:
        parsed = finance_csv.parse(await _read_csv(file), _mapping(mapping))
    except (ValueError, IndexError) as exc:
        bad_request(str(exc) or "Couldn't read that file.")
    if parsed.mapping is None:
        bad_request("Pick the date, description and amount columns first.")
    added = await finance_csv.import_rows(db, auth.user.id, parsed, account_id)
    audit.record(db, "finance.csv_import", user_id=auth.user.id, added=added, rows=len(parsed.rows))
    await db.commit()
    return {"added": added, "duplicates": len(parsed.rows) - added, "errors": parsed.errors}


# --- budgets ----------------------------------------------------------------------------


class BudgetIn(_In):
    category: str
    monthly_limit: Money

    @field_validator("category")
    @classmethod
    def known(cls, v: str) -> str:
        if v not in finance.EXPENSE_CATEGORIES:
            raise ValueError("Pick an expense category.")
        return v


@router.get("/budgets")
async def list_budgets(db: DB, auth: Auth) -> list[dict[str, Any]]:
    rows = await db.scalars(
        select(Budget).where(Budget.user_id == auth.user.id).order_by(Budget.category)
    )
    return [{"category": b.category, "monthly_limit": b.monthly_limit} for b in rows]


@router.put("/budgets")
async def put_budgets(body: list[BudgetIn], db: DB, auth: Auth) -> list[dict[str, Any]]:
    cats = [b.category for b in body]
    if len(cats) != len(set(cats)):
        bad_request("Each category can have one budget.")
    for old in await db.scalars(select(Budget).where(Budget.user_id == auth.user.id)):
        await db.delete(old)
    await db.flush()
    for b in body:
        db.add(Budget(user_id=auth.user.id, category=b.category, monthly_limit=b.monthly_limit))
    await db.commit()
    return await list_budgets(db, auth)


# --- EMIs and bills -------------------------------------------------------------------


class RecurringIn(_In):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["emi", "bill", "subscription", "rent", "other"] = "bill"
    amount: Money
    category: str = "Bills"
    day_of_month: int = Field(ge=1, le=31)
    starts_on: date
    remaining: int | None = Field(None, ge=0, le=600)
    account_id: uuid.UUID | None = None
    remind_days: int = Field(2, ge=0, le=14)
    active: bool = True

    @field_validator("category")
    @classmethod
    def known(cls, v: str) -> str:
        if v not in finance.EXPENSE_CATEGORIES:
            raise ValueError("Pick an expense category.")
        return v


@router.get("/recurring")
async def list_recurring(db: DB, auth: Auth) -> list[dict[str, Any]]:
    today = _today(auth)
    rows = await db.scalars(
        select(RecurringPayment).where(RecurringPayment.user_id == auth.user.id)
    )
    out = [finance_plans.recurring_out(p, today) for p in rows]
    return sorted(out, key=lambda r: (not r["active"], r["next_due"] or "9999"))


async def _rec(db: DB, auth: Auth, rid: uuid.UUID) -> RecurringPayment:
    try:
        return await finance_plans.owned_recurring(db, auth.user.id, rid)
    except LookupError:
        not_found("Payment not found.")


@router.post("/recurring", status_code=status.HTTP_201_CREATED)
async def create_recurring(body: RecurringIn, db: DB, auth: Auth) -> dict[str, Any]:
    if body.account_id:
        await _acc(db, auth, body.account_id)
    p = RecurringPayment(user_id=auth.user.id, **body.model_dump())
    db.add(p)
    await db.commit()
    return finance_plans.recurring_out(p, _today(auth))


@router.patch("/recurring/{rid}")
async def update_recurring(rid: uuid.UUID, body: RecurringIn, db: DB, auth: Auth) -> dict[str, Any]:
    p = await _rec(db, auth, rid)
    if body.account_id:
        await _acc(db, auth, body.account_id)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    await db.commit()
    return finance_plans.recurring_out(p, _today(auth))


@router.delete("/recurring/{rid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring(rid: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _rec(db, auth, rid))
    await db.commit()


class PaidIn(_In):
    paid_on: date | None = None
    amount: Money | None = None


@router.post("/recurring/{rid}/paid")
async def mark_paid(rid: uuid.UUID, body: PaidIn, db: DB, auth: Auth) -> dict[str, Any]:
    p = await _rec(db, auth, rid)
    try:
        tx = await finance_plans.mark_paid(
            db, auth.user.id, p, body.paid_on or _today(auth), body.amount
        )
    except (ValueError, LookupError) as exc:
        bad_request(str(exc))
    await db.commit()
    return {"payment": finance_plans.recurring_out(p, _today(auth)), "transaction": tx_out(tx)}


# --- debts --------------------------------------------------------------------------------


class DebtIn(_In):
    name: str = Field(min_length=1, max_length=80)
    balance: Decimal = Field(ge=0, le=Decimal("1000000000"))
    annual_rate: Decimal = Field(ge=0, le=100)
    min_payment: Money


def debt_out(d: Debt) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "name": d.name,
        "balance": d.balance,
        "annual_rate": d.annual_rate,
        "min_payment": d.min_payment,
    }


async def _debts(db: DB, auth: Auth) -> list[Debt]:
    return list(
        await db.scalars(select(Debt).where(Debt.user_id == auth.user.id).order_by(Debt.created_at))
    )


@router.get("/debts")
async def list_debts(db: DB, auth: Auth) -> list[dict[str, Any]]:
    return [debt_out(d) for d in await _debts(db, auth)]


@router.post("/debts", status_code=status.HTTP_201_CREATED)
async def create_debt(body: DebtIn, db: DB, auth: Auth) -> dict[str, Any]:
    d = Debt(user_id=auth.user.id, **body.model_dump())
    db.add(d)
    await db.commit()
    return debt_out(d)


async def _debt(db: DB, auth: Auth, did: uuid.UUID) -> Debt:
    d = await db.get(Debt, did)
    if d is None or d.user_id != auth.user.id:
        not_found("Debt not found.")
    return d


@router.patch("/debts/{did}")
async def update_debt(did: uuid.UUID, body: DebtIn, db: DB, auth: Auth) -> dict[str, Any]:
    d = await _debt(db, auth, did)
    for k, v in body.model_dump().items():
        setattr(d, k, v)
    await db.commit()
    return debt_out(d)


@router.delete("/debts/{did}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_debt(did: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _debt(db, auth, did))
    await db.commit()


@router.get("/debts/plan")
async def debt_plan(
    db: DB,
    auth: Auth,
    extra: Annotated[Decimal, Query(ge=0, le=100_000_000)] = Decimal(0),
) -> dict[str, Any]:
    debts = await _debts(db, auth)
    return {
        "avalanche": finance_plans.payoff_plan(debts, extra, "avalanche"),
        "snowball": finance_plans.payoff_plan(debts, extra, "snowball"),
    }


# --- savings goals ------------------------------------------------------------------------


class GoalIn(_In):
    name: str = Field(min_length=1, max_length=80)
    target: Money
    saved: Decimal = Field(Decimal(0), ge=0, le=Decimal("1000000000"))
    target_date: date | None = None


@router.get("/goals")
async def list_goals(db: DB, auth: Auth) -> list[dict[str, Any]]:
    rows = await db.scalars(
        select(SavingsGoal)
        .where(SavingsGoal.user_id == auth.user.id)
        .order_by(SavingsGoal.created_at)
    )
    return [finance_plans.goal_out(g, _today(auth)) for g in rows]


@router.post("/goals", status_code=status.HTTP_201_CREATED)
async def create_goal(body: GoalIn, db: DB, auth: Auth) -> dict[str, Any]:
    g = SavingsGoal(user_id=auth.user.id, **body.model_dump())
    db.add(g)
    await db.commit()
    return finance_plans.goal_out(g, _today(auth))


async def _goal(db: DB, auth: Auth, gid: uuid.UUID) -> SavingsGoal:
    g = await db.get(SavingsGoal, gid)
    if g is None or g.user_id != auth.user.id:
        not_found("Goal not found.")
    return g


@router.patch("/goals/{gid}")
async def update_goal(gid: uuid.UUID, body: GoalIn, db: DB, auth: Auth) -> dict[str, Any]:
    g = await _goal(db, auth, gid)
    for k, v in body.model_dump().items():
        setattr(g, k, v)
    await db.commit()
    return finance_plans.goal_out(g, _today(auth))


@router.delete("/goals/{gid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(gid: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _goal(db, auth, gid))
    await db.commit()
