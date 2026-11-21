"""Memory browser: list, add, edit (new version), confirm, forget, history, conflicts
and consent settings."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DB, Auth
from app.api.routes.common import bad_request, not_found
from app.models import MemoryConflict, MemoryItem
from app.models.memory import MEMORY_CATEGORIES
from app.services import memory as mem

router = APIRouter(prefix="/memory", tags=["memory"])

Category = Literal[
    "profile", "preference", "work", "people", "health", "finance", "goal", "routine", "other"
]
Consent = Literal["auto", "ask", "off"]


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    source_type: str
    source_id: str | None
    excerpt: str | None
    created_at: datetime


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    category: str
    content: str
    confidence: float
    status: str
    privacy: str
    version: int
    supersedes_id: uuid.UUID | None
    created_at: datetime
    last_used_at: datetime | None
    sources: list[SourceOut] = []


class MemoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=3, max_length=1000)
    category: Category = "other"
    kind: Literal["semantic", "episodic", "procedural"] = "semantic"
    privacy: Literal["normal", "sensitive", "secret"] = "normal"


class MemoryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str | None = Field(None, min_length=3, max_length=1000)
    category: Category | None = None
    privacy: Literal["normal", "sensitive", "secret"] | None = None


class ConflictOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    memory: MemoryOut
    candidate: dict[str, object]
    status: str
    created_at: datetime


async def _with_sources(db: DB, items: list[MemoryItem]) -> list[MemoryOut]:
    srcs = await mem.sources(db, [i.id for i in items])
    return [
        MemoryOut.model_validate(i).model_copy(
            update={"sources": [SourceOut.model_validate(s) for s in srcs[i.id]]}
        )
        for i in items
    ]


async def _owned(db: DB, auth: Auth, memory_id: uuid.UUID) -> MemoryItem:
    try:
        return await mem.get_owned(db, auth.user.id, memory_id)
    except LookupError:
        not_found("Memory not found.")


@router.get("", response_model=list[MemoryOut])
async def list_memories(
    db: DB,
    auth: Auth,
    status_: Literal["active", "inferred", "superseded"] | None = Query(None, alias="status"),
    category: Category | None = None,
    q: str | None = Query(None, max_length=200),
) -> list[MemoryOut]:
    if q:
        hits = await mem.search(
            db, auth.user.id, q, limit=30, include_inferred=True, allow_secret=True
        )
        items = [h.item for h in hits if not category or h.item.category == category]
        if status_:
            items = [i for i in items if i.status == status_]
    else:
        items = await mem.list_items(db, auth.user.id, status=status_, category=category)
    return await _with_sources(db, items)


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def add_memory(body: MemoryIn, db: DB, auth: Auth) -> MemoryOut:
    item, _ = await mem.remember(
        db,
        auth.user.id,
        body.content,
        category=body.category,
        kind=body.kind,
        privacy=body.privacy,
        source_type="manual",
    )
    await db.commit()
    await db.refresh(item)
    return (await _with_sources(db, [item]))[0]


@router.get("/consent", response_model=dict[str, Consent])
async def get_consent(db: DB, auth: Auth) -> dict[str, str]:
    return await mem.consent_policy(db, auth.user.id)


@router.put("/consent", response_model=dict[str, Consent])
async def put_consent(body: dict[Category, Consent], db: DB, auth: Auth) -> dict[str, str]:
    policy = await mem.set_consent_policy(
        db, auth.user.id, {str(k): str(v) for k, v in body.items()}
    )
    await db.commit()
    return policy


@router.get("/conflicts", response_model=list[ConflictOut])
async def conflicts(db: DB, auth: Auth) -> list[ConflictOut]:
    rows = list(
        await db.scalars(
            select(MemoryConflict)
            .where(MemoryConflict.user_id == auth.user.id, MemoryConflict.status == "open")
            .order_by(MemoryConflict.created_at)
        )
    )
    out = []
    for c in rows:
        item = await db.get(MemoryItem, c.memory_id)
        if item is None:
            continue
        out.append(
            ConflictOut(
                id=c.id,
                memory=(await _with_sources(db, [item]))[0],
                candidate=c.candidate,
                status=c.status,
                created_at=c.created_at,
            )
        )
    return out


class ResolveIn(BaseModel):
    keep: Literal["existing", "candidate"]


@router.post("/conflicts/{conflict_id}/resolve", response_model=MemoryOut | None)
async def resolve(conflict_id: uuid.UUID, body: ResolveIn, db: DB, auth: Auth) -> MemoryOut | None:
    c = await db.get(MemoryConflict, conflict_id)
    if c is None or c.user_id != auth.user.id or c.status != "open":
        not_found("Conflict not found.")
    item = await mem.resolve_conflict(db, c, body.keep)
    await db.commit()
    if item is None:
        return None
    await db.refresh(item)
    return (await _with_sources(db, [item]))[0]


@router.get("/categories")
async def categories() -> list[str]:
    return list(MEMORY_CATEGORIES)


@router.get("/{memory_id}", response_model=MemoryOut)
async def get_memory(memory_id: uuid.UUID, db: DB, auth: Auth) -> MemoryOut:
    return (await _with_sources(db, [await _owned(db, auth, memory_id)]))[0]


@router.get("/{memory_id}/history", response_model=list[MemoryOut])
async def memory_history(memory_id: uuid.UUID, db: DB, auth: Auth) -> list[MemoryOut]:
    item = await _owned(db, auth, memory_id)
    return await _with_sources(db, await mem.history(db, item))


@router.patch("/{memory_id}", response_model=MemoryOut)
async def edit_memory(memory_id: uuid.UUID, body: MemoryPatch, db: DB, auth: Auth) -> MemoryOut:
    """Edits never overwrite: a new version supersedes the old one."""
    item = await _owned(db, auth, memory_id)
    try:
        new = await mem.supersede(
            db, item, body.content or item.content, category=body.category, privacy=body.privacy
        )
    except ValueError as exc:
        bad_request(str(exc))
    await db.commit()
    await db.refresh(new)
    return (await _with_sources(db, [new]))[0]


@router.post("/{memory_id}/confirm", response_model=MemoryOut)
async def confirm_memory(memory_id: uuid.UUID, db: DB, auth: Auth) -> MemoryOut:
    item = await _owned(db, auth, memory_id)
    if item.status == "superseded":
        bad_request("Only the latest version can be confirmed.")
    await mem.confirm(db, item)
    await db.commit()
    await db.refresh(item)
    return (await _with_sources(db, [item]))[0]


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget_memory(memory_id: uuid.UUID, db: DB, auth: Auth) -> None:
    item = await _owned(db, auth, memory_id)
    await mem.forget(db, item)
    await db.commit()
