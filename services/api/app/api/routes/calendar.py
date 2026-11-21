"""Calendar: events in a range, create/edit/delete, conflicts, free slots, time blocks."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DB, Auth
from app.api.routes.common import bad_request, not_found
from app.models import CalendarEvent
from app.services import calendar as cal
from app.services import integrations as integ
from app.services import tasks as task_svc

router = APIRouter(prefix="/calendar", tags=["calendar"])
WORK_START, WORK_END = time(9), time(18)


def event_out(e: CalendarEvent) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "title": e.title,
        "description": e.description,
        "location": e.location,
        "starts_at": e.starts_at.isoformat(),
        "ends_at": e.ends_at.isoformat(),
        "all_day": e.all_day,
        "status": e.status,
        "attendees": e.attendees,
        "html_link": e.html_link,
        "source": e.source,
        "google": e.account_id is not None,
        "task_id": str(e.task_id) if e.task_id else None,
    }


@router.get("/events")
async def list_events(db: DB, auth: Auth, start: datetime, end: datetime) -> dict[str, Any]:
    if end <= start or end - start > timedelta(days=62):
        bad_request("Pick a range of up to 62 days.")
    events = await cal.list_events(db, auth.user.id, start, end)
    account = await integ.google_account(db, auth.user.id)
    return {
        "events": [event_out(e) for e in events],
        "conflicts": [[str(a.id), str(b.id)] for a, b in cal.find_conflicts(events)],
        "google_connected": account is not None,
        "last_sync_at": account.last_sync_at.isoformat()
        if account and account.last_sync_at
        else None,
    }


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(None, max_length=8000)
    location: str | None = Field(None, max_length=300)
    starts_at: datetime
    ends_at: datetime
    all_day: bool = False


class EventPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=8000)
    location: str | None = Field(None, max_length=300)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    all_day: bool | None = None


@router.post("/events", status_code=201)
async def create_event(body: EventIn, db: DB, auth: Auth) -> dict[str, Any]:
    try:
        ev = await cal.create_event(db, auth.user, **body.model_dump())
    except ValueError as exc:
        bad_request(str(exc))
    await db.commit()
    return event_out(ev)


async def _event(db: DB, auth: Auth, eid: uuid.UUID) -> CalendarEvent:
    try:
        return await cal.get_owned(db, auth.user.id, eid)
    except LookupError:
        not_found("Event not found.")


@router.patch("/events/{eid}")
async def update_event(eid: uuid.UUID, body: EventPatch, db: DB, auth: Auth) -> dict[str, Any]:
    ev = await _event(db, auth, eid)
    try:
        ev = await cal.update_event(db, auth.user, ev, **body.model_dump(exclude_unset=True))
    except ValueError as exc:
        bad_request(str(exc))
    await db.commit()
    return event_out(ev)


@router.delete("/events/{eid}", status_code=204)
async def delete_event(eid: uuid.UUID, db: DB, auth: Auth) -> None:
    ev = await _event(db, auth, eid)
    try:
        await cal.delete_event(db, auth.user, ev)
    except ValueError as exc:
        bad_request(str(exc))
    await db.commit()


@router.get("/free-slots")
async def free_slots(
    db: DB,
    auth: Auth,
    day: date,
    minutes: int = Query(30, ge=10, le=480),
    work_start: time = WORK_START,
    work_end: time = WORK_END,
) -> list[dict[str, Any]]:
    if work_end <= work_start:
        bad_request("Working hours must end after they start.")
    zone = ZoneInfo(auth.user.timezone)
    start = datetime.combine(day, time(0), zone).astimezone(UTC)
    events = await cal.list_events(db, auth.user.id, start, start + timedelta(days=1))
    slots = cal.free_slots(
        events, day, auth.user.timezone, minutes=minutes, work_start=work_start, work_end=work_end
    )
    return [
        {"start": s.start.isoformat(), "end": s.end.isoformat(), "minutes": s.minutes}
        for s in slots
    ]


class TimeBlockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: uuid.UUID
    starts_at: datetime
    minutes: int = Field(60, ge=15, le=480)


@router.post("/time-block", status_code=201)
async def time_block(body: TimeBlockIn, db: DB, auth: Auth) -> dict[str, Any]:
    try:
        task = await task_svc.get_owned_task(db, auth.user.id, body.task_id)
    except LookupError:
        not_found("Task not found.")
    try:
        ev = await cal.time_block(db, auth.user, task, body.starts_at, body.minutes)
    except ValueError as exc:
        bad_request(str(exc))
    await db.commit()
    return event_out(ev)
