from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo


def local_to_utc(day: str | None, at: str | None, tz: str) -> tuple[datetime | None, bool]:
    """Turn a local date ("2026-11-22") and optional time ("17:30") into UTC.
    Returns (due_at, all_day). A date without a time is all-day, stored at 09:00 local
    so reminders land in the morning."""
    if not day:
        return None, False
    d = date.fromisoformat(day)
    all_day = not at
    t = time.fromisoformat(at) if at else time(9, 0)
    local = datetime.combine(d, t, tzinfo=ZoneInfo(tz))
    return local.astimezone(UTC), all_day


def now_local(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))


def describe_now(tz: str, now: datetime | None = None) -> str:
    n = now.astimezone(ZoneInfo(tz)) if now else now_local(tz)
    return f"{n:%A %d %B %Y, %H:%M} ({tz}, UTC{n:%z})"
