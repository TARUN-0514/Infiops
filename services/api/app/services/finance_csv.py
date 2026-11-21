"""Bank statement CSV import: detect columns, preview, then import without duplicates."""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Transaction
from app.services import finance

MAX_ROWS = 5000
DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%d %b %y",
    "%d-%b-%y",
    "%d.%m.%Y",
    "%m/%d/%Y",
)
ROLES = {
    "date": r"^(txn |transaction |value |posting )?date$|^date",
    "description": r"narration|description|particulars|details|remarks|merchant|payee",
    "amount": r"^amount( \(inr\))?$|^amt$",
    "debit": r"debit|withdrawal|dr\b|paid out|spent",
    "credit": r"credit|deposit|cr\b|paid in|received",
    "drcr": r"^(cr/dr|dr/cr|dr / cr|type)$",
}


@dataclass
class Mapping:
    date: int
    description: int
    amount: int | None = None
    debit: int | None = None
    credit: int | None = None
    drcr: int | None = None
    day_first: bool = True


@dataclass
class Parsed:
    header: list[str]
    mapping: Mapping | None
    rows: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _table(raw: bytes) -> list[list[str]]:
    text = raw.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if len(rows) > MAX_ROWS + 50:
        raise ValueError(f"That file has more than {MAX_ROWS} rows. Split it by month.")
    return rows


def detect(header: list[str]) -> Mapping | None:
    found: dict[str, int] = {}
    for i, name in enumerate(header):
        low = name.strip().lower()
        if re.search(ROLES["drcr"], low):  # before debit/credit, which would also match
            found.setdefault("drcr", i)
            continue
        for role, pattern in ROLES.items():
            if role not in found and role != "drcr" and re.search(pattern, low):
                found[role] = i
                break
    if "date" not in found or "description" not in found:
        return None
    if "amount" not in found and "debit" not in found and "credit" not in found:
        return None
    return Mapping(
        date=found["date"],
        description=found["description"],
        amount=found.get("amount"),
        debit=found.get("debit"),
        credit=found.get("credit"),
        drcr=found.get("drcr"),
    )


def parse_date(raw: str, day_first: bool = True) -> date:
    s = (
        raw.strip().split(" ")[0]
        if re.match(r"^\d{4}-\d{2}-\d{2}[ T]", raw.strip())
        else raw.strip()
    )
    formats = DATE_FORMATS if day_first else ("%m/%d/%Y", *DATE_FORMATS)
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{raw}' isn't a date NEXUS understands.")


def _header_index(rows: list[list[str]]) -> int:
    """Bank exports often start with account details; the header is the first row that maps."""
    for i, row in enumerate(rows[:30]):
        if detect(row) is not None:
            return i
    return 0


def row_hash(day: date, kind: str, amount: Decimal, description: str) -> str:
    key = get_settings().encryption_key.get_secret_value().encode()
    msg = f"{day.isoformat()}|{kind}|{amount}|{' '.join(description.lower().split())}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def parse(raw: bytes, mapping: Mapping | None = None) -> Parsed:
    rows = _table(raw)
    if not rows:
        raise ValueError("The file is empty.")
    h = _header_index(rows)
    header = [c.strip() for c in rows[h]]
    m = mapping or detect(header)
    out = Parsed(header=header, mapping=m)
    if m is None:
        out.errors.append(
            "Couldn't find the date, description and amount columns. Pick them below."
        )
        return out
    width = len(header)
    for n, row in enumerate(rows[h + 1 :], start=h + 2):
        row = row + [""] * (width - len(row))
        try:
            day = parse_date(row[m.date], m.day_first)
            desc = row[m.description].strip()
            if m.amount is not None and row[m.amount].strip():
                cell = row[m.amount].strip()
                negative = cell.startswith("-") or cell.endswith("dr") or cell.startswith("(")
                amount = finance.parse_amount(cell)
                kind = "expense" if negative else "income"
                if m.drcr is not None and row[m.drcr].strip():
                    kind = "income" if row[m.drcr].strip().lower().startswith("cr") else "expense"
            elif m.debit is not None and row[m.debit].strip() not in ("", "0", "0.00", "-"):
                amount, kind = finance.parse_amount(row[m.debit]), "expense"
            elif m.credit is not None and row[m.credit].strip() not in ("", "0", "0.00", "-"):
                amount, kind = finance.parse_amount(row[m.credit]), "income"
            else:
                continue  # balance-only or summary lines
        except ValueError as exc:
            if len(out.errors) < 20:
                out.errors.append(f"Row {n}: {exc}")
            continue
        out.rows.append(
            {
                "occurred_on": day,
                "kind": kind,
                "amount": amount,
                "description": desc[:300],
                "category": finance.guess_category(desc, kind),
                "hash": row_hash(day, kind, amount, desc),
            }
        )
    return out


async def mark_duplicates(db: AsyncSession, user_id: uuid.UUID, parsed: Parsed) -> int:
    hashes = [r["hash"] for r in parsed.rows]
    existing = (
        set(
            await db.scalars(
                select(Transaction.import_hash).where(
                    Transaction.user_id == user_id, Transaction.import_hash.in_(hashes)
                )
            )
        )
        if hashes
        else set()
    )
    seen: set[str] = set()
    dupes = 0
    for r in parsed.rows:
        r["duplicate"] = r["hash"] in existing or r["hash"] in seen
        dupes += r["duplicate"]
        seen.add(r["hash"])
    return dupes


async def import_rows(
    db: AsyncSession, user_id: uuid.UUID, parsed: Parsed, account_id: uuid.UUID | None
) -> int:
    await mark_duplicates(db, user_id, parsed)
    added = 0
    for r in parsed.rows:
        if r["duplicate"]:
            continue
        await finance.add_transaction(
            db,
            user_id,
            kind=r["kind"],
            amount=r["amount"],
            occurred_on=r["occurred_on"],
            description=r["description"],
            category=r["category"],
            account_id=account_id,
            source="csv",
            import_hash=r["hash"],
        )
        added += 1
    return added
