"""Security workspaces (findings and project boards) and learning tracks."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.ai.timeutil import now_local
from app.api.deps import DB, Auth
from app.api.routes.common import bad_request, not_found
from app.models import (
    LearningSession,
    LearningTopic,
    LearningTrack,
    Workspace,
    WorkspaceItem,
    WorkspaceItemEvent,
)
from app.services import audit, learning
from app.services import workspaces as ws_svc

router = APIRouter(tags=["workspaces"])
Severity = Literal["critical", "high", "medium", "low", "info"]
MAX_FILE = 10 * 1024 * 1024


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _today(auth: Auth) -> date:
    return now_local(auth.user.timezone).date()


# --- workspaces -----------------------------------------------------------------------------


class FieldDef(_In):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")
    label: str = Field(min_length=1, max_length=40)
    type: Literal["text", "number", "select", "date"] = "text"
    options: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(
        default_factory=list, max_length=20
    )


class WorkspaceIn(_In):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["vulns", "appsec", "cloud", "pentest", "custom"] = "custom"
    statuses: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(
        min_length=2, max_length=12
    )
    closed: list[str] = Field(min_length=1)
    fields: list[FieldDef] = Field(default_factory=list, max_length=12)
    sla_days: dict[Severity, Annotated[int, Field(ge=1, le=3650)]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent(self) -> WorkspaceIn:
        if len(set(self.statuses)) != len(self.statuses):
            raise ValueError("Status names must be different.")
        if not set(self.closed) <= set(self.statuses):
            raise ValueError("Closed statuses must be among the statuses.")
        if set(self.closed) == set(self.statuses):
            raise ValueError("At least one status must be open.")
        keys = [f.key for f in self.fields]
        if len(set(keys)) != len(keys):
            raise ValueError("Field keys must be different.")
        for f in self.fields:
            if f.type == "select" and not f.options:
                raise ValueError(f"{f.label} needs options.")
        return self


def ws_out(w: Workspace, counts: dict[uuid.UUID, tuple[int, int]] | None = None) -> dict[str, Any]:
    open_n, breached = (counts or {}).get(w.id, (0, 0))
    return {
        "id": str(w.id),
        "kind": w.kind,
        "name": w.name,
        "statuses": w.statuses,
        "closed": w.closed,
        "fields": w.fields,
        "sla_days": w.sla_days,
        "open": open_n,
        "breached": breached,
    }


@router.get("/workspaces")
async def list_workspaces(db: DB, auth: Auth) -> list[dict[str, Any]]:
    await ws_svc.ensure_defaults(db, auth.user.id)
    await db.commit()
    rows = list(
        await db.scalars(
            select(Workspace)
            .where(Workspace.user_id == auth.user.id)
            .order_by(Workspace.position, Workspace.created_at)
        )
    )
    today = _today(auth)
    counts: dict[uuid.UUID, tuple[int, int]] = {}
    for w in rows:
        items = await db.execute(
            select(WorkspaceItem.status, WorkspaceItem.due_on).where(
                WorkspaceItem.workspace_id == w.id
            )
        )
        open_items = [(s, d) for s, d in items.tuples() if s not in w.closed]
        counts[w.id] = (len(open_items), sum(1 for _, d in open_items if d and d < today))
    return [ws_out(w, counts) for w in rows]


@router.post("/workspaces", status_code=status.HTTP_201_CREATED)
async def create_workspace(body: WorkspaceIn, db: DB, auth: Auth) -> dict[str, Any]:
    pos = await db.scalar(
        select(func.coalesce(func.max(Workspace.position), 0)).where(
            Workspace.user_id == auth.user.id
        )
    )
    w = Workspace(user_id=auth.user.id, position=(pos or 0) + 1, **_ws_values(body))
    db.add(w)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        bad_request("You already have a workspace with that name.")
    return ws_out(w)


def _ws_values(body: WorkspaceIn) -> dict[str, Any]:
    v = body.model_dump()
    v["fields"] = [f.model_dump() for f in body.fields]
    return v


async def _ws(db: DB, auth: Auth, wid: uuid.UUID) -> Workspace:
    try:
        return await ws_svc.owned_workspace(db, auth.user.id, wid)
    except LookupError:
        not_found("Workspace not found.")


@router.put("/workspaces/{wid}")
async def update_workspace(wid: uuid.UUID, body: WorkspaceIn, db: DB, auth: Auth) -> dict[str, Any]:
    w = await _ws(db, auth, wid)
    in_use = set(
        await db.scalars(select(WorkspaceItem.status).where(WorkspaceItem.workspace_id == w.id))
    )
    missing = in_use - set(body.statuses)
    if missing:
        bad_request(f"Move the items out of {', '.join(sorted(missing))} before removing it.")
    for k, v in _ws_values(body).items():
        setattr(w, k, v)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        bad_request("You already have a workspace with that name.")
    return ws_out(w)


@router.delete("/workspaces/{wid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(wid: uuid.UUID, db: DB, auth: Auth) -> None:
    w = await _ws(db, auth, wid)
    audit.record(db, "workspace.deleted", user_id=auth.user.id, name=w.name)
    await db.delete(w)
    await db.commit()


@router.get("/workspaces/{wid}/summary")
async def workspace_summary(wid: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    w = await _ws(db, auth, wid)
    items = list(await db.scalars(select(WorkspaceItem).where(WorkspaceItem.workspace_id == w.id)))
    return ws_svc.summary(w, items, _today(auth))


# --- items ----------------------------------------------------------------------------------


class ItemIn(_In):
    title: str = Field(min_length=1, max_length=300)
    status: str | None = None
    severity: Severity = "medium"
    source: str = Field("manual", max_length=30)
    asset: str | None = Field(None, max_length=300)
    identifier: str | None = Field(None, max_length=120)
    owner: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=8000)
    found_on: date | None = None
    due_on: date | None = None
    follow_up_on: date | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ItemPatch(_In):
    title: str | None = Field(None, min_length=1, max_length=300)
    status: str | None = None
    severity: Severity | None = None
    asset: str | None = Field(None, max_length=300)
    identifier: str | None = Field(None, max_length=120)
    owner: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=8000)
    due_on: date | None = None
    follow_up_on: date | None = None
    data: dict[str, Any] | None = None
    note: str | None = Field(None, max_length=2000)


@router.get("/workspaces/{wid}/items")
async def list_items(
    wid: uuid.UUID,
    db: DB,
    auth: Auth,
    state: Literal["open", "closed", "all"] = "open",
    severity: Severity | None = None,
    source: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sla: Literal["breached", "due_soon"] | None = None,
) -> list[dict[str, Any]]:
    w = await _ws(db, auth, wid)
    stmt = select(WorkspaceItem).where(WorkspaceItem.workspace_id == w.id)
    if state == "open":
        stmt = stmt.where(WorkspaceItem.status.not_in(w.closed))
    elif state == "closed":
        stmt = stmt.where(WorkspaceItem.status.in_(w.closed))
    if severity:
        stmt = stmt.where(WorkspaceItem.severity == severity)
    if source:
        stmt = stmt.where(WorkspaceItem.source == source)
    if q:
        like = f"%{q.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(
            or_(
                WorkspaceItem.title.ilike(like),
                WorkspaceItem.asset.ilike(like),
                WorkspaceItem.identifier.ilike(like),
                WorkspaceItem.owner.ilike(like),
            )
        )
    today = _today(auth)
    rank = {s: i for i, s in enumerate(("critical", "high", "medium", "low", "info"))}
    out = [ws_svc.item_out(w, it, today) for it in await db.scalars(stmt.limit(2000))]
    if sla == "breached":
        out = [o for o in out if o["breached"]]
    elif sla == "due_soon":
        out = [o for o in out if o["days_left"] is not None and 0 <= o["days_left"] <= 7]
    return sorted(
        out,
        key=lambda o: (
            o["closed"],
            o["days_left"] is None,
            o["days_left"] or 0,
            rank[o["severity"]],
        ),
    )


@router.post("/workspaces/{wid}/items", status_code=status.HTTP_201_CREATED)
async def create_item(wid: uuid.UUID, body: ItemIn, db: DB, auth: Auth) -> dict[str, Any]:
    w = await _ws(db, auth, wid)
    today = _today(auth)
    found = body.found_on or today
    if found > today:
        bad_request("The found date can't be in the future.")
    try:
        data = ws_svc.check_fields(w, body.data)
        status_ = body.status or w.statuses[0]
        if status_ not in w.statuses:
            raise ValueError(f"Status must be one of: {', '.join(w.statuses)}.")
    except ValueError as exc:
        bad_request(str(exc))
    it = WorkspaceItem(
        user_id=auth.user.id,
        workspace_id=w.id,
        **body.model_dump(exclude={"status", "found_on", "due_on", "data"}),
        status=status_,
        found_on=found,
        due_on=body.due_on or ws_svc.due_for(w, body.severity, found),
        closed_on=today if status_ in w.closed else None,
        data=data,
    )
    db.add(it)
    await db.flush()
    db.add(ws_svc.event(it, "created", f"Added as {status_}"))
    await db.commit()
    return ws_svc.item_out(w, it, today)


async def _item(db: DB, auth: Auth, iid: uuid.UUID) -> tuple[Workspace, WorkspaceItem]:
    try:
        it = await ws_svc.owned_item(db, auth.user.id, iid)
    except LookupError:
        not_found("Item not found.")
    return await _ws(db, auth, it.workspace_id), it


@router.get("/workspace-items/{iid}")
async def get_item(iid: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    w, it = await _item(db, auth, iid)
    events = await db.scalars(
        select(WorkspaceItemEvent)
        .where(WorkspaceItemEvent.item_id == it.id)
        .order_by(WorkspaceItemEvent.created_at.desc())
    )
    return {
        **ws_svc.item_out(w, it, _today(auth)),
        "events": [
            {"kind": e.kind, "text": e.text, "at": e.created_at.isoformat()} for e in events
        ],
    }


@router.patch("/workspace-items/{iid}")
async def update_item(iid: uuid.UUID, body: ItemPatch, db: DB, auth: Auth) -> dict[str, Any]:
    w, it = await _item(db, auth, iid)
    today = _today(auth)
    changes = body.model_dump(exclude_unset=True)
    try:
        new_status = changes.pop("status", None)
        if new_status is not None:
            was_closed = it.status in w.closed
            line = ws_svc.set_status(w, it, new_status, today)
            if line:
                reopened = was_closed and it.status not in w.closed
                db.add(ws_svc.event(it, "reopened" if reopened else "status", line))
        if "data" in changes and changes["data"] is not None:
            it.data = ws_svc.check_fields(w, {**it.data, **changes.pop("data")})
        changes.pop("data", None)
    except ValueError as exc:
        bad_request(str(exc))
    note = changes.pop("note", None)
    if "severity" in changes and changes["severity"] and changes["severity"] != it.severity:
        db.add(ws_svc.event(it, "status", f"Severity {it.severity} → {changes['severity']}"))
        if "due_on" not in changes:
            changes["due_on"] = ws_svc.due_for(w, changes["severity"], it.found_on) or it.due_on
    if changes.get("follow_up_on"):
        db.add(ws_svc.event(it, "follow_up", f"Follow up on {changes['follow_up_on']:%d %b %Y}"))
    for k, v in changes.items():
        if k == "title" and v is None:
            continue
        setattr(it, k, v)
    if note:
        db.add(ws_svc.event(it, "comment", note))
    await db.commit()
    await db.refresh(it)
    return ws_svc.item_out(w, it, today)


class EscalateIn(_In):
    to: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=1, max_length=2000)
    follow_up_on: date | None = None


@router.post("/workspace-items/{iid}/escalate")
async def escalate(iid: uuid.UUID, body: EscalateIn, db: DB, auth: Auth) -> dict[str, Any]:
    """Records an escalation. NEXUS doesn't email anyone; draft that from Emails if needed."""
    w, it = await _item(db, auth, iid)
    if it.status in w.closed:
        bad_request("This item is closed.")
    it.escalated_at, it.escalated_to = datetime.now(UTC), body.to
    if body.follow_up_on:
        it.follow_up_on = body.follow_up_on
    db.add(ws_svc.event(it, "escalated", f"To {body.to}: {body.note}"))
    await db.commit()
    return ws_svc.item_out(w, it, _today(auth))


