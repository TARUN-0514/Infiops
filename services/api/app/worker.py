"""Background worker (Arq on Redis). Run with: arq app.worker.WorkerSettings

Jobs: memory extraction after each chat turn, Google sync (Gmail, triage, Calendar),
the morning briefing, and session cleanup.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import configure_logging, log
from app.db.session import dispose_engine, get_sessionmaker
from app.models import ConnectedAccount, Document, Message, User, UserSession


async def extract_memories(
    _: dict[str, Any], *, user_id: str, message_id: str, cloud: bool = False
) -> dict[str, int]:
    """Read the owner's message and the reply that followed, and store new facts."""

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


async def run_account_sync(db: AsyncSession, account: ConnectedAccount) -> dict[str, Any]:
    """Sync Gmail and Calendar for one account, then triage new mail with the local model.
    Each part reports its own result so one failure doesn't hide the others."""
    from app.ai.gateway import get_gateway
    from app.ai.types import BudgetExceededError, ModelUnavailableError
    from app.integrations.google import GoogleError
    from app.services import calendar as cal
    from app.services import email as mail
    from app.services import integrations as integ

    user = await db.get(User, account.user_id)
    if user is None:
        return {}
    gc = integ.client(account)
    out: dict[str, Any] = {}
    try:
        out["emails_added"] = await mail.sync_gmail(db, account, gc)
    except GoogleError as exc:
        out["gmail_error"] = str(exc)
    try:
        out["events_changed"] = await cal.sync_calendar(db, account, gc, user.timezone)
    except GoogleError as exc:
        out["calendar_error"] = str(exc)
    await db.flush()
    try:
        out["triaged"] = await mail.triage(db, get_gateway(), user)
    except (ModelUnavailableError, BudgetExceededError) as exc:
        out["triage_error"] = str(exc)
    return out


async def sync_account(_: dict[str, Any], *, account_id: str) -> dict[str, Any]:
    async with get_sessionmaker()() as db:
        account = await db.get(ConnectedAccount, uuid.UUID(account_id))
        if account is None or account.status != "connected":
            return {}
        result = await run_account_sync(db, account)
        await db.commit()
    log.info("sync_account", **{k: v for k, v in result.items() if not k.endswith("error")})
    return result


async def sync_all(ctx: dict[str, Any]) -> int:
    async with get_sessionmaker()() as db:
        ids = list(
            await db.scalars(
                select(ConnectedAccount.id).where(ConnectedAccount.status == "connected")
            )
        )
    for account_id in ids:
        await sync_account(ctx, account_id=str(account_id))
    return len(ids)


async def briefing_tick(_: dict[str, Any]) -> int:
    """Every few minutes: write and deliver any morning briefing, midday check-in, evening
    review or monthly report that is due."""
    from app.ai.gateway import get_gateway
    from app.services import briefing, checkins

    delivered = 0
    async with get_sessionmaker()() as db:
        for user, day in await briefing.due_users(db):
            await briefing.deliver(db, get_gateway(), user, day)
            await db.commit()
            delivered += 1
        for user, kind, day in await checkins.due(db):
            await checkins.deliver(db, get_gateway(), user, kind, day)
            await db.commit()
            delivered += 1
    return delivered


async def reminders_tick(_: dict[str, Any]) -> int:
    """Hourly, after 8 AM the owner's time: bills and EMIs coming due, findings past SLA
    and follow-ups due, and important dates coming up. Each is sent once."""
    from app.ai.timeutil import now_local
    from app.models import User
    from app.services import finance_plans, personal
    from app.services import workspaces as ws_svc

    sent = 0
    async with get_sessionmaker()() as db:
        for user in list(await db.scalars(select(User))):
            local = now_local(user.timezone)
            if local.hour < 8:
                continue
            sent += await finance_plans.send_reminders(db, user, local.date())
            sent += await ws_svc.sla_alerts(db, user, local.date())
            sent += await personal.date_reminders(db, user, local.date())
            await db.commit()
    return sent


async def process_document(_: dict[str, Any], *, document_id: str) -> str:
    from app.ai.gateway import get_gateway
    from app.services import knowledge as kb

    async with get_sessionmaker()() as db:
        doc = await db.get(Document, uuid.UUID(document_id))
        if doc is None:
            return "missing"
        await kb.process(db, get_gateway(), doc)
        await db.commit()
        return doc.status


async def research_job(_: dict[str, Any], *, report_id: str) -> str:
    from app.ai.gateway import get_gateway
    from app.models import ResearchReport
    from app.services import research

    async with get_sessionmaker()() as db:
        report = await db.get(ResearchReport, uuid.UUID(report_id))
        if report is None or report.status != "running":
            return "skipped"
        await research.run(db, get_gateway(), report)
        await db.commit()
        return report.status


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


async def automation_tick(_: dict[str, Any]) -> int:
    from app.ai.gateway import get_gateway
    from app.ai.tools.builtin import get_registry
    from app.services import automation_engine

    async with get_sessionmaker()() as db:
        return await automation_engine.tick(db, get_gateway(), get_registry())


async def startup(_: dict[str, Any]) -> None:
    configure_logging(get_settings().log_level)


async def shutdown(_: dict[str, Any]) -> None:
    await dispose_engine()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [
        purge_expired_sessions,
        extract_memories,
        sync_account,
        sync_all,
        briefing_tick,
        reminders_tick,
        process_document,
        research_job,
        automation_tick,
    ]
    cron_jobs: ClassVar[list[Any]] = [
        cron(purge_expired_sessions, hour={3}, minute={15}),  # type: ignore[arg-type]
        cron(
            sync_all,
            minute=set(range(0, 60, max(1, get_settings().sync_interval_minutes))),
            run_at_startup=True,
        ),
        cron(briefing_tick, minute=set(range(0, 60, 5))),  # type: ignore[arg-type]
        cron(reminders_tick, minute={7}),  # type: ignore[arg-type]
        cron(automation_tick, second={30}),  # type: ignore[arg-type]  # every minute
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
