"""Tasks and projects."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.ai.gateway import get_gateway
from app.ai.task_parser import parse_task
from app.ai.types import BudgetExceededError, ModelRefusalError, ModelUnavailableError
from app.api.deps import DB, Auth
from app.api.routes.common import bad_request, not_found
from app.models import Project, Task
from app.services import tasks as svc

router = APIRouter(tags=["tasks"])

Priority = Literal["none", "low", "medium", "high", "urgent"]
Status = Literal["todo", "in_progress", "done", "cancelled"]


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    notes: str | None
    status: str
    priority: str
    due_at: datetime | None
    all_day: bool
    recurrence: str | None
    project_id: uuid.UUID | None
    parent_task_id: uuid.UUID | None
    postponed_count: int
    position: int
    source: str
    completed_at: datetime | None
    created_at: datetime
    subtasks_total: int = 0
    subtasks_done: int = 0


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    notes: str | None = None
    status: Status = "todo"
    priority: Priority = "none"
    due_at: datetime | None = None
    all_day: bool = False
    recurrence: str | None = None
    project_id: uuid.UUID | None = None
    parent_task_id: uuid.UUID | None = None
    position: int = 0
    subtasks: list[str] = Field(default_factory=list, max_length=20)


class TaskPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, min_length=1, max_length=300)
    notes: str | None = None
    status: Status | None = None
    priority: Priority | None = None
    due_at: datetime | None = None
    all_day: bool | None = None
    recurrence: str | None = None
    project_id: uuid.UUID | None = None
    parent_task_id: uuid.UUID | None = None
    position: int | None = None


class ParseIn(BaseModel):
    text: str = Field(min_length=2, max_length=1000)
    cloud: bool = False


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None
    color: str
    status: str
    created_at: datetime
    open_tasks: int = 0
    done_tasks: int = 0


class ProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    color: str = Field("violet", max_length=16)


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = None
    color: str | None = Field(None, max_length=16)
    status: Literal["active", "archived"] | None = None


def _aware(dt: datetime | None, tz: str) -> datetime | None:
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=ZoneInfo(tz))


async def _out(db: DB, tasks: list[Task]) -> list[TaskOut]:
    counts = await svc.subtask_counts(db, [t.id for t in tasks])
    out = []
    for t in tasks:
        total, done = counts.get(t.id, (0, 0))
        out.append(
            TaskOut.model_validate(t).model_copy(
                update={"subtasks_total": total, "subtasks_done": done}
            )
        )
    return out


async def _owned(db: DB, auth: Auth, task_id: uuid.UUID) -> Task:
    try:
        return await svc.get_owned_task(db, auth.user.id, task_id)
    except LookupError:
        not_found("Task not found.")


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    db: DB,
    auth: Auth,
    status_: list[Status] | None = Query(None, alias="status"),  # noqa: B008
    project_id: uuid.UUID | None = None,
    parent_task_id: uuid.UUID | None = None,
    top_level: bool = True,
    q: str | None = Query(None, max_length=200),
) -> list[TaskOut]:
    rows = await svc.list_tasks(
        db,
        auth.user.id,
        status=list(status_) if status_ else None,
        project_id=project_id,
        parent_task_id=parent_task_id,
        top_level=top_level and parent_task_id is None,
        q=q,
    )
    return await _out(db, rows)


@router.get("/tasks/today", response_model=dict[str, list[TaskOut]])
async def today(db: DB, auth: Auth) -> dict[str, list[TaskOut]]:
    tz = ZoneInfo(auth.user.timezone)
    now = datetime.now(tz)
    end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await svc.list_tasks(
        db,
        auth.user.id,
        status=["todo", "in_progress"],
        top_level=True,
        due_before=end.astimezone(UTC),
    )
    overdue = [t for t in rows if t.due_at and t.due_at < start.astimezone(UTC)]
    due_today = [t for t in rows if t not in overdue]
    return {"overdue": await _out(db, overdue), "today": await _out(db, due_today)}


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(body: TaskIn, db: DB, auth: Auth) -> TaskOut:
    data = body.model_dump(exclude={"subtasks"})
    data["due_at"] = _aware(data["due_at"], auth.user.timezone)
    try:
        task = await svc.create_task(db, auth.user.id, **data)
        for title in body.subtasks:
            await svc.create_task(
                db, auth.user.id, title=title, parent_task_id=task.id, project_id=task.project_id
            )
    except LookupError:
        not_found("Project or parent task not found.")
    except ValueError as exc:
        bad_request(str(exc))
    await db.commit()
    await db.refresh(task)
    return (await _out(db, [task]))[0]


@router.post("/tasks/parse")
async def parse(body: ParseIn, db: DB, auth: Auth) -> dict[str, Any]:
    """Preview a task from a sentence. Nothing is saved until the owner confirms."""
    try:
        fields = await parse_task(
            db,
            get_gateway(),
            user_id=auth.user.id,
            text=body.text,
            tz=auth.user.timezone,
            cloud=body.cloud,
        )
    except (ModelUnavailableError, BudgetExceededError, ModelRefusalError) as exc:
        await db.commit()
        bad_request(str(exc), code="model_unavailable")
    except ValueError as exc:
        await db.commit()
        bad_request(str(exc), code="unparseable")
    project = None
    if fields["project_name"]:
        project = await svc.find_project_by_name(db, auth.user.id, fields["project_name"])
    await db.commit()
    return {
        **fields,
        "due_at": fields["due_at"].isoformat() if fields["due_at"] else None,
        "project_id": str(project.id) if project else None,
    }


@router.get("/tasks/{task_id}", response_model=dict[str, Any])
async def get_task(task_id: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    task = await _owned(db, auth, task_id)
    subs = await svc.list_tasks(db, auth.user.id, parent_task_id=task.id)
    return {"task": (await _out(db, [task]))[0], "subtasks": await _out(db, subs)}


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: uuid.UUID, body: TaskPatch, db: DB, auth: Auth) -> TaskOut:
    task = await _owned(db, auth, task_id)
    data = body.model_dump(exclude_unset=True)
    if "due_at" in data:
        data["due_at"] = _aware(data["due_at"], auth.user.timezone)
    try:
        if data.get("status") == "done" and task.status != "done":
            data.pop("status")
            await svc.update_task(db, task, **data)
            await svc.complete_task(db, task, auth.user.timezone)
        else:
            await svc.update_task(db, task, **data)
    except LookupError:
        not_found("Project or parent task not found.")
    except ValueError as exc:
        bad_request(str(exc))
    await db.commit()
    await db.refresh(task)
    return (await _out(db, [task]))[0]


@router.post("/tasks/{task_id}/complete", response_model=dict[str, TaskOut | None])
async def complete(task_id: uuid.UUID, db: DB, auth: Auth) -> dict[str, TaskOut | None]:
    task = await _owned(db, auth, task_id)
    task, nxt = await svc.complete_task(db, task, auth.user.timezone)
    await db.commit()
    await db.refresh(task)
    out = await _out(db, [task, nxt] if nxt else [task])
    return {"task": out[0], "next": out[1] if nxt else None}


class PostponeIn(BaseModel):
    days: int = Field(1, ge=1, le=365)


@router.post("/tasks/{task_id}/postpone", response_model=TaskOut)
async def postpone(task_id: uuid.UUID, body: PostponeIn, db: DB, auth: Auth) -> TaskOut:
    task = await _owned(db, auth, task_id)
    await svc.postpone_task(db, task, days=body.days)
    await db.commit()
    await db.refresh(task)
    return (await _out(db, [task]))[0]


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: uuid.UUID, db: DB, auth: Auth) -> None:
    task = await _owned(db, auth, task_id)
    await db.delete(task)
    await db.commit()


# --- projects ---------------------------------------------------------------------


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(db: DB, auth: Auth, include_archived: bool = False) -> list[ProjectOut]:
    stmt = select(Project).where(Project.user_id == auth.user.id)
    if not include_archived:
        stmt = stmt.where(Project.status == "active")
    projects = list(await db.scalars(stmt.order_by(Project.created_at)))
    tasks = await svc.list_tasks(db, auth.user.id, top_level=True, limit=5000)
    out = []
    for p in projects:
        mine = [t for t in tasks if t.project_id == p.id]
        out.append(
            ProjectOut.model_validate(p).model_copy(
                update={
                    "open_tasks": sum(t.status in ("todo", "in_progress") for t in mine),
                    "done_tasks": sum(t.status == "done" for t in mine),
                }
            )
        )
    return out


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectIn, db: DB, auth: Auth) -> ProjectOut:
    if await svc.find_project_by_name(db, auth.user.id, body.name):
        bad_request("A project with that name exists.", code="duplicate")
    p = await svc.create_project(db, auth.user.id, **body.model_dump())
    await db.commit()
    await db.refresh(p)
    return ProjectOut.model_validate(p)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID, body: ProjectPatch, db: DB, auth: Auth
) -> ProjectOut:
    try:
        p = await svc.get_owned_project(db, auth.user.id, project_id)
    except LookupError:
        not_found("Project not found.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    await db.commit()
    await db.refresh(p)
    return ProjectOut.model_validate(p)
