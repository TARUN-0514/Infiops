"""Calendar: Google sync, local events, conflicts, free slots and time blocking.
When Google is connected, events you create are written to your primary calendar."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.google import GoogleClient, GoogleError
from app.models import CalendarEvent, ConnectedAccount, Task, User
from app.services import audit
from app.services import integrations as integ

SYNC_PAST_DAYS = 30
SYNC_FUTURE_DAYS = 120
EVENT_FIELDS = {"title", "description", "location", "starts_at", "ends_at", "all_day"}


def _parse_when(when: dict[str, Any], tz: str) -> tuple[datetime, bool]:
    if "dateTime" in when:
        return datetime.fromisoformat(when["dateTime"].replace("Z", "+00:00")), False
    day = date.fromisoformat(when["date"])
    zone = ZoneInfo(when.get("timeZone") or tz)
    return datetime.combine(day, time(0), zone).astimezone(UTC), True


def google_fields(ev: dict[str, Any], tz: str) -> dict[str, Any]:
    start, all_day = _parse_when(ev.get("start", {}), tz)
    end, _ = _parse_when(ev.get("end", {}), tz) if ev.get("end") else (start, all_day)
    status = ev.get("status", "confirmed")
    return {
        "provider_id": ev["id"],
        "title": (ev.get("summary") or "(no title)")[:300],
        "description": ev.get("description"),
        "location": (ev.get("location") or None) and ev["location"][:300],
        "starts_at": start,
        "ends_at": max(end, start),
        "all_day": all_day,
        "status": status if status in ("confirmed", "tentative", "cancelled") else "confirmed",
        "attendees": [
            {
                "email": a.get("email", ""),
                "name": a.get("displayName"),
                "response": a.get("responseStatus"),
                "self": bool(a.get("self")),
            }
            for a in ev.get("attendees", [])
        ],
        "html_link": ev.get("htmlLink"),
        "source": "google",
    }


async def sync_calendar(
    db: AsyncSession, account: ConnectedAccount, gc: GoogleClient, tz: str
) -> int:
    log = integ.start_log(db, account, "calendar")
    now = datetime.now(UTC)
    t_min, t_max = now - timedelta(days=SYNC_PAST_DAYS), now + timedelta(days=SYNC_FUTURE_DAYS)
    changed = 0
    try:
        page: str | None = None
        items: list[dict[str, Any]] = []
        for _ in range(10):
            res = await gc.events_list(t_min, t_max, page)
            items += res.get("items", [])
            page = res.get("nextPageToken")
            if not page:
                break
        existing = {
            e.provider_id: e
            for e in await db.scalars(
                select(CalendarEvent).where(CalendarEvent.account_id == account.id)
            )
        }
        for raw in items:
            if "start" not in raw and raw.get("status") != "cancelled":
                continue
            current = existing.get(raw["id"])
            if raw.get("status") == "cancelled" and "start" not in raw:
                if current is not None and current.status != "cancelled":
                    current.status = "cancelled"
                    changed += 1
                continue
            fields = google_fields(raw, tz)
            if current is None:
                db.add(CalendarEvent(user_id=account.user_id, account_id=account.id, **fields))
                changed += 1
            else:
                diff = {k: v for k, v in fields.items() if getattr(current, k) != v}
                for k, v in diff.items():
                    setattr(current, k, v)
                if diff:
                    current.updated_at = now
                    changed += 1
    except GoogleError as exc:
        integ.finish_log(log, changed, str(exc))
        if exc.status == 401:
            account.status, account.last_error = "error", str(exc)
        raise
    account.last_sync_at = now
    integ.finish_log(log, changed)
    return changed


# --- reads ----------------------------------------------------------------------


async def list_events(
    db: AsyncSession, user_id: uuid.UUID, start: datetime, end: datetime
) -> list[CalendarEvent]:
    rows = await db.scalars(
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.status != "cancelled",
            CalendarEvent.starts_at < end,
            CalendarEvent.ends_at > start,
        )
        .order_by(CalendarEvent.starts_at)
    )
    return list(rows)


def find_conflicts(events: list[CalendarEvent]) -> list[tuple[CalendarEvent, CalendarEvent]]:
    """Timed events that overlap. All-day events and events you declined are ignored."""
    timed = sorted(
        (
            e
            for e in events
            if not e.all_day
            and not any(a.get("self") and a.get("response") == "declined" for a in e.attendees)
        ),
        key=lambda e: e.starts_at,
    )
    out = []
    for i, a in enumerate(timed):
        for b in timed[i + 1 :]:
            if b.starts_at >= a.ends_at:
                break
            out.append((a, b))
    return out


@dataclass
class Slot:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def free_slots(
    events: list[CalendarEvent],
    day: date,
    tz: str,
    *,
    minutes: int = 30,
    work_start: time = time(9),
    work_end: time = time(18),
    now: datetime | None = None,
) -> list[Slot]:
    zone = ZoneInfo(tz)
    start = datetime.combine(day, work_start, zone).astimezone(UTC)
    end = datetime.combine(day, work_end, zone).astimezone(UTC)
    now = now or datetime.now(UTC)
    if now > start:
        start = min(max(start, now), end)
    busy = sorted(
        (max(e.starts_at, start), min(e.ends_at, end))
        for e in events
        if not e.all_day and e.ends_at > start and e.starts_at < end
    )
    slots, cursor = [], start
    for b_start, b_end in busy:
        if b_start > cursor:
            slots.append(Slot(cursor, b_start))
        cursor = max(cursor, b_end)
    if end > cursor:
        slots.append(Slot(cursor, end))
    return [s for s in slots if s.minutes >= minutes]


# --- writes ---------------------------------------------------------------------


def _google_body(ev: CalendarEvent, tz: str) -> dict[str, Any]:
    if ev.all_day:
        zone = ZoneInfo(tz)
        s_day = ev.starts_at.astimezone(zone).date()
        e_day = max(ev.ends_at.astimezone(zone).date(), s_day + timedelta(days=1))
        when = {"start": {"date": s_day.isoformat()}, "end": {"date": e_day.isoformat()}}
    else:
        when = {
            "start": {"dateTime": ev.starts_at.isoformat(), "timeZone": tz},
            "end": {"dateTime": ev.ends_at.isoformat(), "timeZone": tz},
        }
    return {
        "summary": ev.title,
        "description": ev.description or "",
        "location": ev.location or "",
        **when,
    }


def _check_times(fields: dict[str, Any]) -> None:
    s, e = fields.get("starts_at"), fields.get("ends_at")
    if s is not None and e is not None and e <= s:
        raise ValueError("An event must end after it starts.")


async def get_owned(db: AsyncSession, user_id: uuid.UUID, event_id: uuid.UUID) -> CalendarEvent:
    ev = await db.get(CalendarEvent, event_id)
    if ev is None or ev.user_id != user_id:
        raise LookupError("Event not found.")
    return ev


async def create_event(
    db: AsyncSession,
    user: User,
    *,
    source: str = "local",
    task_id: uuid.UUID | None = None,
    **fields: Any,
) -> CalendarEvent:
    fields = {k: v for k, v in fields.items() if k in EVENT_FIELDS}
    _check_times(fields)
    ev = CalendarEvent(user_id=user.id, source=source, task_id=task_id, **fields)
    account = await integ.google_account(db, user.id)
    if account is not None:
        try:
            res = await integ.client(account).event_insert(_google_body(ev, user.timezone))
        except GoogleError as exc:
            raise ValueError(f"Google Calendar didn't accept the event: {exc}") from None
        ev.account_id, ev.provider_id = account.id, res.get("id")
        ev.html_link = res.get("htmlLink")
    db.add(ev)
    await db.flush()
    audit.record(db, "calendar.created", user_id=user.id, target=str(ev.id))
    return ev


async def update_event(
    db: AsyncSession, user: User, ev: CalendarEvent, **fields: Any
) -> CalendarEvent:
    fields = {k: v for k, v in fields.items() if k in EVENT_FIELDS}
    merged = {"starts_at": ev.starts_at, "ends_at": ev.ends_at, **fields}
    _check_times(merged)
    for k, v in fields.items():
        setattr(ev, k, v)
    ev.updated_at = datetime.now(UTC)
    if ev.account_id and ev.provider_id:
        account = await db.get(ConnectedAccount, ev.account_id)
        if account is None or account.status != "connected":
            raise ValueError("Reconnect Google to change this event.")
        try:
            await integ.client(account).event_patch(ev.provider_id, _google_body(ev, user.timezone))
        except GoogleError as exc:
            raise ValueError(f"Google Calendar didn't accept the change: {exc}") from None
    audit.record(db, "calendar.updated", user_id=user.id, target=str(ev.id))
    return ev


async def delete_event(db: AsyncSession, user: User, ev: CalendarEvent) -> None:
    if ev.account_id and ev.provider_id:
        account = await db.get(ConnectedAccount, ev.account_id)
        if account is None or account.status != "connected":
            raise ValueError("Reconnect Google to delete this event.")
        try:
            await integ.client(account).event_delete(ev.provider_id)
        except GoogleError as exc:
            if exc.status not in (404, 410):
                raise ValueError(f"Google Calendar didn't delete it: {exc}") from None
    audit.record(db, "calendar.deleted", user_id=user.id, target=str(ev.id))
    await db.delete(ev)


async def time_block(
    db: AsyncSession, user: User, task: Task, starts_at: datetime, minutes: int
) -> CalendarEvent:
    return await create_event(
        db,
        user,
        source="time_block",
        task_id=task.id,
        title=f"Focus: {task.title}"[:300],
        description="Time blocked by NEXUS for this task.",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=minutes),
        all_day=False,
    )
