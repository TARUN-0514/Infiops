"""Fixed-window rate limiting backed by Redis."""

from fastapi import HTTPException, status

from app.services.redis import get_redis


async def enforce_rate_limit(bucket: str, limit: int, window_seconds: int) -> None:
    redis = get_redis()
    key = f"ratelimit:{bucket}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count > limit:
        ttl = await redis.ttl(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many attempts. Try again later."},
            headers={"Retry-After": str(max(ttl, 1))},
        )


async def reset_rate_limit(bucket: str) -> None:
    await get_redis().delete(f"ratelimit:{bucket}")
