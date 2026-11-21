"""Finance: entry, CSV import, budgets, bills, debts, goals; encrypted at rest; local only."""

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.ai.gateway import ModelGateway, set_gateway
from app.ai.providers import ScriptedProvider
from app.ai.timeutil import now_local
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import AuditLog, FinancialAccount, Notification, User
from app.services import finance, finance_plans
from tests.conftest import auth_headers, register_and_login
from tests.test_chat import _conv, _send

API = "/api/v1/finance"


def _today() -> date:
    return now_local("Asia/Kolkata").date()


async def _tx(client: AsyncClient, h: dict[str, str], **body: Any) -> dict[str, Any]:
    payload = {
        "kind": "expense",
        "amount": "100",
        "occurred_on": _today().isoformat(),
        "description": "x",
        **body,
    }
    r = await client.post(f"{API}/transactions", json=payload, headers=h)
    assert r.status_code == 201, r.text
    return dict(r.json())


# --- parsing -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ("₹1,250.50", "1250.50"),
        ("2.5k", "2500"),
        ("1.2 lakh", "120000"),
        ("(450)", "450"),
        ("3 cr", "30000000"),
    ],
)
def test_parse_amount(raw: str, value: str) -> None:
    assert finance.parse_amount(raw) == Decimal(value)


def test_parse_amount_rejects_zero_and_words() -> None:
    for bad in ("0", "abc", ""):
        with pytest.raises(ValueError):
            finance.parse_amount(bad)


def test_parse_quick_and_categories() -> None:
    q = finance.parse_quick("450 swiggy dinner")
    assert q["kind"] == "expense" and q["amount"] == Decimal(450) and q["category"] == "Food"
    q = finance.parse_quick("salary 85000")
    assert q["kind"] == "income" and q["category"] == "Salary"
    assert finance.guess_category("Uber to office") == "Transport"


# --- API -----------------------------------------------------------------------------


async def test_transactions_summary_and_encryption(client: AsyncClient) -> None:
    h = await auth_headers(client)
    acc = (
        await client.post(
            f"{API}/accounts", json={"name": "HDFC", "opening_balance": "10000"}, headers=h
        )
    ).json()
    month = _today().strftime("%Y-%m")
    await _tx(client, h, amount="1200.50", description="Big Bazaar groceries", account_id=acc["id"])
    await _tx(
        client,
        h,
        kind="income",
        amount="50000",
        description="Salary",
        category="Salary",
        account_id=acc["id"],
    )
    r = await client.post(f"{API}/transactions/quick", json={"text": "300 uber"}, headers=h)
    assert r.status_code == 201 and r.json()["category"] == "Transport"

    s = (await client.get(f"{API}/summary", params={"month": month}, headers=h)).json()
    assert Decimal(s["income"]) == Decimal(50000) and Decimal(s["expense"]) == Decimal("1500.50")
    assert Decimal(s["net"]) == Decimal("48499.50") and s["count"] == 3
    accounts = (await client.get(f"{API}/accounts", headers=h)).json()
    assert Decimal(accounts[0]["balance"]) == Decimal("58799.50")

    found = (
        await client.get(f"{API}/transactions", params={"month": month, "q": "bazaar"}, headers=h)
    ).json()
    assert len(found) == 1 and found[0]["description"] == "Big Bazaar groceries"

    # Money and descriptions are ciphertext in the database.
    async with get_sessionmaker()() as db:
        raw = (await db.execute(text("SELECT amount, description FROM transactions"))).all()
    assert all(isinstance(a, bytes) and b"1200" not in a and b"Bazaar" not in d for a, d in raw)

    bad = await client.post(
        f"{API}/transactions",
        json={"kind": "expense", "amount": "0", "occurred_on": month + "-01", "description": "x"},
        headers=h,
    )
    assert bad.status_code == 422
    bad = await client.post(
        f"{API}/transactions",
        json={
            "kind": "expense",
            "amount": "5",
            "occurred_on": month + "-01",
            "description": "x",
            "category": "Nope",
        },
        headers=h,
    )
    assert bad.status_code == 400


