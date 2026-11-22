"""Proactive detection: overdue work, email waiting too long for a reply, calendar
conflicts, overloaded days and tasks that keep getting pushed back.

Everything here is computed from stored rows. Nothing is guessed: an insight only
appears when the data shows it, and each one lists the items behind it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CalendarEvent, EmailMessage, Task, User
from app.services import calendar as cal

Severity = Literal["high", "medium", "low"]

# Thresholds. They are rules, not estimates, and the UI states them.
REPLY_WAIT_HOURS = 48
POSTPONED_MIN = 3
OVERLOAD_MEETING_MINUTES = 360  # six hours of meetings in one day
OVERLOAD_TASKS_DUE = 8
OVERLOAD_TIGHT_TASKS = 3  # this many tasks due with under an hour of free time
TIGHT_FREE_MINUTES = 60
LOOKAHEAD_DAYS = 7

OPEN = ("todo", "in_progress")


def day_bounds(day: date, tz: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(tz)
    start = datetime.combine(day, time(0), zone).astimezone(UTC)
    return start, start + timedelta(days=1)


def is_overdue(t: Task, now: datetime, today_start: datetime) -> bool:
    if t.due_at is None or t.status not in OPEN:
        return False
    return t.due_at < (today_start if t.all_day else now)


def _local(dt: datetime, tz: str) -> datetime:
    return dt.astimezone(ZoneInfo(tz))


@dataclass
class DayLoad:
    day: date
    meeting_minutes: int
    tasks_due: int
    free_minutes: int
    conflicts: int

    @property
    def reasons(self) -> list[str]:
        out = []
        if self.meeting_minutes >= OVERLOAD_MEETING_MINUTES:
            out.append(f"{self.meeting_minutes / 60:.1f} h of meetings")
        if self.tasks_due >= OVERLOAD_TASKS_DUE:
            out.append(f"{self.tasks_due} tasks due")
        elif self.tasks_due >= OVERLOAD_TIGHT_TASKS and self.free_minutes < TIGHT_FREE_MINUTES:
            out.append(
                f"{self.tasks_due} tasks due with {self.free_minutes} min free between 9 and 6"
            )
        return out

    @property
    def overloaded(self) -> bool:
        return bool(self.reasons)

    def out(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "meeting_minutes": self.meeting_minutes,
            "tasks_due": self.tasks_due,
            "free_minutes": self.free_minutes,
            "conflicts": self.conflicts,
            "overloaded": self.overloaded,
            "reasons": self.reasons,
        }


def _attending(e: CalendarEvent) -> bool:
    return e.status != "cancelled" and not any(
        a.get("self") and a.get("response") == "declined" for a in e.attendees
    )


async def day_loads(
    db: AsyncSession, user: User, first: date, days: int, now: datetime | None = None
) -> list[DayLoad]:
    """Meetings, tasks due and free working time for each day from `first`."""
    tz = user.timezone
    now = now or datetime.now(UTC)
    start, _ = day_bounds(first, tz)
    end, _ = day_bounds(first + timedelta(days=days), tz)
    events = [e for e in await cal.list_events(db, user.id, start, end) if _attending(e)]
    tasks = list(
        await db.scalars(
            select(Task).where(
                Task.user_id == user.id,
                Task.status.in_(OPEN),
                Task.due_at >= start,
                Task.due_at < end,
            )
        )
    )
    today = _local(now, tz).date()
    out = []
    for i in range(days):
        day = first + timedelta(days=i)
        d0, d1 = day_bounds(day, tz)
        todays = [e for e in events if e.starts_at < d1 and e.ends_at > d0]
        timed = [e for e in todays if not e.all_day]
        minutes = sum(
            int((min(e.ends_at, d1) - max(e.starts_at, d0)).total_seconds() // 60) for e in timed
        )
        free = cal.free_slots(timed, day, tz, minutes=1, now=now if day == today else d0)
        out.append(
            DayLoad(
                day=day,
                meeting_minutes=minutes,
                tasks_due=sum(1 for t in tasks if t.due_at and d0 <= t.due_at < d1),
                free_minutes=sum(s.minutes for s in free),
                conflicts=len(cal.find_conflicts(timed)),
            )
        )
    return out


def _insight(
    kind: str,
    severity: Severity,
    title: str,
    detail: str,
    items: list[dict[str, Any]],
    link: str,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "severity": severity,
        "title": title,
        "detail": detail,
        "link": link,
        "count": len(items),
        "items": items[:8],
    }


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


async def detect(db: AsyncSession, user: User, now: datetime | None = None) -> list[dict[str, Any]]:
    tz = user.timezone
    now = now or datetime.now(UTC)
    today = _local(now, tz).date()
    today_start, _ = day_bounds(today, tz)
    found: list[dict[str, Any]] = []

    # Overdue tasks.
    open_tasks = list(
        await db.scalars(
            select(Task)
            .where(
                Task.user_id == user.id,
                Task.status.in_(OPEN),
                Task.due_at.is_not(None),
                Task.due_at < now,
            )
            .order_by(Task.due_at)
        )
    )
    overdue = [t for t in open_tasks if is_overdue(t, now, today_start)]
    if overdue:
        found.append(
            _insight(
                "overdue",
                "high" if len(overdue) >= 5 else "medium",
                f"{_plural(len(overdue), 'task')} overdue",
                "Past their due date and still open.",
                [
                    {
                        "id": str(t.id),
                        "label": t.title,
                        "sub": f"due {_local(t.due_at, tz):%d %b}"
                        + (f", pushed back {t.postponed_count}x" if t.postponed_count else ""),
                        "link": "/tasks",
                    }
                    for t in overdue
                    if t.due_at
                ],
                "/tasks",
            )
        )

    # Email waiting for a reply.
    cutoff = now - timedelta(hours=REPLY_WAIT_HOURS)
    waiting = list(
        await db.scalars(
            select(EmailMessage)
            .where(
                EmailMessage.user_id == user.id,
                EmailMessage.needs_reply.is_(True),
                EmailMessage.replied_at.is_(None),
                EmailMessage.received_at < cutoff,
            )
            .order_by(EmailMessage.received_at)
            .limit(50)
        )
    )
    if waiting:
        high = sum(1 for m in waiting if m.priority == "high")
        found.append(
            _insight(
                "unanswered",
                "high" if high else "medium",
                f"{_plural(len(waiting), 'email')} waiting over 2 days for your reply",
                (f"{high} marked important. " if high else "")
                + "Marked as needing a reply and not answered yet.",
                [
                    {
                        "id": str(m.id),
                        "label": m.subject or "(no subject)",
                        "sub": f"{m.from_name or m.from_addr}, "
                        f"{(now - m.received_at).days} days ago"
                        + (", important" if m.priority == "high" else ""),
                        "link": "/emails",
                    }
                    for m in sorted(waiting, key=lambda m: (m.priority != "high", m.received_at))
                ],
                "/emails",
            )
        )

    # Calendar conflicts and overloaded days in the next week.
    loads = await day_loads(db, user, today, LOOKAHEAD_DAYS, now)
    w_start, _ = day_bounds(today, tz)
    w_end, _ = day_bounds(today + timedelta(days=LOOKAHEAD_DAYS), tz)
    events = [e for e in await cal.list_events(db, user.id, w_start, w_end) if _attending(e)]
    pairs = [(a, b) for a, b in cal.find_conflicts(events) if a.ends_at > now]
    if pairs:
        found.append(
            _insight(
                "conflicts",
                "high"
                if any(_local(a.starts_at, tz).date() == today for a, _ in pairs)
                else "medium",
                f"{_plural(len(pairs), 'calendar conflict')} this week",
                "Events that overlap. Declined events are ignored.",
                [
                    {
                        "id": f"{a.id}:{b.id}",
                        "label": f"{a.title} overlaps {b.title}",
                        "sub": _local(max(a.starts_at, b.starts_at), tz).strftime(
                            "%a %d %b, %H:%M"
                        ),
                        "link": "/calendar",
                    }
                    for a, b in pairs
                ],
                "/calendar",
            )
        )
    heavy = [d for d in loads if d.overloaded]
    if heavy:
        found.append(
            _insight(
                "overloaded",
                "high" if heavy[0].day == today else "medium",
                f"{_plural(len(heavy), 'overloaded day')} coming up",
                f"Six or more hours of meetings, {OVERLOAD_TASKS_DUE}+ tasks due, or "
                f"{OVERLOAD_TIGHT_TASKS}+ tasks due with under an hour free.",
                [
                    {
                        "id": d.day.isoformat(),
                        "label": "Today" if d.day == today else d.day.strftime("%A %d %b"),
                        "sub": ", ".join(d.reasons),
                        "link": "/calendar",
                    }
                    for d in heavy
                ],
                "/calendar",
            )
        )

    # Tasks that keep getting pushed back.
    pushed = list(
        await db.scalars(
            select(Task)
            .where(
                Task.user_id == user.id,
                Task.status.in_(OPEN),
                Task.postponed_count >= POSTPONED_MIN,
            )
            .order_by(Task.postponed_count.desc(), Task.created_at)
            .limit(30)
        )
    )
    if pushed:
        found.append(
            _insight(
                "postponed",
                "medium" if pushed[0].postponed_count >= 5 else "low",
                f"{_plural(len(pushed), 'task')} postponed {POSTPONED_MIN}+ times",
                "Worth breaking down, delegating or dropping.",
                [
                    {
                        "id": str(t.id),
                        "label": t.title,
                        "sub": f"pushed back {t.postponed_count} times",
                        "link": "/tasks",
                    }
                    for t in pushed
                ],
                "/tasks",
            )
        )

    rank = {"high": 0, "medium": 1, "low": 2}
    found.sort(key=lambda i: rank[i["severity"]])
    return found
