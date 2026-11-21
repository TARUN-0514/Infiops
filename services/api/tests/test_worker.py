from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db.session import get_sessionmaker
from app.models import User, UserSession
from app.worker import purge_expired_sessions


async def test_purge_removes_only_old_sessions() -> None:
    now = datetime.now(UTC)
    async with get_sessionmaker()() as db:
        user = User(email="w@example.com", password_hash="x", display_name="W")
        db.add(user)
        await db.flush()
        db.add_all(
            [
                UserSession(
                    user_id=user.id,
                    refresh_token_hash="a" * 64,
                    last_used_at=now,
                    expires_at=now - timedelta(days=40),
                ),
                UserSession(
                    user_id=user.id,
                    refresh_token_hash="b" * 64,
                    last_used_at=now,
                    expires_at=now + timedelta(days=5),
                ),
            ]
        )
        await db.commit()
    assert await purge_expired_sessions({}) == 1
    async with get_sessionmaker()() as db:
        assert await db.scalar(select(func.count()).select_from(UserSession)) == 1