async def test_transfer_needs_two_own_accounts(client: AsyncClient) -> None:
    h = await auth_headers(client)
    a = (await client.post(f"{API}/accounts", json={"name": "Bank"}, headers=h)).json()
    b = (
        await client.post(f"{API}/accounts", json={"name": "Cash", "kind": "cash"}, headers=h)
    ).json()
    r = await client.post(
        f"{API}/transactions",
        json={
            "kind": "transfer",
            "amount": "500",
            "occurred_on": _today().isoformat(),
            "description": "ATM",
            "account_id": a["id"],
        },
        headers=h,
    )
    assert r.status_code == 400
    await _tx(
        client,
        h,
        kind="transfer",
        amount="500",
        description="ATM",
        account_id=a["id"],
        to_account_id=b["id"],
    )
    bal = {
        x["name"]: Decimal(x["balance"])
        for x in (await client.get(f"{API}/accounts", headers=h)).json()
    }
    assert bal == {"Bank": Decimal(-500), "Cash": Decimal(500)}
    s = (
        await client.get(f"{API}/summary", params={"month": _today().strftime("%Y-%m")}, headers=h)
    ).json()
    assert Decimal(s["expense"]) == 0  # a transfer isn't spending


async def test_owner_isolation(client: AsyncClient) -> None:
    h = await auth_headers(client)
    async with get_sessionmaker()() as db:
        other = User(email="x@example.com", password_hash="x", display_name="X")
        db.add(other)
        await db.flush()
        acc = FinancialAccount(user_id=other.id, name="Theirs", opening_balance=Decimal(5))
        db.add(acc)
        await db.flush()
        tx = await finance.add_transaction(
            db,
            other.id,
            kind="expense",
            amount=Decimal(9),
            occurred_on=_today(),
            description="theirs",
        )
        await db.commit()
    month = _today().strftime("%Y-%m")
    assert (await client.delete(f"{API}/transactions/{tx.id}", headers=h)).status_code == 404
    assert (
        await client.get(f"{API}/transactions", params={"month": month}, headers=h)
    ).json() == []
    assert (await client.get(f"{API}/accounts", headers=h)).json() == []
    r = await _post_tx_raw(client, h, account_id=str(acc.id))
    assert r.status_code in (400, 404)


async def _post_tx_raw(client: AsyncClient, h: dict[str, str], **body: Any) -> Any:
    payload = {
        "kind": "expense",
        "amount": "1",
        "occurred_on": _today().isoformat(),
        "description": "x",
    }
    return await client.post(f"{API}/transactions", json={**payload, **body}, headers=h)


HDFC = b"""HDFC BANK Ltd.
Account No : XXXX1234

Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance
01/11/26,UPI-SWIGGY-BANGALORE,0001,01/11/26,450.00,,9550.00
02/11/26,NEFT-ACME CORP SALARY,0002,02/11/26,,85000.00,94550.00
03/11/26,POS AMAZON PAY,0003,03/11/26,"1,299.00",,93251.00
bad-date,???,0004,x,10.00,,1
"""

DRCR = b"""Txn Date;Description;Amount;Dr/Cr
2026-11-05;Rent November;25000;DR
2026-11-06;Refund;300;CR
"""


