"""Background jobs. Enqueued on Redis for the Arq worker, or run inline when
NEXUS_JOBS_INLINE is set (single-process setups)."""

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings
from app.core.logging import log

_pool: ArqRedis | None = None


async def enqueue(name: str, **kwargs: Any) -> None:
    global _pool
    settings = get_settings()
    if settings.jobs_inline:
        from app import worker

        await getattr(worker, name)({}, **kwargs)
        return
    try:
        if _pool is None:
            _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        await _pool.enqueue_job(name, **kwargs)
    except OSError as exc:
        log.warning("enqueue_failed", job=name, error=type(exc).__name__)


async def close_jobs() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
