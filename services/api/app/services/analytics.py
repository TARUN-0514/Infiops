"""Analytics from stored data only: tasks, time, habits, goals, workload, money and fitness.

Each section reports what was recorded in the period and says when nothing was. Rates are
None, not zero, when there is nothing to divide by, so the UI can say "no data" instead of
showing a made-up 0%. Finance and health values are decrypted here and never leave the
owner's machine through a model call."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CalendarEvent,
    Goal,
    Habit,
    LearningSession,
    LearningTrack,
    Project,
    Task,
    User,
    WorkLog,
)
from app.services import calendar as cal
from app.services import finance as fin
from app.services import fitness as fit
from app.services import personal
from app.services.insights import OPEN, _local, day_bounds, day_loads, is_overdue

RANGES = (7, 30, 90)


def bucket_of(day: date, weekly: bool) -> date:
    return day - timedelta(days=day.weekday()) if weekly else day


def buckets(first: date, last: date, weekly: bool) -> list[date]:
    out, d = [], bucket_of(first, weekly)
    while d <= last:
        out.append(d)
        d += timedelta(days=7 if weekly else 1)
    return out


def pct(part: int, whole: int) -> int | None:
    return round(100 * part / whole) if whole else None


def _num(v: Decimal | None) -> float | None:
    return None if v is None else float(v)


def _attending(e: CalendarEvent) -> bool:
    return e.status != "cancelled" and not any(
        a.get("self") and a.get("response") == "declined" for a in e.attendees
    )


# --- tasks ------------------------------------------------------------------------


async def task_stats(
    db: AsyncSession, user: User, first: date, last: date, weekly: bool, now: datetime
) -> dict[str, Any]:
    tz = user.timezone
    start, _ = day_bounds(first, tz)
    _, end = day_bounds(last, tz)
    rows = list(
        await db.scalars(
            select(Task).where(
                Task.user_id == user.id,
                Task.parent_task_id.is_(None),
                or_(
                    Task.created_at >= start,
                    Task.completed_at >= start,
                    Task.status.in_(OPEN),
                ),
            )
        )
    )
    keys = buckets(first, last, weekly)
    created: dict[date, int] = defaultdict(int)
    completed: dict[date, int] = defaultdict(int)
    for t in rows:
        if start <= t.created_at < end:
            created[bucket_of(_local(t.created_at, tz).date(), weekly)] += 1
        if t.completed_at and start <= t.completed_at < end:
            completed[bucket_of(_local(t.completed_at, tz).date(), weekly)] += 1

    made = [t for t in rows if start <= t.created_at < end and t.status != "cancelled"]
    done_in = [t for t in rows if t.completed_at and start <= t.completed_at < end]
    with_due = [t for t in done_in if t.due_at]

    def on_time(t: Task) -> bool:
        assert t.completed_at and t.due_at
        if t.all_day:
            return _local(t.completed_at, tz).date() <= _local(t.due_at, tz).date()
        return t.completed_at <= t.due_at

    today_start, _ = day_bounds(_local(now, tz).date(), tz)
    overdue = [t for t in rows if is_overdue(t, now, today_start)]
    projects = {
        p.id: p.name for p in await db.scalars(select(Project).where(Project.user_id == user.id))
    }
    by_project: dict[str, int] = defaultdict(int)
    for t in done_in:
        by_project[projects.get(t.project_id, "No project") if t.project_id else "No project"] += 1
    pushed = sorted(
        (t for t in rows if t.status in OPEN and t.postponed_count > 0),
        key=lambda t: -t.postponed_count,
    )
    return {
        "series": [
            {
                "bucket": k.isoformat(),
                "created": created.get(k, 0),
                "completed": completed.get(k, 0),
            }
            for k in keys
        ],
        "created": len(made),
        "completed": len(done_in),
        "completion_rate": pct(sum(1 for t in made if t.status == "done"), len(made)),
        "on_time_rate": pct(sum(1 for t in with_due if on_time(t)), len(with_due)),
        "with_due": len(with_due),
        "open": sum(1 for t in rows if t.status in OPEN),
        "overdue": len(overdue),
        "by_project": [
            {"project": k, "completed": v}
            for k, v in sorted(by_project.items(), key=lambda kv: -kv[1])
        ],
        "postponed": [
            {"id": str(t.id), "title": t.title, "times": t.postponed_count} for t in pushed[:6]
        ],
    }


# --- time -------------------------------------------------------------------------


async def time_allocation(
    db: AsyncSession, user: User, first: date, last: date, weekly: bool
) -> dict[str, Any]:
    tz = user.timezone
    logs = list(
        await db.scalars(
            select(WorkLog).where(
                WorkLog.user_id == user.id, WorkLog.day >= first, WorkLog.day <= last
            )
        )
    )
    projects = {
        p.id: p.name for p in await db.scalars(select(Project).where(Project.user_id == user.id))
    }
    work: dict[str, int] = defaultdict(int)
    unlogged = 0
    for w in logs:
        if not w.minutes:
            # Entries written automatically when a task is completed carry no time.
            unlogged += w.source != "task"
            continue
        work[projects.get(w.project_id, "No project") if w.project_id else "No project"] += (
            w.minutes
        )
    start, _ = day_bounds(first, tz)
    _, end = day_bounds(last, tz)
    events = [
        e for e in await cal.list_events(db, user.id, start, end) if not e.all_day and _attending(e)
    ]
    keys = buckets(first, last, weekly)
    meet: dict[date, int] = defaultdict(int)
    for e in events:
        s, f = max(e.starts_at, start), min(e.ends_at, end)
        meet[bucket_of(_local(s, tz).date(), weekly)] += int((f - s).total_seconds() // 60)
    study = sum(
        s.minutes
        for s in await db.scalars(
            select(LearningSession)
            .join(LearningTrack, LearningTrack.id == LearningSession.track_id)
            .where(
                LearningTrack.user_id == user.id,
                LearningSession.day >= first,
                LearningSession.day <= last,
            )
        )
    )
    workouts = await fit.sessions_between(db, user.id, first, last)
    gym = sum(s.minutes or 0 for s in workouts)
    categories: list[dict[str, Any]] = [
        *({"label": k, "group": "Work log", "minutes": v} for k, v in work.items()),
        {"label": "Meetings", "group": "Calendar", "minutes": sum(meet.values())},
        {"label": "Study", "group": "Learning", "minutes": study},
        {"label": "Workouts", "group": "Fitness", "minutes": gym},
    ]
    categories = sorted((c for c in categories if c["minutes"]), key=lambda c: -int(c["minutes"]))
    return {
        "categories": categories,
        "total_minutes": sum(c["minutes"] for c in categories),
        "work_entries_without_minutes": unlogged,
        "meetings": {
            "count": len(events),
            "series": [{"bucket": k.isoformat(), "minutes": meet.get(k, 0)} for k in keys],
        },
    }


# --- habits and goals -------------------------------------------------------------


async def habit_stats(
    db: AsyncSession, user: User, first: date, last: date
) -> list[dict[str, Any]]:
    habits = list(
        await db.scalars(select(Habit).where(Habit.user_id == user.id, Habit.archived.is_(False)))
    )
    days = await fit.habit_days(db, [h.id for h in habits], first - timedelta(days=366), last)
    span = (last - first).days + 1
    out = []
    for h in habits:
        since = max(first, _local(h.created_at, user.timezone).date())
        n_days = (last - since).days + 1
        target = max(1, round(h.per_week * n_days / 7)) if n_days > 0 else 0
        done = sum(1 for d in days.get(h.id, set()) if first <= d <= last)
        out.append(
            {
                "id": str(h.id),
                "name": h.name,
                "per_week": h.per_week,
                "done": done,
                "target": target,
                "rate": pct(min(done, target), target),
                "streak": fit.streak(days.get(h.id, set()), last),
                "tracked_days": min(span, max(0, n_days)),
            }
        )
    return sorted(out, key=lambda h: (h["rate"] is None, -(h["rate"] or 0)))


def expected_progress(g: Goal, today: date, tz: str) -> int | None:
    """Where a straight line from creation to target date would put the goal today."""
    if g.target_date is None:
        return None
    begin = _local(g.created_at, tz).date()
    total = (g.target_date - begin).days
    if total <= 0:
        return 100
    return max(0, min(100, round(100 * (today - begin).days / total)))


async def goal_stats(db: AsyncSession, user: User, today: date) -> list[dict[str, Any]]:
    goals = list(
        await db.scalars(
            select(Goal)
            .where(Goal.user_id == user.id, Goal.status == "active")
            .order_by(Goal.target_date.nulls_last(), Goal.created_at)
        )
    )
    out = []
    for g in goals:
        progress = personal.goal_progress(g)
        expected = expected_progress(g, today, user.timezone)
        out.append(
            {
                "id": str(g.id),
                "title": g.title,
                "area": g.area,
                "progress": progress,
                "expected": expected,
                "target_date": g.target_date.isoformat() if g.target_date else None,
                "days_left": (g.target_date - today).days if g.target_date else None,
                "behind": expected is not None and progress + 15 < expected,
                "milestones": len(g.milestones),
            }
        )
    return out


# --- money and fitness --------------------------------------------------------------


async def finance_trends(db: AsyncSession, user: User, today: date, months: int) -> dict[str, Any]:
    flow = await fin.cash_flow(db, user.id, months, today)
    current = await fin.month_summary(db, user.id, f"{today.year}-{today.month:02d}", today)
    has_data = any(m["income"] or m["expense"] for m in flow)
    return {
        "has_data": has_data,
        "months": [
            {
                "month": m["month"],
                "income": _num(m["income"]),
                "expense": _num(m["expense"]),
                "net": _num(m["net"]),
            }
            for m in flow
        ],
        "top_categories": [
            {"category": c["category"], "spent": _num(c["spent"]), "budget": _num(c["budget"])}
            for c in current["categories"][:6]
            if c["spent"]
        ],
        "over_budget": current["over_budget"],
    }


async def fitness_trends(
    db: AsyncSession, user: User, first: date, last: date, weekly: bool
) -> dict[str, Any]:
    sessions = await fit.sessions_between(db, user.id, first, last)
    keys = buckets(first, last, weekly)
    count: dict[date, int] = defaultdict(int)
    minutes: dict[date, int] = defaultdict(int)
    for s in sessions:
        k = bucket_of(s.day, weekly)
        count[k] += 1
        minutes[k] += s.minutes or 0
    vals = fit.daily_values(await fit.logs_between(db, user.id, first, last))
    weight = sorted(vals.get("weight_kg", {}).items())
    sleep = vals.get("sleep_hours", {})
    return {
        "workouts": len(sessions),
        "series": [
            {"bucket": k.isoformat(), "workouts": count.get(k, 0), "minutes": minutes.get(k, 0)}
            for k in keys
        ],
        "weight": [{"day": d.isoformat(), "kg": float(v)} for d, v in weight],
        "weight_change": float(weight[-1][1] - weight[0][1]) if len(weight) >= 2 else None,
        "sleep_avg": round(float(sum(sleep.values(), Decimal(0)) / len(sleep)), 1)
        if sleep
        else None,
        "sleep_days": len(sleep),
    }


# --- overview ---------------------------------------------------------------------


async def overview(
    db: AsyncSession, user: User, days: int, now: datetime | None = None
) -> dict[str, Any]:
    if days not in RANGES:
        raise ValueError("Range must be 7, 30 or 90 days.")
    now = now or datetime.now(UTC)
    today = _local(now, user.timezone).date()
    first = today - timedelta(days=days - 1)
    weekly = days > 31
    loads = await day_loads(db, user, today, 14, now)
    return {
        "range": {
            "days": days,
            "from": first.isoformat(),
            "to": today.isoformat(),
            "bucket": "week" if weekly else "day",
        },
        "tasks": await task_stats(db, user, first, today, weekly, now),
        "time": await time_allocation(db, user, first, today, weekly),
        "habits": await habit_stats(db, user, first, today),
        "goals": await goal_stats(db, user, today),
        "workload": [d.out() for d in loads],
        "finance": await finance_trends(db, user, today, 6 if days > 31 else 3),
        "fitness": await fitness_trends(db, user, first, today, weekly),
    }