async def test_csv_preview_import_and_dedupe(client: AsyncClient) -> None:
    h = await auth_headers(client)
    files = {"file": ("hdfc.csv", HDFC, "text/csv")}
    p = (await client.post(f"{API}/import/preview", files=files, headers=h)).json()
    assert p["total"] == 3 and p["duplicates"] == 0 and len(p["errors"]) == 1
    assert [r["kind"] for r in p["rows"]] == ["expense", "income", "expense"]
    assert Decimal(p["expense"]) == Decimal("1749.00") and p["rows"][0]["category"] == "Food"

    r = await client.post(f"{API}/import", files=files, headers=h)
    assert r.status_code == 201 and r.json()["added"] == 3
    again = (await client.post(f"{API}/import", files=files, headers=h)).json()
    assert again == {"added": 0, "duplicates": 3, "errors": again["errors"]}

    r = await client.post(f"{API}/import", files={"file": ("b.csv", DRCR, "text/csv")}, headers=h)
    assert r.json()["added"] == 2
    rows = (await client.get(f"{API}/transactions", params={"month": "2026-11"}, headers=h)).json()
    kinds = {x["description"]: x["kind"] for x in rows}
    assert kinds["Rent November"] == "expense" and kinds["Refund"] == "income"
    async with get_sessionmaker()() as db:
        assert await db.scalar(select(AuditLog).where(AuditLog.action == "finance.csv_import"))

    r = await client.post(
        f"{API}/import/preview", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")}, headers=h
    )
    assert r.status_code == 200 and r.json()["mapping"] is None and r.json()["errors"]


async def test_budgets_and_over_budget(client: AsyncClient) -> None:
    h = await auth_headers(client)
    r = await client.put(
        f"{API}/budgets", json=[{"category": "Food", "monthly_limit": "1000"}], headers=h
    )
    assert r.status_code == 200
    await _tx(client, h, amount="1200", description="Dinner", category="Food")
    s = (
        await client.get(f"{API}/summary", params={"month": _today().strftime("%Y-%m")}, headers=h)
    ).json()
    food = next(c for c in s["categories"] if c["category"] == "Food")
    assert Decimal(food["left"]) == Decimal(-200) and "Food" in s["over_budget"]
    bad = await client.put(
        f"{API}/budgets",
        json=[
            {"category": "Food", "monthly_limit": "1"},
            {"category": "Food", "monthly_limit": "2"},
        ],
        headers=h,
    )
    assert bad.status_code == 400


async def test_emi_paid_and_reminders(client: AsyncClient) -> None:
    h = await auth_headers(client)
    today = _today()
    due = today + timedelta(days=1)
    r = await client.post(
        f"{API}/recurring",
        json={
            "name": "Car EMI",
            "kind": "emi",
            "amount": "12500",
            "category": "EMI" if "EMI" in finance.EXPENSE_CATEGORIES else "Bills",
            "day_of_month": due.day,
            "starts_on": (today - timedelta(days=40)).isoformat(),
            "remaining": 2,
            "remind_days": 2,
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    emi = r.json()
    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User))
        assert user is not None
        sent = await finance_plans.send_reminders(db, user, today)
        await db.commit()
        assert sent >= 1
        assert await finance_plans.send_reminders(db, user, today) == 0  # once per cycle
        assert await db.scalar(select(Notification).where(Notification.kind == "bill"))

    r = await client.post(f"{API}/recurring/{emi['id']}/paid", json={}, headers=h)
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["payment"]["remaining"] == 1 and after["payment"]["active"] is True
    assert (
        after["transaction"]["kind"] == "expense"
        and Decimal(after["transaction"]["amount"]) == 12500
    )
    assert after["payment"]["next_due"] != emi["next_due"]
    r = await client.post(f"{API}/recurring/{emi['id']}/paid", json={"amount": "12000"}, headers=h)
    assert r.json()["payment"]["remaining"] == 0 and r.json()["payment"]["active"] is False


def test_payoff_plan_avalanche_beats_snowball() -> None:
    from types import SimpleNamespace

    debts = [
        SimpleNamespace(
            id="a",
            name="Card",
            balance=Decimal(50000),
            annual_rate=Decimal(36),
            min_payment=Decimal(2500),
        ),
        SimpleNamespace(
            id="b",
            name="Friend",
            balance=Decimal(10000),
            annual_rate=Decimal(0),
            min_payment=Decimal(1000),
        ),
    ]
    av = finance_plans.payoff_plan(debts, Decimal(3000), "avalanche")  # type: ignore[arg-type]
    sb = finance_plans.payoff_plan(debts, Decimal(3000), "snowball")  # type: ignore[arg-type]
    assert Decimal(av["total_interest"]) <= Decimal(sb["total_interest"])
    assert av["months"] > 0