@router.delete("/workspace-items/{iid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(iid: uuid.UUID, db: DB, auth: Auth) -> None:
    _, it = await _item(db, auth, iid)
    await db.delete(it)
    await db.commit()


@router.post("/workspaces/{wid}/import")
async def import_findings(
    wid: uuid.UUID,
    db: DB,
    auth: Auth,
    file: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
    dry_run: Annotated[bool, Form()] = False,
) -> dict[str, Any]:
    w = await _ws(db, auth, wid)
    raw = await file.read(MAX_FILE + 1)
    if len(raw) > MAX_FILE:
        bad_request("That file is over 10 MB.")
    today = _today(auth)
    try:
        parsed = ws_svc.parse_import(raw, source, today)
    except ValueError as exc:
        bad_request(str(exc))
    if dry_run:
        return {
            "rows": len(parsed.rows),
            "open": sum(1 for r in parsed.rows if not r["fixed"]),
            "by_severity": {
                s: sum(1 for r in parsed.rows if r["severity"] == s and not r["fixed"])
                for s in ("critical", "high", "medium", "low", "info")
            },
            "sample": [
                {
                    k: (v.isoformat() if isinstance(v, date) else v)
                    for k, v in r.items()
                    if k != "description"
                }
                for r in parsed.rows[:20]
            ],
            "errors": parsed.errors[:20],
        }
    result = await ws_svc.import_rows(db, w, parsed, today)
    audit.record(
        db, "workspace.import", user_id=auth.user.id, workspace=w.name, source=source, counts=result
    )
    await db.commit()
    return {**result, "errors": parsed.errors[:20]}


# --- learning -------------------------------------------------------------------------------


class TrackIn(_In):
    name: str = Field(min_length=1, max_length=80)
    goal: str | None = Field(None, max_length=300)
    target_date: date | None = None
    template: Literal["oscp"] | None = None


@router.get("/learning/tracks")
async def list_tracks(db: DB, auth: Auth) -> list[dict[str, Any]]:
    rows = await db.scalars(
        select(LearningTrack)
        .where(LearningTrack.user_id == auth.user.id)
        .order_by(LearningTrack.created_at)
    )
    return [{"id": str(t.id), "name": t.name} for t in rows]


@router.post("/learning/tracks", status_code=status.HTTP_201_CREATED)
async def create_track(body: TrackIn, db: DB, auth: Auth) -> dict[str, Any]:
    try:
        t = await learning.create_track(
            db,
            auth.user.id,
            body.name.strip(),
            template=body.template,
            goal=body.goal,
            target_date=body.target_date,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        bad_request("You already have a track with that name.")
    return await learning.track_detail(db, t, _today(auth))


async def _track(db: DB, auth: Auth, tid: uuid.UUID) -> LearningTrack:
    try:
        return await learning.owned_track(db, auth.user.id, tid)
    except LookupError:
        not_found("Track not found.")


@router.get("/learning/tracks/{tid}")
async def get_track(tid: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    return await learning.track_detail(db, await _track(db, auth, tid), _today(auth))


@router.patch("/learning/tracks/{tid}")
async def update_track(tid: uuid.UUID, body: TrackIn, db: DB, auth: Auth) -> dict[str, Any]:
    t = await _track(db, auth, tid)
    t.name, t.goal, t.target_date = body.name.strip(), body.goal, body.target_date
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        bad_request("You already have a track with that name.")
    return await learning.track_detail(db, t, _today(auth))


@router.delete("/learning/tracks/{tid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_track(tid: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _track(db, auth, tid))
    await db.commit()


class TopicIn(_In):
    title: str = Field(min_length=1, max_length=160)
    section: str = Field("", max_length=80)


class TopicPatch(_In):
    title: str | None = Field(None, min_length=1, max_length=160)
    status: Literal["todo", "learning", "done"] | None = None
    notes: str | None = Field(None, max_length=20000)


@router.post("/learning/tracks/{tid}/topics", status_code=status.HTTP_201_CREATED)
async def add_topic(tid: uuid.UUID, body: TopicIn, db: DB, auth: Auth) -> dict[str, Any]:
    t = await _track(db, auth, tid)
    pos = await db.scalar(
        select(func.coalesce(func.max(LearningTopic.position), -1)).where(
            LearningTopic.track_id == t.id
        )
    )
    topic = LearningTopic(
        track_id=t.id, title=body.title, section=body.section, position=(pos or 0) + 1
    )
    db.add(topic)
    await db.commit()
    return learning.topic_out(topic, _today(auth))


async def _topic(db: DB, auth: Auth, tid: uuid.UUID) -> LearningTopic:
    try:
        return await learning.owned_topic(db, auth.user.id, tid)
    except LookupError:
        not_found("Topic not found.")


@router.patch("/learning/topics/{tid}")
async def update_topic(tid: uuid.UUID, body: TopicPatch, db: DB, auth: Auth) -> dict[str, Any]:
    topic = await _topic(db, auth, tid)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None or k == "notes":
            setattr(topic, k, v)
    today = _today(auth)
    if body.status == "learning" and topic.next_review_on is None:
        topic.next_review_on = today + timedelta(days=1)
    await db.commit()
    return learning.topic_out(topic, today)


class ReviewIn(_In):
    confidence: int = Field(ge=0, le=5)


@router.post("/learning/topics/{tid}/review")
async def review_topic(tid: uuid.UUID, body: ReviewIn, db: DB, auth: Auth) -> dict[str, Any]:
    topic = await _topic(db, auth, tid)
    today = _today(auth)
    learning.review(topic, body.confidence, today)
    await db.commit()
    return learning.topic_out(topic, today)


@router.delete("/learning/topics/{tid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(tid: uuid.UUID, db: DB, auth: Auth) -> None:
    await db.delete(await _topic(db, auth, tid))
    await db.commit()


class SessionIn(_In):
    day: date
    kind: Literal["study", "lab", "review", "exam"] = "study"
    minutes: int = Field(ge=1, le=1440)
    topic_id: uuid.UUID | None = None
    machine: str | None = Field(None, max_length=120)
    outcome: Literal["user", "root", "stuck", "partial"] | None = None
    notes: str | None = Field(None, max_length=20000)


@router.post("/learning/tracks/{tid}/sessions", status_code=status.HTTP_201_CREATED)
async def add_session(tid: uuid.UUID, body: SessionIn, db: DB, auth: Auth) -> dict[str, Any]:
    t = await _track(db, auth, tid)
    if body.day > _today(auth):
        bad_request("You can't log a session in the future.")
    if body.topic_id:
        topic = await _topic(db, auth, body.topic_id)
        if topic.track_id != t.id:
            bad_request("That topic is in another track.")
    s = LearningSession(track_id=t.id, **body.model_dump())
    db.add(s)
    await db.commit()
    return learning.session_out(s, {})


@router.delete("/learning/sessions/{sid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(sid: uuid.UUID, db: DB, auth: Auth) -> None:
    s = await db.get(LearningSession, sid)
    if s is None:
        not_found("Session not found.")
    await _track(db, auth, s.track_id)
    await db.delete(s)
    await db.commit()
