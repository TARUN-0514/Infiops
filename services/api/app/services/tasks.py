"""Tasks and projects: CRUD, subtasks, recurrence and postponing."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Task
from app.services import audit

TASK_FIELDS = {
    "title",
    "notes",
    "status",
    "priority",
    "due_at",
    "all_day",
    "recurrence",
    "project_id",
    "parent_task_id",
    "position",
}


def validate_rrule(rule: str | None) -> str | None:
    if not rule:
        return None
    rule = rule.strip()
    if rule.upper().startswith("RRULE:"):
        rule = rule[6:]
    try:
        rrulestr(rule, dtstart=datetime(2026, 1, 1, tzinfo=UTC))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid repeat rule: {rule}") from exc
    return rule


async def get_owned_task(db: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    task = await db.get(Task, task_id)
    if task is None or task.user_id != user_id:
        raise LookupError("task not found")
    return task


async def get_owned_project(db: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if project is None or project.user_id != user_id:
        raise LookupError("project not found")
    return project


async def find_project_by_name(db: AsyncSession, user_id: uuid.UUID, name: str) -> Project | None:
    return await db.scalar(
        select(Project).where(
            Project.user_id == user_id,
            func.lower(Project.name) == name.strip().lower(),
            Project.status == "active",
        )
    )


async def create_project(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    name: str,
    description: str | None = None,
    color: str = "violet",
) -> Project:
    project = Project(user_id=user_id, name=name.strip(), description=description, color=color)
    db.add(project)
    await db.flush()
    audit.record(db, "project.created", user_id=user_id, target=str(project.id))
    return project


async def _check_refs(db: AsyncSession, user_id: uuid.UUID, data: dict[str, Any]) -> None:
    if data.get("project_id"):
        await get_owned_project(db, user_id, data["project_id"])
    if data.get("parent_task_id"):
        parent = await get_owned_task(db, user_id, data["parent_task_id"])
        if parent.parent_task_id is not None:
            raise ValueError("Subtasks can be one level deep.")


async def create_task(
    db: AsyncSession, user_id: uuid.UUID, *, source: str = "manual", **data: Any
) -> Task:
    data = {k: v for k, v in data.items() if k in TASK_FIELDS}
    data["recurrence"] = validate_rrule(data.get("recurrence"))
    await _check_refs(db, user_id, data)
    if data.get("recurrence") and not data.get("due_at"):
        raise ValueError("A repeating task needs a due date.")
    task = Task(user_id=user_id, source=source, **data)
    db.add(task)
    await db.flush()
    audit.record(db, "task.created", user_id=user_id, target=str(task.id), source=source)
    return task


async def update_task(db: AsyncSession, task: Task, **data: Any) -> Task:
    data = {k: v for k, v in data.items() if k in TASK_FIELDS}
    if "recurrence" in data:
        data["recurrence"] = validate_rrule(data["recurrence"])
    if data.get("parent_task_id") == task.id:
        raise ValueError("A task cannot be its own parent.")
    await _check_refs(db, task.user_id, data)
    for key, value in data.items():
        setattr(task, key, value)
    if data.get("status") == "done" and task.completed_at is None:
        task.completed_at = datetime.now(UTC)
    elif "status" in data and data["status"] != "done":
        task.completed_at = None
    task.updated_at = datetime.now(UTC)
    return task


def next_occurrence(task: Task, tz: str) -> datetime | None:
    if not task.recurrence or task.due_at is None:
        return None
    zone = ZoneInfo(tz)
    start = task.due_at.astimezone(zone)
    rule = rrulestr(task.recurrence, dtstart=start)
    nxt = rule.after(start)
    return nxt.astimezone(UTC) if nxt else None


async def complete_task(db: AsyncSession, task: Task, tz: str) -> tuple[Task, Task | None]:
    """Mark done. A repeating task spawns its next occurrence."""
    now = datetime.now(UTC)
    task.status, task.completed_at, task.updated_at = "done", now, now
    follow_up = None
    nxt = next_occurrence(task, tz)
    if nxt is not None:
        follow_up = Task(
            user_id=task.user_id,
            project_id=task.project_id,
            parent_task_id=task.parent_task_id,
            title=task.title,
            notes=task.notes,
            priority=task.priority,
            due_at=nxt,
            all_day=task.all_day,
            recurrence=task.recurrence,
            source=task.source,
        )
        db.add(follow_up)
        await db.flush()
    audit.record(db, "task.completed", user_id=task.user_id, target=str(task.id))
    return task, follow_up


async def postpone_task(db: AsyncSession, task: Task, *, days: int = 1) -> Task:
    base = task.due_at or datetime.now(UTC)
    task.due_at = base + timedelta(days=days)
    task.postponed_count += 1
    task.updated_at = datetime.now(UTC)
    return task


async def list_tasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: list[str] | None = None,
    project_id: uuid.UUID | None = None,
    parent_task_id: uuid.UUID | None = None,
    top_level: bool = False,
    due_before: datetime | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[Task]:
    stmt = select(Task).where(Task.user_id == user_id)
    if status:
        stmt = stmt.where(Task.status.in_(status))
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if parent_task_id:
        stmt = stmt.where(Task.parent_task_id == parent_task_id)
    elif top_level:
        stmt = stmt.where(Task.parent_task_id.is_(None))
    if due_before:
        stmt = stmt.where(Task.due_at <= due_before)
    if q:
        stmt = stmt.where(Task.title.ilike(f"%{q}%"))
    stmt = stmt.order_by(Task.due_at.asc().nulls_last(), Task.position, Task.created_at).limit(
        limit
    )
    return list(await db.scalars(stmt))


async def subtask_counts(
    db: AsyncSession, task_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    if not task_ids:
        return {}
    rows = await db.execute(
        select(
            Task.parent_task_id,
            func.count(),
            func.count().filter(Task.status == "done"),
        )
        .where(Task.parent_task_id.in_(task_ids))
        .group_by(Task.parent_task_id)
    )
    return {pid: (total, done) for pid, total, done in rows if pid is not None}
