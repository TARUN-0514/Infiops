"""System status: what is working, what isn't, and what to do about it."""

from typing import Any

from fastapi import APIRouter

from app.api.deps import DB, Auth
from app.services import monitor

router = APIRouter(tags=["status"])


@router.get("/status")
async def system_status(db: DB, auth: Auth) -> dict[str, Any]:
    return await monitor.status(db, auth.user)
