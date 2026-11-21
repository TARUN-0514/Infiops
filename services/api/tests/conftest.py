import base64
import os
import secrets
import subprocess
from collections.abc import AsyncIterator

import pytest

os.environ.setdefault("NEXUS_ENV", "test")
os.environ.setdefault(
    "NEXUS_DATABASE_URL", "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus_test"
)
os.environ.setdefault("NEXUS_REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("NEXUS_JWT_SECRET", secrets.token_urlsafe(32))
os.environ.setdefault("NEXUS_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
os.environ.setdefault("NEXUS_COOKIE_SECURE", "false")

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import dispose_engine, get_sessionmaker
from app.main import create_app
from app.services.redis import close_redis, get_redis

TABLES = "audit_logs, devices, user_sessions, user_preferences, users"


@pytest.fixture(scope="session", autouse=True)
def migrated() -> None:
    subprocess.run(["alembic", "upgrade", "head"], check=True, capture_output=True)  # noqa: S607


@pytest.fixture(autouse=True)
async def clean() -> AsyncIterator[None]:
    async with get_sessionmaker()() as db:
        await db.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        await db.commit()
    await get_redis().flushdb()
    yield


@pytest.fixture(scope="session", autouse=True)
async def teardown() -> AsyncIterator[None]:
    yield
    await dispose_engine()
    await close_redis()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


OWNER = {"email": "owner@example.com", "password": "correct horse battery", "display_name": "Owner"}


async def register_and_login(client: AsyncClient) -> dict[str, str]:
    r = await client.post("/api/v1/auth/register", json=OWNER)
    assert r.status_code == 201, r.text
    r = await client.post(
        "/api/v1/auth/login", json={"email": OWNER["email"], "password": OWNER["password"]}
    )
    assert r.status_code == 200, r.text
    return r.json()
