"""Memory engine: remember, version, confirm, forget and hybrid search."""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, literal_column, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import get_embedder
from app.models import MemoryConflict, MemoryItem, MemorySource, UserPreferences
from app.models.memory import MEMORY_CATEGORIES
from app.services import audit

# Default consent per category: auto saves explicit facts, ask holds everything for
# confirmation, off never stores. Health, finance and people start on ask.
DEFAULT_CONSENT: dict[str, str] = {
    "profile": "auto",
    "preference": "auto",
    "work": "auto",
    "goal": "auto",
    "routine": "auto",
    "other": "auto",
    "people": "ask",
    "health": "ask",
    "finance": "ask",
}
DUPLICATE_SIMILARITY = 0.95


@dataclass
class Hit:
    item: MemoryItem
    score: float


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower()).rstrip(".")


async def consent_policy(db: AsyncSession, user_id: uuid.UUID) -> dict[str, str]:
    prefs = await db.get(UserPreferences, user_id)
    saved = (prefs.settings if prefs else {}).get("memory_consent", {})
    return {c: saved.get(c, DEFAULT_CONSENT[c]) for c in MEMORY_CATEGORIES}


async def set_consent_policy(
    db: AsyncSession, user_id: uuid.UUID, policy: dict[str, str]
) -> dict[str, str]:
    prefs = await db.get(UserPreferences, user_id)
    if prefs is None:
        prefs = UserPreferences(user_id=user_id, settings={})
        db.add(prefs)
    current = await consent_policy(db, user_id)
    current.update({k: v for k, v in policy.items() if k in MEMORY_CATEGORIES})
    prefs.settings = {**(prefs.settings or {}), "memory_consent": current}
    return current


async def _embed_one(text: str) -> list[float] | None:
    vectors = await get_embedder().embed([text])
    return vectors[0] if vectors else None


async def find_duplicate(
    db: AsyncSession, user_id: uuid.UUID, content: str, embedding: list[float] | None
) -> MemoryItem | None:
    live = (MemoryItem.user_id == user_id, MemoryItem.status != "superseded")
    rows = await db.scalars(select(MemoryItem).where(*live))
    norm = _normalise(content)
    for item in rows:
        if _normalise(item.content) == norm:
            return item
    if embedding is None:
        return None
    distance = MemoryItem.embedding.cosine_distance(embedding)
    row = (
        await db.execute(
            select(MemoryItem, distance.label("d"))
            .where(*live, MemoryItem.embedding.is_not(None))
            .order_by(distance)
            .limit(1)
        )
    ).first()
    if row is not None and 1 - float(row.d) >= DUPLICATE_SIMILARITY:
        found: MemoryItem = row[0]
        return found
    return None


async def remember(
    db: AsyncSession,
    user_id: uuid.UUID,
    content: str,
    *,
    category: str = "other",
    kind: str = "semantic",
    privacy: str = "normal",
    confidence: float = 1.0,
    status: str = "active",
    source_type: str = "manual",
    source_id: str | None = None,
    excerpt: str | None = None,
) -> tuple[MemoryItem, bool]:
    """Store a memory, or add a source to an identical one. Returns (item, created)."""
    content = content.strip()
    embedding = await _embed_one(content) if privacy != "secret" else None
    existing = await find_duplicate(db, user_id, content, embedding)
    if existing is not None:
        db.add(
            MemorySource(
                memory_id=existing.id,
                source_type=source_type,
                source_id=source_id,
                excerpt=excerpt,
            )
        )
        existing.confidence = min(1.0, max(existing.confidence, confidence) + 0.05)
        if status == "active" and existing.status == "inferred":
            existing.status = "active"
        return existing, False
    item = MemoryItem(
        user_id=user_id,
        content=content,
        category=category,
        kind=kind,
        privacy=privacy,
        confidence=confidence,
        status=status,
        embedding=embedding,
    )
    db.add(item)
    await db.flush()
    db.add(
        MemorySource(
            memory_id=item.id, source_type=source_type, source_id=source_id, excerpt=excerpt
        )
    )
    audit.record(db, "memory.created", user_id=user_id, target=str(item.id), category=category)
    return item, True


async def get_owned(db: AsyncSession, user_id: uuid.UUID, memory_id: uuid.UUID) -> MemoryItem:
    item = await db.get(MemoryItem, memory_id)
    if item is None or item.user_id != user_id:
        raise LookupError("memory not found")
    return item


async def supersede(
    db: AsyncSession,
    item: MemoryItem,
    new_content: str,
    *,
    source_type: str = "manual",
    source_id: str | None = None,
    category: str | None = None,
    privacy: str | None = None,
) -> MemoryItem:
    """Write a new version and keep the old one as history."""
    if item.status == "superseded":
        raise ValueError("Only the latest version can be changed.")
    now = datetime.now(UTC)
    item.status, item.superseded_at = "superseded", now
    new_privacy = privacy or item.privacy
    new = MemoryItem(
        user_id=item.user_id,
        content=new_content.strip(),
        category=category or item.category,
        kind=item.kind,
        privacy=new_privacy,
        confidence=1.0,
        status="active",
        version=item.version + 1,
        supersedes_id=item.id,
        embedding=await _embed_one(new_content) if new_privacy != "secret" else None,
    )
    db.add(new)
    await db.flush()
    db.add(MemorySource(memory_id=new.id, source_type=source_type, source_id=source_id))
    audit.record(db, "memory.updated", user_id=item.user_id, target=str(new.id))
    return new


