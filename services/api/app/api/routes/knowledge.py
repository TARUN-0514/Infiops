"""Knowledge base: upload and parse documents, search them, and ask cited questions."""

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.ai.gateway import get_gateway
from app.ai.types import BudgetExceededError, ModelRefusalError, ModelUnavailableError
from app.api.deps import DB, Auth, SettingsDep
from app.api.routes.common import bad_request, not_found
from app.models import Document, DocumentChunk
from app.services import knowledge as kb

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def doc_out(d: Document, chunks: int = 0) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "title": d.title,
        "filename": d.filename,
        "mime_type": d.mime_type,
        "size": d.size,
        "category": d.category,
        "status": d.status,
        "error": d.error,
        "pages": d.pages,
        "chars": d.chars,
        "chunks": chunks,
        "summary": d.summary,
        "created_at": d.created_at.isoformat(),
        "processed_at": d.processed_at.isoformat() if d.processed_at else None,
    }


async def _process(document_id: str) -> None:
    from app.worker import process_document

    await process_document({}, document_id=document_id)


@router.get("/documents")
async def list_documents(
    db: DB, auth: Auth, q: str | None = Query(None, max_length=200)
) -> list[dict[str, Any]]:
    stmt = select(Document).where(Document.user_id == auth.user.id)
    if q:
        stmt = stmt.where(Document.title.ilike(f"%{q}%"))
    docs = list(await db.scalars(stmt.order_by(Document.created_at.desc()).limit(200)))
    counts = await kb.chunk_counts(db, [d.id for d in docs])
    return [doc_out(d, counts.get(d.id, 0)) for d in docs]


@router.post("/documents", status_code=201)
async def upload(
    db: DB,
    auth: Auth,
    settings: SettingsDep,
    background: BackgroundTasks,
    file: UploadFile = File(...),  # noqa: B008
    title: str | None = Form(None, max_length=300),
    category: str | None = Form(None, max_length=60),
) -> dict[str, Any]:
    data = await file.read(settings.kb_max_upload_mb * 1024 * 1024 + 1)
    try:
        doc = await kb.add_document(
            db,
            auth.user,
            filename=file.filename or "file",
            data=data,
            declared_type=file.content_type,
            title=title,
            category=category,
        )
    except ValueError as exc:
        bad_request(str(exc), code="bad_file")
    await db.commit()
    # Parsing runs after the response so large files don't hold the request.
    background.add_task(_process, str(doc.id))
    return doc_out(doc)


async def _doc(db: DB, auth: Auth, did: uuid.UUID) -> Document:
    try:
        return await kb.get_owned(db, auth.user.id, did)
    except LookupError:
        not_found("Document not found.")


@router.get("/documents/{did}")
async def get_document(did: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    d = await _doc(db, auth, did)
    chunks = list(
        await db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == d.id)
            .order_by(DocumentChunk.ordinal)
            .limit(40)
        )
    )
    counts = await kb.chunk_counts(db, [d.id])
    return {
        **doc_out(d, counts.get(d.id, 0)),
        "preview": [
            {"ordinal": c.ordinal, "page": c.page, "label": c.label, "content": c.content}
            for c in chunks
        ],
    }


class DocPatch(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    category: str | None = Field(None, max_length=60)


@router.patch("/documents/{did}")
async def update_document(did: uuid.UUID, body: DocPatch, db: DB, auth: Auth) -> dict[str, Any]:
    d = await _doc(db, auth, did)
    if body.title is not None:
        d.title = body.title
    if body.category is not None:
        d.category = body.category or None
    await db.commit()
    return doc_out(d)


@router.post("/documents/{did}/reprocess")
async def reprocess(
    did: uuid.UUID, db: DB, auth: Auth, background: BackgroundTasks
) -> dict[str, Any]:
    d = await _doc(db, auth, did)
    d.status, d.error = "processing", None
    await db.commit()
    background.add_task(_process, str(d.id))
    return doc_out(d)


@router.delete("/documents/{did}", status_code=204)
async def delete_document(did: uuid.UUID, db: DB, auth: Auth) -> None:
    d = await _doc(db, auth, did)
    await kb.remove(db, d)
    await db.commit()


@router.get("/search")
async def search(
    db: DB, auth: Auth, q: str = Query(..., min_length=2, max_length=300)
) -> list[dict[str, Any]]:
    hits = await kb.search(db, auth.user.id, q, limit=12)
    return [{**kb.citation(i + 1, h), "score": round(h.score, 4)} for i, h in enumerate(hits)]


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    cloud: bool = False


@router.post("/ask")
async def ask(body: AskIn, db: DB, auth: Auth) -> dict[str, Any]:
    try:
        out = await kb.ask(
            db,
            get_gateway(),
            auth.user,
            body.question,
            document_ids=body.document_ids or None,
            cloud=body.cloud,
        )
    except (ModelUnavailableError, BudgetExceededError, ModelRefusalError) as exc:
        await db.commit()
        bad_request(str(exc), code="model_unavailable")
    await db.commit()
    return out
