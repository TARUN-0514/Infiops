"""Work log, weekly status reports, the morning briefing and notifications."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update

from app.ai.gateway import get_gateway
from app.api.deps import DB, Auth
from app.api.routes.common import bad_request, not_found
from app.models import Briefing, Notification, Project, PushSubscription, WorkLog
from app.services import briefing as svc
from app.services import notify

router = APIRouter(tags=["briefing"])


def _today(auth: Auth) -> date:
    return datetime.now(ZoneInfo(auth.user.timezone)).date()


def briefing_out(b: Briefing) -> dict[str, Any]:
    return {
        "id": str(b.id),
        "kind": b.kind,
        "for_date": b.for_date.isoformat(),
        "content": b.content,
        "data": b.data,
        "model": b.model,
        "written_by_model": b.model is not None,
        "created_at": b.created_at.isoformat(),
        "read_at": b.read_at.isoformat() if b.read_at else None,
    }


# --- work log -------------------------------------------------------------------


def log_out(e: WorkLog, projects: dict[uuid.UUID, str]) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "day": e.day.isoformat(),
        "content": e.content,
        "minutes": e.minutes,
        "project_id": str(e.project_id) if e.project_id else None,
        "project": projects.get(e.project_id) if e.project_id else None,
        "task_id": str(e.task_id) if e.task_id else None,
        "source": e.source,
        "created_at": e.created_at.isoformat(),
    }


async def _projects(db: DB, auth: Auth) -> dict[uuid.UUID, str]:
    rows = await db.scalars(select(Project).where(Project.user_id == auth.user.id))
    return {p.id: p.name for p in rows}


@router.get("/worklog")
async def list_worklog(
    db: DB, auth: Auth, start: date | None = None, end: date | None = None
) -> list[dict[str, Any]]:
    end = end or _today(auth)
    start = start or end - timedelta(days=13)
    if end < start or (end - start).days > 92:
        bad_request("Pick a range of up to 92 days.")
    rows = await db.scalars(
        select(WorkLog)
        .where(WorkLog.user_id == auth.user.id, WorkLog.day >= start, WorkLog.day <= end)
        .order_by(WorkLog.day.desc(), WorkLog.created_at.desc())
    )
    projects = await _projects(db, auth)
    return [log_out(e, projects) for e in rows]


class LogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=2, max_length=2000)
    day: date | None = None
    minutes: int | None = Field(None, ge=1, le=1440)
    project_id: uuid.UUID | None = None


class LogPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str | None = Field(None, min_length=2, max_length=2000)
    day: date | None = None
    minutes: int | None = Field(None, ge=1, le=1440)
    project_id: uuid.UUID | None = None


async def _check_project(db: DB, auth: Auth, pid: uuid.UUID | None) -> None:
    if pid is not None:
        p = await db.get(Project, pid)
        if p is None or p.user_id != auth.user.id:
            bad_request("Unknown project.")


@router.post("/worklog", status_code=201)
async def add_log(body: LogIn, db: DB, auth: Auth) -> dict[str, Any]:
    await _check_project(db, auth, body.project_id)
    e = WorkLog(
        user_id=auth.user.id,
        day=body.day or _today(auth),
        content=body.content.strip(),
        minutes=body.minutes,
        project_id=body.project_id,
    )
    db.add(e)
    await db.commit()
    return log_out(e, await _projects(db, auth))


async def _log(db: DB, auth: Auth, lid: uuid.UUID) -> WorkLog:
    e = await db.get(WorkLog, lid)
    if e is None or e.user_id != auth.user.id:
        not_found("Entry not found.")
    return e


@router.patch("/worklog/{lid}")
async def update_log(lid: uuid.UUID, body: LogPatch, db: DB, auth: Auth) -> dict[str, Any]:
    e = await _log(db, auth, lid)
    values = body.model_dump(exclude_unset=True)
    if "project_id" in values:
        await _check_project(db, auth, values["project_id"])
    for k, v in values.items():
        if k == "content" and v is None:
            continue
        setattr(e, k, v)
    await db.commit()
    return log_out(e, await _projects(db, auth))


@router.delete("/worklog/{lid}", status_code=204)
async def delete_log(lid: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _log(db, auth, lid))
    await db.commit()


@router.get("/reports")
async def list_reports(db: DB, auth: Auth) -> list[dict[str, Any]]:
    rows = await db.scalars(
        select(Briefing)
        .where(Briefing.user_id == auth.user.id, Briefing.kind == "weekly_status")
        .order_by(Briefing.for_date.desc())
        .limit(26)
    )
    return [briefing_out(b) for b in rows]


class ReportIn(BaseModel):
    week_of: date | None = None
    cloud: bool = False


@router.post("/reports", status_code=201)
async def make_report(body: ReportIn, db: DB, auth: Auth) -> dict[str, Any]:
    start = body.week_of or svc.week_start(_today(auth))
    report = await svc.weekly_report(db, get_gateway(), auth.user, start, cloud=body.cloud)
    await db.commit()
    return briefing_out(report)


# --- morning briefing ------------------------------------------------------------


@router.get("/briefings/today")
async def today(db: DB, auth: Auth) -> dict[str, Any]:
    day = _today(auth)
    b = await db.scalar(
        select(Briefing).where(
            Briefing.user_id == auth.user.id, Briefing.kind == "morning", Briefing.for_date == day
        )
    )
    return {
        "date": day.isoformat(),
        "briefing": briefing_out(b) if b else None,
        "settings": await svc.settings_for(db, auth.user.id),
    }


class GenerateIn(BaseModel):
    regenerate: bool = False


@router.post("/briefings/today")
async def generate_today(body: GenerateIn, db: DB, auth: Auth) -> dict[str, Any]:
    b = await svc.morning(db, get_gateway(), auth.user, _today(auth), regenerate=body.regenerate)
    await db.commit()
    return briefing_out(b)


@router.get("/briefings")
async def history(
    db: DB, auth: Auth, kind: str = Query("morning", pattern="^(morning|midday|evening)$")
) -> list[dict[str, Any]]:
    rows = await db.scalars(
        select(Briefing)
        .where(Briefing.user_id == auth.user.id, Briefing.kind == kind)
        .order_by(Briefing.for_date.desc())
        .limit(30)
    )
    return [briefing_out(b) for b in rows]


@router.post("/briefings/{bid}/read")
async def mark_read(bid: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    b = await db.get(Briefing, bid)
    if b is None or b.user_id != auth.user.id:
        not_found("Briefing not found.")
    b.read_at = b.read_at or datetime.now(UTC)
    await db.commit()
    return briefing_out(b)


HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class BriefingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    time: str | None = Field(None, pattern=HHMM)
    push: bool | None = None
    midday: bool | None = None
    midday_time: str | None = Field(None, pattern=HHMM)
    evening: bool | None = None
    evening_time: str | None = Field(None, pattern=HHMM)
    monthly: bool | None = None


@router.put("/briefings/settings")
async def save_settings(body: BriefingSettings, db: DB, auth: Auth) -> dict[str, Any]:
    out = await svc.save_settings(db, auth.user.id, body.model_dump(exclude_none=True))
    await db.commit()
    return out


# --- notifications ----------------------------------------------------------------


def notification_out(n: Notification) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "kind": n.kind,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "read": n.read_at is not None,
        "created_at": n.created_at.isoformat(),
    }


@router.get("/notifications")
async def list_notifications(db: DB, auth: Auth, unread: bool = Query(False)) -> dict[str, Any]:
    stmt = select(Notification).where(Notification.user_id == auth.user.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = list(await db.scalars(stmt.order_by(Notification.created_at.desc()).limit(50)))
    count = len(
        list(
            await db.scalars(
                select(Notification.id).where(
                    Notification.user_id == auth.user.id, Notification.read_at.is_(None)
                )
            )
        )
    )
    return {"items": [notification_out(n) for n in rows], "unread": count}


@router.post("/notifications/read-all")
async def read_all(db: DB, auth: Auth) -> dict[str, bool]:
    await db.execute(
        update(Notification)
        .where(Notification.user_id == auth.user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await db.commit()
    return {"ok": True}


@router.post("/notifications/{nid}/read")
async def read_one(nid: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    n = await db.get(Notification, nid)
    if n is None or n.user_id != auth.user.id:
        not_found("Notification not found.")
    n.read_at = n.read_at or datetime.now(UTC)
    await db.commit()
    return notification_out(n)


@router.get("/push/key")
async def push_key(auth: Auth) -> dict[str, str]:
    return {"public_key": notify.vapid_keys()[0]}


class SubIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000, pattern=r"^https://")
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=4, max_length=100)


@router.post("/push/subscriptions", status_code=201)
async def subscribe(body: SubIn, request: Request, db: DB, auth: Auth) -> dict[str, bool]:
    existing = await db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    if existing is not None:
        existing.user_id, existing.p256dh, existing.auth = auth.user.id, body.p256dh, body.auth
    else:
        db.add(
            PushSubscription(
                user_id=auth.user.id,
                endpoint=body.endpoint,
                p256dh=body.p256dh,
                auth=body.auth,
                user_agent=(request.headers.get("user-agent") or "")[:400],
            )
        )
    await db.commit()
    return {"ok": True}


class UnsubIn(BaseModel):
    endpoint: str = Field(max_length=2000)


@router.post("/push/unsubscribe")
async def unsubscribe(body: UnsubIn, db: DB, auth: Auth) -> dict[str, bool]:
    sub = await db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == auth.user.id
        )
    )
    if sub is not None:
        await db.delete(sub)
        await db.commit()
    return {"ok": True}


@router.post("/push/test")
async def push_test(db: DB, auth: Auth) -> dict[str, int]:
    n = await notify.notify(
        db,
        auth.user.id,
        kind="test",
        title="NEXUS notifications work",
        body="You'll get your morning briefing here.",
        link="/briefing",
    )
    await db.commit()
    subs = len(
        list(
            await db.scalars(
                select(PushSubscription.id).where(PushSubscription.user_id == auth.user.id)
            )
        )
    )
    return {"devices": subs, "delivered": int(n.pushed)}