async def test_debts_and_goals_api(client: AsyncClient) -> None:
    h = await auth_headers(client)
    r = await client.post(
        f"{API}/debts",
        json={"name": "Card", "balance": "40000", "annual_rate": "36", "min_payment": "2000"},
        headers=h,
    )
    assert r.status_code == 201
    plan = (await client.get(f"{API}/debts/plan", params={"extra": "1000"}, headers=h)).json()
    assert plan["avalanche"]["feasible"] and plan["avalanche"]["months"] > 12
    await client.post(
        f"{API}/debts",
        json={"name": "Never", "balance": "100000", "annual_rate": "48", "min_payment": "100"},
        headers=h,
    )
    plan = (await client.get(f"{API}/debts/plan", headers=h)).json()
    assert plan["snowball"]["feasible"] is False and "never" in plan["snowball"]["reason"]
    g = await client.post(
        f"{API}/goals",
        json={
            "name": "Trip",
            "target": "60000",
            "saved": "15000",
            "target_date": (_today() + timedelta(days=180)).isoformat(),
        },
        headers=h,
    )
    assert g.status_code == 201, g.text
    goals = (await client.get(f"{API}/goals", headers=h)).json()
    assert goals[0]["percent"] == 25


# --- chat tools stay local -------------------------------------------------------------


@pytest.fixture
def cloud(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[ScriptedProvider, ScriptedProvider]]:
    monkeypatch.setattr(get_settings(), "cloud_enabled", True)
    local, remote = ScriptedProvider("local"), ScriptedProvider("anthropic")
    set_gateway(ModelGateway(get_settings(), {"local": local, "anthropic": remote}))
    yield local, remote
    set_gateway(None)


async def test_finance_tools_are_local_only(
    client: AsyncClient, cloud: tuple[ScriptedProvider, ScriptedProvider]
) -> None:
    local, remote = cloud
    h = await auth_headers(client)
    cid = await _conv(client, h)

    remote.push("I can't see your finances here.")
    events = await _send(client, h, cid, "how much did I spend?", cloud=True)
    names = {t.name for t in remote.requests[0].tools}
    assert "finance_summary" not in names and "finance_add_transaction" not in names
    assert "turn off" in remote.requests[0].system[-1]["text"].lower() or any(
        "Use cloud" in b["text"] for b in remote.requests[0].system
    )

    local.push(
        [
            {
                "name": "finance_add_transaction",
                "input": {"amount": "450", "description": "Swiggy dinner"},
            }
        ],
        "Logged ₹450.",
    )
    events = await _send(client, h, cid, "spent 450 on swiggy")
    assert events[0]["provider"] == "local"
    done = next(e for e in events if e["type"] == "tool.finished")
    assert done["status"] == "succeeded" and done["output"]["category"] == "Food"

    # Once money is in the conversation, cloud is refused for it.
    local.push("Still local.")
    events = await _send(client, h, cid, "now think hard", cloud=True)
    assert events[0]["provider"] == "local" and events[0]["cloud_blocked"] == "local_data"
    assert len(remote.requests) == 1


async def test_cloud_model_cannot_call_local_tool(
    client: AsyncClient, cloud: tuple[ScriptedProvider, ScriptedProvider]
) -> None:
    _, remote = cloud
    h = await auth_headers(client)
    cid = await _conv(client, h)
    remote.push([{"name": "finance_summary", "input": {}}], "ok")
    events = await _send(client, h, cid, "x", cloud=True)
    done = next(e for e in events if e["type"] == "tool.finished")
    assert done["status"] == "failed" and "local model" in done["error"]


async def test_routes_need_auth(client: AsyncClient) -> None:
    await register_and_login(client)
    assert (await client.get(f"{API}/accounts")).status_code == 401
