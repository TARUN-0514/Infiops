"""Time the busiest endpoints with about a year of realistic data.

    NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_perf \\
        uv run python scripts/perf.py

Uses a database whose name ends in _perf (it is wiped first) and prints the median of
five calls per endpoint. Used in Phase 7 to find what needed an index."""

from __future__ import annotations

import asyncio
import os
import random
import statistics
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta

os.environ.setdefault("NEXUS_ENV", "test")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENDPOINTS = [
    "/tasks?status=todo",
    "/tasks/today",
    "/email/summary",
    "/email/messages?limit=50",
    "/notifications",
    "/insights",
    "/analytics?days=30",
    "/analytics?days=90",
    "/briefings/today",
    "/checkins/today",
    "/approvals?status=pending",
    "/status",
]


async def seed(owner_id: uuid.UUID, account_id: uuid.UUID) -> None:
    from sqlalchemy import insert

    from app.db.session import get_sessionmaker
    from app.models import CalendarEvent, EmailMessage, Notification, Task, WorkLog

    rnd = random.Random(7)  # noqa: S311 - test data, not secrets
    now = datetime.now(UTC)
    async with get_sessionmaker()() as db:
        tasks = []
        for i in range(6000):
            created = now - timedelta(days=rnd.uniform(0, 365))
            done = rnd.random() < 0.8
            tasks.append(
                {
                    "user_id": owner_id,
                    "title": f"Task {i}",
                    "status": "done" if done else "todo",
                    "due_at": created + timedelta(days=rnd.uniform(-2, 14)),
                    "completed_at": created + timedelta(days=rnd.uniform(0, 10)) if done else None,
                    "created_at": created,
                    "updated_at": created,
                    "postponed_count": rnd.choice([0, 0, 0, 1, 4]),
                }
            )
        await db.execute(insert(Task), tasks)
        mails = []
        for i in range(30000):
            got = now - timedelta(minutes=rnd.uniform(0, 525600))
            mails.append(
                {
                    "user_id": owner_id,
                    "account_id": account_id,
                    "provider_id": f"m{i}",
                    "thread_id": f"t{i // 3}",
                    "from_name": "Sender",
                    "from_addr": "s@example.com",
                    "subject": f"Subject {i}",
                    "snippet": "Hello",
                    "body_text": "Hello " * 200,
                    "received_at": got,
                    "triaged_at": got if i > 20 else None,
                    "needs_reply": rnd.random() < 0.05,
                    "replied_at": got + timedelta(hours=3) if rnd.random() < 0.9 else None,
                    "priority": "high" if rnd.random() < 0.05 else "normal",
                }
            )
        await db.execute(insert(EmailMessage), mails)
        events = []
        for i in range(3000):
            start = now + timedelta(days=rnd.uniform(-350, 30))
            events.append(
                {
                    "user_id": owner_id,
                    "title": f"Meeting {i}",
                    "starts_at": start,
                    "ends_at": start + timedelta(minutes=rnd.choice([30, 60])),
                }
            )
        await db.execute(insert(CalendarEvent), events)
        await db.execute(
            insert(WorkLog),
            [
                {
                    "user_id": owner_id,
                    "day": (now - timedelta(days=rnd.uniform(0, 365))).date(),
                    "content": "Work",
                    "minutes": rnd.choice([None, 30, 60, 120]),
                }
                for _ in range(4000)
            ],
        )
        await db.execute(
            insert(Notification),
            [
                {
                    "user_id": owner_id,
                    "kind": "reminder",
                    "title": f"Note {i}",
                    "body": "",
                    "created_at": now - timedelta(minutes=i * 30),
                }
                for i in range(8000)
            ],
        )
        await db.commit()


async def main() -> int:
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select, text

    import app.models  # noqa: F401
    from app.core.config import get_settings
    from app.db.base import Base
    from app.db.session import dispose_engine, get_engine, get_sessionmaker
    from app.main import create_app
    from app.models import ConnectedAccount, User

    if not get_settings().database_url.rsplit("/", 1)[-1].endswith("_perf"):
        print("Refusing: point NEXUS_DATABASE_URL at a database whose name ends in _perf.")
        return 2
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with get_sessionmaker()() as db:
        await db.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        await db.commit()
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://p") as c:
        owner = {"email": "perf@example.com", "password": "perf horse battery", "display_name": "P"}
        await c.post("/api/v1/auth/register", json=owner)
        async with get_sessionmaker()() as db:
            user = await db.scalar(select(User))
            assert user is not None
            acc = ConnectedAccount(
                user_id=user.id,
                provider="google",
                account_email="p@example.com",
                status="connected",
            )
            db.add(acc)
            await db.commit()
            uid, aid = user.id, acc.id
        t0 = time.perf_counter()
        await seed(uid, aid)
        async with get_sessionmaker()() as db:
            await db.commit()
        async with get_engine().connect() as conn:
            auto = await conn.execution_options(isolation_level="AUTOCOMMIT")
            await auto.execute(text("VACUUM ANALYZE"))
        print(f"seeded in {time.perf_counter() - t0:.1f} s")
        tok = (
            await c.post("/api/v1/auth/login", json={k: owner[k] for k in ("email", "password")})
        ).json()
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        for path in ENDPOINTS:
            times = []
            for _ in range(5):
                t = time.perf_counter()
                r = await c.get("/api/v1" + path, headers=h)
                times.append((time.perf_counter() - t) * 1000)
            print(f"{statistics.median(times):8.1f} ms  {r.status_code}  {path}")
    await dispose_engine()
    return 0


if __name__ == "__main__":
    subprocess.run(["alembic", "upgrade", "head"], check=True, capture_output=True)  # noqa: S607
    sys.exit(asyncio.run(main()))
