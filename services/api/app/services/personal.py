"""Goals, routines, lists, journal and important dates."""

from __future__ import annotations

import calendar
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Goal, ImportantDate, Routine, RoutineLog, User
from app.services import notify


def goal_progress(g: Goal) -> int:
    if g.milestones:
        return round(100 * sum(1 for m in g.milestones if m.get("done")) / len(g.milestones))
    return g.progress


def goal_out(g: Goal, today: date) -> dict[str, Any]:
    return {
        "id": str(g.id),
        "title": g.title,
        "area": g.area,
        "why": g.why,
        "target_date": g.target_date.isoformat() if g.target_date else None,
        "days_left": (g.target_date - today).days if g.target_date else None,
        "status": g.status,
        "progress": goal_progress(g),
        "milestones": g.milestones,
    }


def routine_due(r: Routine, day: date) -> bool:
    return r.active and (not r.weekdays or day.weekday() in r.weekdays)


async def routine_logs(
    db: AsyncSession, ids: list[uuid.UUID], start: date, end: date
) -> dict[tuple[uuid.UUID, date], list[int]]:
    if not ids:
        return {}
    rows = await db.scalars(
        select(RoutineLog).where(
            RoutineLog.routine_id.in_(ids), RoutineLog.day >= start, RoutineLog.day <= end
        )
    )
    return {(x.routine_id, x.day): list(x.done_steps) for x in rows}


async def set_steps(db: AsyncSession, r: Routine, day: date, done: list[int]) -> list[int]:
    clean = sorted({i for i in done if 0 <= i < len(r.steps)})
    log = await db.get(RoutineLog, (r.id, day))
    if log is None:
        if clean:
            db.add(RoutineLog(routine_id=r.id, day=day, done_steps=clean))
    elif clean:
        log.done_steps = clean
    else:
        await db.delete(log)
    await db.flush()
    return clean


def next_occurrence(d: ImportantDate, today: date) -> date | None:
    """The next time this date comes round (today counts). Feb 29 falls on Feb 28."""

    def make(year: int) -> date:
        last = calendar.monthrange(year, d.month)[1]
        return date(year, d.month, min(d.day, last))

    if not d.yearly:
        if d.year is None:
            return None
        when = make(d.year)
        return when if when >= today - timedelta(days=30) else None
    this = make(today.year)
    return this if this >= today else make(today.year + 1)


def date_out(d: ImportantDate, today: date) -> dict[str, Any]:
    nxt = next_occurrence(d, today)
    turning = (nxt.year - d.year) if (nxt and d.yearly and d.year) else None
    return {
        "id": str(d.id),
        "title": d.title,
        "kind": d.kind,
        "month": d.month,
        "day": d.day,
        "year": d.year,
        "yearly": d.yearly,
        "remind_days": d.remind_days,
        "notes": d.notes,
        "next": nxt.isoformat() if nxt else None,
        "days_left": (nxt - today).days if nxt else None,
        "turning": turning,
    }


def check_date(month: int, day: int, year: int | None, yearly: bool) -> None:
    if not yearly and year is None:
        raise ValueError("A one-off date needs a year.")
    probe = year if year else 2024  # a leap year, so 29 Feb is allowed for yearly dates
    if day > calendar.monthrange(probe, month)[1]:
        raise ValueError("That day doesn't exist in that month.")


async def date_reminders(db: AsyncSession, user: User, today: date) -> int:
    sent = 0
    for d in await db.scalars(select(ImportantDate).where(ImportantDate.user_id == user.id)):
        nxt = next_occurrence(d, today)
        if nxt is None or not 0 <= (nxt - today).days <= d.remind_days:
            continue
        if d.last_reminded_on and d.last_reminded_on >= nxt - timedelta(days=d.remind_days):
            continue
        out = date_out(d, today)
        when = (
            "today"
            if nxt == today
            else ("tomorrow" if out["days_left"] == 1 else f"on {nxt:%d %b}")
        )
        extra = f" (turning {out['turning']})" if d.kind == "birthday" and out["turning"] else ""
        await notify.notify(
            db,
            user.id,
            kind="date",
            title=f"{d.title} {when}{extra}",
            body=d.notes or "",
            link="/personal?tab=dates",
        )
        d.last_reminded_on = today
        sent += 1
    return sent
