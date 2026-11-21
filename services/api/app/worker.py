"""Background worker (Arq on Redis). Run with: arq app.worker.WorkerSettings

Phase 0 only ships a maintenance job. Agent runs, syncs, reminders and briefings arrive in later
phases as additional functions and cron jobs here.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.logging import configure_logging, log
from app.db.session import dispose_engine, get_sessionmaker
from app.models import UserSession


async def purge_expired_sessions(_: dict[str, Any]) -> int:
    """Delete sessions that expired or were revoked more than 30 days ago."""
    cutoff = datetime.now(UTC) - timedelta(days=30)
    async with get_sessionmaker()() as db:
        result = await db.execute(
            delete(UserSession).where(
                (UserSession.expires_at < cutoff) | (UserSession.revoked_at < cutoff)
            )
        )
        await db.commit()
    removed = int(getattr(result, "rowcount", 0) or 0)
    log.info("purge_expired_sessions", removed=removed)
    return removed


async def startup(_: dict[str, Any]) -> None:
    configure_logging(get_settings().log_level)


async def shutdown(_: dict[str, Any]) -> None:
    await dispose_engine()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [purge_expired_sessions]
    cron_jobs: ClassVar[list[Any]] = [
        cron(purge_expired_sessions, hour={3}, minute={15})  # type: ignore[arg-type]
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