async def confirm(db: AsyncSession, item: MemoryItem) -> MemoryItem:
    item.status, item.confidence = "active", 1.0
    audit.record(db, "memory.confirmed", user_id=item.user_id, target=str(item.id))
    return item


async def forget(db: AsyncSession, item: MemoryItem) -> int:
    """Delete a memory and every earlier version of it. Content is not kept anywhere."""
    ids = [item.id]
    cursor = item.supersedes_id
    while cursor is not None:
        prev = await db.get(MemoryItem, cursor)
        if prev is None:
            break
        ids.append(prev.id)
        cursor = prev.supersedes_id
    for mid in ids:
        obj = await db.get(MemoryItem, mid)
        if obj is not None:
            await db.delete(obj)
    audit.record(
        db, "memory.forgotten", user_id=item.user_id, target=str(item.id), versions=len(ids)
    )
    return len(ids)


async def history(db: AsyncSession, item: MemoryItem) -> list[MemoryItem]:
    """All versions, newest first: walk forward to the latest, then back."""
    latest = item
    while True:
        nxt = await db.scalar(select(MemoryItem).where(MemoryItem.supersedes_id == latest.id))
        if nxt is None:
            break
        latest = nxt
    chain = [latest]
    while chain[-1].supersedes_id is not None:
        prev = await db.get(MemoryItem, chain[-1].supersedes_id)
        if prev is None:
            break
        chain.append(prev)
    return chain


async def sources(
    db: AsyncSession, memory_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[MemorySource]]:
    out: dict[uuid.UUID, list[MemorySource]] = {mid: [] for mid in memory_ids}
    if not memory_ids:
        return out
    rows = await db.scalars(
        select(MemorySource)
        .where(MemorySource.memory_id.in_(memory_ids))
        .order_by(MemorySource.created_at)
    )
    for src in rows:
        out[src.memory_id].append(src)
    return out


async def search(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    *,
    limit: int = 8,
    include_inferred: bool = False,
    allow_secret: bool = False,
    touch: bool = False,
) -> list[Hit]:
    """Hybrid retrieval: full-text rank and vector similarity merged with reciprocal
    rank fusion. Works with full-text only when no embedding model is set."""
    statuses = ["active", "inferred"] if include_inferred else ["active"]
    base = [MemoryItem.user_id == user_id, MemoryItem.status.in_(statuses)]
    if not allow_secret:
        base.append(MemoryItem.privacy != "secret")

    ranked: dict[uuid.UUID, float] = {}
    items: dict[uuid.UUID, MemoryItem] = {}
    k = 60.0

    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    if words:
        tsq = func.to_tsquery("english", " | ".join(words))
        rank = func.ts_rank(MemoryItem.search, tsq)
        rows = await db.execute(
            select(MemoryItem, rank.label("r"))
            .where(*base, MemoryItem.search.op("@@")(tsq))
            .order_by(literal_column("r").desc())
            .limit(limit * 3)
        )
        for pos, row in enumerate(rows):
            item = row[0]
            items[item.id] = item
            ranked[item.id] = ranked.get(item.id, 0.0) + 1.0 / (k + pos)

    embedding = await _embed_one(query) if query.strip() else None
    if embedding is not None:
        distance = MemoryItem.embedding.cosine_distance(embedding)
        rows = await db.execute(
            select(MemoryItem, distance.label("d"))
            .where(*base, MemoryItem.embedding.is_not(None))
            .order_by(distance)
            .limit(limit * 3)
        )
        for pos, row in enumerate(rows):
            if 1 - float(row.d) < 0.2:
                continue
            item = row[0]
            items[item.id] = item
            ranked[item.id] = ranked.get(item.id, 0.0) + 1.0 / (k + pos)

    top = sorted(ranked.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    hits = [Hit(items[mid], score) for mid, score in top]
    if touch and hits:
        await db.execute(
            update(MemoryItem)
            .where(MemoryItem.id.in_([h.item.id for h in hits]))
            .values(last_used_at=datetime.now(UTC))
        )
    return hits


async def list_items(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    category: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> list[MemoryItem]:
    stmt = select(MemoryItem).where(MemoryItem.user_id == user_id)
    stmt = (
        stmt.where(MemoryItem.status == status)
        if status
        else stmt.where(MemoryItem.status != "superseded")
    )
    if category:
        stmt = stmt.where(MemoryItem.category == category)
    if q:
        stmt = stmt.where(or_(MemoryItem.content.ilike(f"%{q}%")))
    stmt = stmt.order_by(MemoryItem.created_at.desc()).limit(limit)
    return list(await db.scalars(stmt))


async def open_conflict(
    db: AsyncSession, existing: MemoryItem, candidate: dict[str, Any]
) -> MemoryConflict:
    conflict = MemoryConflict(user_id=existing.user_id, memory_id=existing.id, candidate=candidate)
    db.add(conflict)
    await db.flush()
    return conflict


async def resolve_conflict(
    db: AsyncSession, conflict: MemoryConflict, keep: str
) -> MemoryItem | None:
    existing = await db.get(MemoryItem, conflict.memory_id)
    conflict.status, conflict.resolution = "resolved", keep
    conflict.resolved_at = datetime.now(UTC)
    if existing is None or keep == "existing":
        return existing
    cand = conflict.candidate
    return await supersede(
        db,
        existing,
        cand["content"],
        source_type=cand.get("source_type", "chat"),
        source_id=cand.get("source_id"),
    )
