"""Personal life: goals, routines, lists, journal and important dates."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.ai.timeutil import now_local
from app.api.deps import DB, Auth
from app.api.routes.common import bad_request, not_found
from app.models import (
    Goal,
    ImportantDate,
    JournalEntry,
    ListItem,
    PersonalList,
    Routine,
)
from app.services import personal

router = APIRouter(tags=["personal"])
Area = Literal["personal", "career", "health", "money", "learning", "relationships"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _today(auth: Auth) -> date:
    return now_local(auth.user.timezone).date()


async def _owned(db: DB, auth: Auth, model: Any, oid: uuid.UUID, what: str) -> Any:
    row = await db.get(model, oid)
    if row is None or row.user_id != auth.user.id:
        not_found(f"{what} not found.")
    return row


# --- goals ---------------------------------------------------------------------------------


class Milestone(_In):
    title: str = Field(min_length=1, max_length=160)
    done: bool = False


class GoalIn(_In):
    title: str = Field(min_length=1, max_length=160)
    area: Area = "personal"
    why: str | None = Field(None, max_length=2000)
    target_date: date | None = None
    status: Literal["active", "done", "dropped"] = "active"
    progress: int = Field(0, ge=0, le=100)
    milestones: list[Milestone] = Field(default_factory=list, max_length=30)


@router.get("/goals")
async def list_goals(db: DB, auth: Auth) -> list[dict[str, Any]]:
    rows = await db.scalars(
        select(Goal).where(Goal.user_id == auth.user.id).order_by(Goal.status, Goal.created_at)
    )
    today = _today(auth)
    return [personal.goal_out(g, today) for g in rows]


@router.post("/goals", status_code=status.HTTP_201_CREATED)
async def create_goal(body: GoalIn, db: DB, auth: Auth) -> dict[str, Any]:
    g = Goal(user_id=auth.user.id, **body.model_dump())
    db.add(g)
    await db.commit()
    return personal.goal_out(g, _today(auth))


@router.put("/goals/{gid}")
async def update_goal(gid: uuid.UUID, body: GoalIn, db: DB, auth: Auth) -> dict[str, Any]:
    g = await _owned(db, auth, Goal, gid, "Goal")
    for k, v in body.model_dump().items():
        setattr(g, k, v)
    await db.commit()
    return personal.goal_out(g, _today(auth))


@router.delete("/goals/{gid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(gid: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _owned(db, auth, Goal, gid, "Goal"))
    await db.commit()


# --- routines ------------------------------------------------------------------------------


class RoutineIn(_In):
    name: str = Field(min_length=1, max_length=80)
    time_of_day: Literal["morning", "afternoon", "evening", "any"] = "any"
    steps: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(
        min_length=1, max_length=30
    )
    weekdays: list[Annotated[int, Field(ge=0, le=6)]] = Field(default_factory=list, max_length=7)
    active: bool = True


@router.get("/routines")
async def list_routines(
    db: DB, auth: Auth, day: date | None = None, days: Annotated[int, Query(ge=1, le=60)] = 14
) -> dict[str, Any]:
    d = day or _today(auth)
    rows = list(
        await db.scalars(
            select(Routine).where(Routine.user_id == auth.user.id).order_by(Routine.created_at)
        )
    )
    start = d - timedelta(days=days - 1)
    logs = await personal.routine_logs(db, [r.id for r in rows], start, d)
    out = []
    for r in rows:
        due_days = [start + timedelta(days=i) for i in range(days)]
        due_days = [x for x in due_days if personal.routine_due(r, x)]
        full = sum(1 for x in due_days if len(logs.get((r.id, x), [])) == len(r.steps))
        out.append(
            {
                "id": str(r.id),
                "name": r.name,
                "time_of_day": r.time_of_day,
                "steps": r.steps,
                "weekdays": r.weekdays,
                "active": r.active,
                "due_today": personal.routine_due(r, d),
                "done_steps": logs.get((r.id, d), []),
                "completed_days": full,
                "due_days": len(due_days),
            }
        )
    return {"day": d.isoformat(), "routines": out}


@router.post("/routines", status_code=status.HTTP_201_CREATED)
async def create_routine(body: RoutineIn, db: DB, auth: Auth) -> dict[str, str]:
    r = Routine(
        user_id=auth.user.id, **{**body.model_dump(), "weekdays": sorted(set(body.weekdays))}
    )
    db.add(r)
    await db.commit()
    return {"id": str(r.id)}


@router.put("/routines/{rid}")
async def update_routine(rid: uuid.UUID, body: RoutineIn, db: DB, auth: Auth) -> dict[str, str]:
    r = await _owned(db, auth, Routine, rid, "Routine")
    for k, v in body.model_dump().items():
        setattr(r, k, sorted(set(v)) if k == "weekdays" else v)
    await db.commit()
    return {"id": str(r.id)}


@router.delete("/routines/{rid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routine(rid: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _owned(db, auth, Routine, rid, "Routine"))
    await db.commit()


class StepsIn(_In):
    day: date
    done_steps: list[int] = Field(max_length=30)


@router.put("/routines/{rid}/log")
async def log_routine(rid: uuid.UUID, body: StepsIn, db: DB, auth: Auth) -> dict[str, Any]:
    if body.day > _today(auth):
        bad_request("You can't tick a future day.")
    r = await _owned(db, auth, Routine, rid, "Routine")
    done = await personal.set_steps(db, r, body.day, body.done_steps)
    await db.commit()
    return {"day": body.day.isoformat(), "done_steps": done}


# --- lists -----------------------------------------------------------------------------------


class ListIn(_In):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["checklist", "shopping", "reading", "travel", "ideas"] = "checklist"
    archived: bool = False


class ItemIn(_In):
    text: str = Field(min_length=1, max_length=300)
    note: str | None = Field(None, max_length=500)


class ItemPatch(_In):
    text: str | None = Field(None, min_length=1, max_length=300)
    note: str | None = Field(None, max_length=500)
    done: bool | None = None
    position: int | None = Field(None, ge=0, le=100000)


def item_out(i: ListItem) -> dict[str, Any]:
    return {"id": str(i.id), "text": i.text, "note": i.note, "done": i.done, "position": i.position}


@router.get("/lists")
async def list_lists(db: DB, auth: Auth) -> list[dict[str, Any]]:
    lists = list(
        await db.scalars(
            select(PersonalList)
            .where(PersonalList.user_id == auth.user.id)
            .order_by(PersonalList.archived, PersonalList.created_at)
        )
    )
    items: dict[uuid.UUID, list[ListItem]] = {x.id: [] for x in lists}
    if lists:
        for i in await db.scalars(
            select(ListItem)
            .where(ListItem.list_id.in_(items))
            .order_by(ListItem.done, ListItem.position, ListItem.created_at)
        ):
            items[i.list_id].append(i)
    return [
        {
            "id": str(x.id),
            "name": x.name,
            "kind": x.kind,
            "archived": x.archived,
            "items": [item_out(i) for i in items[x.id]],
        }
        for x in lists
    ]


@router.post("/lists", status_code=status.HTTP_201_CREATED)
async def create_list(body: ListIn, db: DB, auth: Auth) -> dict[str, str]:
    x = PersonalList(user_id=auth.user.id, **body.model_dump())
    db.add(x)
    await db.commit()
    return {"id": str(x.id)}


@router.put("/lists/{lid}")
async def update_list(lid: uuid.UUID, body: ListIn, db: DB, auth: Auth) -> dict[str, str]:
    x = await _owned(db, auth, PersonalList, lid, "List")
    for k, v in body.model_dump().items():
        setattr(x, k, v)
    await db.commit()
    return {"id": str(x.id)}


@router.delete("/lists/{lid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_list(lid: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _owned(db, auth, PersonalList, lid, "List"))
    await db.commit()


@router.post("/lists/{lid}/items", status_code=status.HTTP_201_CREATED)
async def add_item(lid: uuid.UUID, body: ItemIn, db: DB, auth: Auth) -> dict[str, Any]:
    x = await _owned(db, auth, PersonalList, lid, "List")
    count = await db.scalar(select(func.count()).where(ListItem.list_id == x.id))
    if (count or 0) >= 1000:
        bad_request("A list can hold 1,000 items.")
    pos = await db.scalar(
        select(func.coalesce(func.max(ListItem.position), -1)).where(ListItem.list_id == x.id)
    )
    i = ListItem(list_id=x.id, text=body.text, note=body.note, position=(pos or 0) + 1)
    db.add(i)
    await db.commit()
    return item_out(i)


async def _item(db: DB, auth: Auth, iid: uuid.UUID) -> ListItem:
    i = await db.get(ListItem, iid)
    if i is None:
        not_found("Item not found.")
    await _owned(db, auth, PersonalList, i.list_id, "Item")
    return i


@router.patch("/list-items/{iid}")
async def update_item(iid: uuid.UUID, body: ItemPatch, db: DB, auth: Auth) -> dict[str, Any]:
    i = await _item(db, auth, iid)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None or k == "note":
            setattr(i, k, v)
    await db.commit()
    return item_out(i)


@router.delete("/list-items/{iid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(iid: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _item(db, auth, iid))
    await db.commit()


# --- journal ---------------------------------------------------------------------------------


class JournalIn(_In):
    day: date
    mood: int | None = Field(None, ge=1, le=5)
    content: str = Field(min_length=1, max_length=50000)
    tags: list[Annotated[str, Field(min_length=1, max_length=30)]] = Field(
        default_factory=list, max_length=10
    )


def entry_out(e: JournalEntry) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "day": e.day.isoformat(),
        "mood": e.mood,
        "content": e.content,
        "tags": e.tags,
        "created_at": e.created_at.isoformat(),
    }


@router.get("/journal")
async def list_journal(
    db: DB,
    auth: Auth,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    tag: Annotated[str | None, Query(max_length=30)] = None,
) -> dict[str, Any]:
    today = _today(auth)
    m = month or today.strftime("%Y-%m")
    y, mo = (int(x) for x in m.split("-"))
    if not 1 <= mo <= 12:
        bad_request("Month must be YYYY-MM.")
    start = date(y, mo, 1)
    end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    rows = list(
        await db.scalars(
            select(JournalEntry)
            .where(
                JournalEntry.user_id == auth.user.id,
                JournalEntry.day >= start,
                JournalEntry.day <= end,
            )
            .order_by(JournalEntry.day.desc(), JournalEntry.created_at.desc())
        )
    )
    if q:  # text is encrypted, so search after decrypting
        rows = [e for e in rows if q.lower() in e.content.lower()]
    if tag:
        rows = [e for e in rows if tag in e.tags]
    moods = [e.mood for e in rows if e.mood]
    return {
        "month": m,
        "entries": [entry_out(e) for e in rows],
        "days_written": len({e.day for e in rows}),
        "average_mood": round(sum(moods) / len(moods), 1) if moods else None,
    }


@router.post("/journal", status_code=status.HTTP_201_CREATED)
async def add_entry(body: JournalIn, db: DB, auth: Auth) -> dict[str, Any]:
    if body.day > _today(auth):
        bad_request("You can't write an entry for a future day.")
    e = JournalEntry(user_id=auth.user.id, **body.model_dump())
    db.add(e)
    await db.commit()
    return entry_out(e)


@router.put("/journal/{eid}")
async def update_entry(eid: uuid.UUID, body: JournalIn, db: DB, auth: Auth) -> dict[str, Any]:
    e = await _owned(db, auth, JournalEntry, eid, "Entry")
    for k, v in body.model_dump().items():
        setattr(e, k, v)
    await db.commit()
    return entry_out(e)


@router.delete("/journal/{eid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(eid: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _owned(db, auth, JournalEntry, eid, "Entry"))
    await db.commit()


# --- important dates -------------------------------------------------------------------------


class DateIn(_In):
    title: str = Field(min_length=1, max_length=120)
    kind: Literal["birthday", "anniversary", "renewal", "deadline", "other"] = "birthday"
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    year: int | None = Field(None, ge=1900, le=2200)
    yearly: bool = True
    remind_days: int = Field(3, ge=0, le=60)
    notes: str | None = Field(None, max_length=500)


@router.get("/important-dates")
async def list_dates(db: DB, auth: Auth) -> list[dict[str, Any]]:
    today = _today(auth)
    rows = await db.scalars(select(ImportantDate).where(ImportantDate.user_id == auth.user.id))
    out = [personal.date_out(d, today) for d in rows]
    return sorted(out, key=lambda d: (d["days_left"] is None, d["days_left"] or 0))


@router.post("/important-dates", status_code=status.HTTP_201_CREATED)
async def create_date(body: DateIn, db: DB, auth: Auth) -> dict[str, Any]:
    try:
        personal.check_date(body.month, body.day, body.year, body.yearly)
    except ValueError as exc:
        bad_request(str(exc))
    d = ImportantDate(user_id=auth.user.id, **body.model_dump())
    db.add(d)
    await db.commit()
    return personal.date_out(d, _today(auth))


@router.put("/important-dates/{did}")
async def update_date(did: uuid.UUID, body: DateIn, db: DB, auth: Auth) -> dict[str, Any]:
    d = await _owned(db, auth, ImportantDate, did, "Date")
    try:
        personal.check_date(body.month, body.day, body.year, body.yearly)
    except ValueError as exc:
        bad_request(str(exc))
    for k, v in body.model_dump().items():
        setattr(d, k, v)
    d.last_reminded_on = None
    await db.commit()
    return personal.date_out(d, _today(auth))


@router.delete("/important-dates/{did}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_date(did: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _owned(db, auth, ImportantDate, did, "Date"))
    await db.commit()
