"""Background worker (Arq on Redis). Run with: arq app.worker.WorkerSettings

Jobs: memory extraction after each chat turn, and session cleanup. Syncs, reminders and
briefings arrive in later phases.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.logging import configure_logging, log
from app.db.session import dispose_engine, get_sessionmaker
from app.models import Message, User, UserSession


async def extract_memories(
    _: dict[str, Any], *, user_id: str, message_id: str, cloud: bool = False
) -> dict[str, int]:
    """Read the owner's message and the reply that followed, and store new facts."""
    from sqlalchemy import select

    from app.ai.gateway import get_gateway
    from app.ai.memory_agent import extract_and_store
    from app.ai.types import BudgetExceededError, ModelUnavailableError

    async with get_sessionmaker()() as db:
        user = await db.get(User, uuid.UUID(user_id))
        msg = await db.get(Message, uuid.UUID(message_id))
        if user is None or msg is None or msg.user_id != user.id:
            return {}
        reply = await db.scalar(
            select(Message)
            .where(
                Message.conversation_id == msg.conversation_id,
                Message.role == "assistant",
                Message.created_at >= msg.created_at,
                Message.text != "",
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        try:
            counts = await extract_and_store(
                db,
                get_gateway(),
                user=user,
                user_text=msg.text,
                assistant_text=reply.text if reply else "",
                message_id=msg.id,
                cloud=cloud,
            )
        except (ModelUnavailableError, BudgetExceededError) as exc:
            log.warning("extract_memories_skipped", reason=str(exc))
            await db.commit()
            return {}
        await db.commit()
    log.info("extract_memories", **counts)
    return counts


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
    functions: ClassVar[list[Any]] = [purge_expired_sessions, extract_memories]
    cron_jobs: ClassVar[list[Any]] = [
        cron(purge_expired_sessions, hour={3}, minute={15})  # type: ignore[arg-type]
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
