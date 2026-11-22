"""Phase 7 operations: system status, alerts, and the backup and restore drill."""

import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import make_url, select, text

from app.ai.providers import ScriptedProvider
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import Notification
from app.services import monitor
from app.services.redis import get_redis
from tests.conftest import auth_headers
from tests.test_finance import _tx

API = "/api/v1"
INFRA = Path(__file__).resolve().parents[3] / "infra" / "backup"


@pytest.fixture
def backups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(get_settings(), "backup_dir", str(tmp_path))
    return tmp_path


def _manifest(root: Path, at: datetime, *, verified: bool = False) -> Path:
    folder = root / at.strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir()
    created = at.strftime("%Y-%m-%dT%H:%M:%SZ")
    (folder / "manifest.json").write_text(
        json.dumps({"created_at": created, "size_mb": 1.5, "counts": {}})
    )
    if verified:
        (folder / "verified.json").write_text(json.dumps({"verified_at": created}))
    return folder


async def _checks(client: AsyncClient, h: dict[str, str]) -> dict[str, dict[str, Any]]:
    r = await client.get(f"{API}/status", headers=h)
    assert r.status_code == 200, r.text
    return {c["key"]: c for c in r.json()["checks"]}


async def test_status_needs_sign_in(client: AsyncClient) -> None:
    assert (await client.get(f"{API}/status")).status_code == 401


async def test_fresh_install_says_what_is_missing(
    client: AsyncClient, model: ScriptedProvider, backups: Path
) -> None:
    h = await auth_headers(client)
    r = await client.get(f"{API}/status", headers=h)
    body = r.json()
    checks = {c["key"]: c for c in body["checks"]}
    assert body["overall"] == "error"  # the worker has never run
    assert checks["database"]["state"] == "ok" and checks["redis"]["state"] == "ok"
    assert (
        checks["worker"]["state"] == "error" and "never seen" in checks["worker"]["detail"].lower()
    )
    assert checks["jobs"]["state"] == "off"
    assert checks["sync"]["state"] == "off" and checks["automations"]["state"] == "off"
    assert checks["backups"]["state"] == "warn" and "No backups" in checks["backups"]["detail"]
    assert checks["model"]["state"] == "ok"
    assert (
        checks["disk"]["state"] in ("ok", "warn", "error") and "GB free" in checks["disk"]["detail"]
    )


async def test_worker_heartbeat_and_job_errors(
    client: AsyncClient, model: ScriptedProvider, backups: Path
) -> None:
    h = await auth_headers(client)
    await monitor.heartbeat()

    @monitor.tracked("demo_job")
    async def job(fail: bool) -> int:
        if fail:
            raise RuntimeError("Gmail said 503")
        return 1

    assert await job(False) == 1
    checks = await _checks(client, h)
    assert checks["worker"]["state"] == "ok"
    assert checks["jobs"]["state"] == "ok"
    with pytest.raises(RuntimeError):
        await job(True)
    checks = await _checks(client, h)
    assert checks["jobs"]["state"] == "warn"
    assert "demo_job: RuntimeError: Gmail said 503" in checks["jobs"]["detail"]
    assert checks["jobs"]["jobs"]["demo_job"]["failures"] == 1
    assert checks["jobs"]["jobs"]["demo_job"]["last_ok"] is not None
    await job(False)
    assert (await _checks(client, h))["jobs"]["state"] == "ok"

    old = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    await get_redis().set(monitor.HEARTBEAT, old)
    worker = (await _checks(client, h))["worker"]
    assert worker["state"] == "error" and "10 min ago" in worker["detail"]


async def test_requests_are_counted(
    client: AsyncClient, model: ScriptedProvider, monkeypatch: pytest.MonkeyPatch, backups: Path
) -> None:
    h = await auth_headers(client)
    await client.get(f"{API}/tasks", headers=h)
    monkeypatch.setattr(get_settings(), "slow_request_ms", 0)
    await client.get(f"{API}/tasks", headers=h)
    req = (await _checks(client, h))["requests"]
    assert (
        req["errors"] == 0 and req["slow"] == 1 and req["total"] >= 4
    )  # sign-up, sign-in, 2 lists


async def test_backup_ages_and_failures(
    client: AsyncClient, model: ScriptedProvider, backups: Path
) -> None:
    h = await auth_headers(client)
    now = datetime.now(UTC)
    _manifest(backups, now - timedelta(hours=80))
    assert (await _checks(client, h))["backups"]["state"] == "error"  # over twice the limit
    _manifest(backups, now - timedelta(hours=50))
    assert (await _checks(client, h))["backups"]["state"] == "warn"
    folder = _manifest(backups, now - timedelta(hours=2), verified=True)
    b = (await _checks(client, h))["backups"]
    assert b["state"] == "ok" and b["last"] == folder.name
    assert "1.5 MB" in b["detail"] and "Restore drill passed" in b["detail"]

    (backups / "last-error.json").write_text(
        json.dumps({"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "error": "pg_dump failed"})
    )
    b = (await _checks(client, h))["backups"]
    assert b["state"] == "error" and "pg_dump failed" in b["detail"]


async def test_alerts_wait_for_a_second_failure_then_report_recovery(
    client: AsyncClient, model: ScriptedProvider, backups: Path
) -> None:
    await auth_headers(client)
    err = backups / "last-error.json"
    err.write_text(json.dumps({"at": datetime.now(UTC).isoformat(), "error": "disk full"}))

    async def tick() -> list[Notification]:
        async with get_sessionmaker()() as db:
            await monitor.alert_tick(db)
            await db.commit()
            rows = await db.scalars(select(Notification).order_by(Notification.created_at))
            return list(rows)

    assert await tick() == []  # one failed check is not enough
    (alert,) = await tick()
    assert alert.title == "NEXUS problem: Backups" and "disk full" in alert.body
    assert alert.link == "/settings/status"
    assert len(await tick()) == 1  # no repeat while it stays broken
    err.unlink()
    _manifest(backups, datetime.now(UTC))
    rows = await tick()
    assert [n.title for n in rows] == ["NEXUS problem: Backups", "Fixed: Backups"]
    assert len(await tick()) == 2


def _pg_env(database: str) -> dict[str, str]:
    url = make_url(get_settings().database_url)
    return {
        **os.environ,
        "PGHOST": url.host or "localhost",
        "PGPORT": str(url.port or 5432),
        "PGUSER": url.username or "",
        "PGPASSWORD": url.password or "",
        "PGDATABASE": database,
    }


def _pg_tools_ok() -> bool:
    if not (shutil.which("pg_dump") and shutil.which("bash")):
        return False
    out = subprocess.run(["pg_dump", "--version"], capture_output=True, text=True).stdout
    m = re.search(r"(\d+)\.", out)
    return bool(m and int(m.group(1)) >= 16)


@pytest.mark.skipif(not _pg_tools_ok(), reason="needs bash and pg_dump 16+")
async def test_backup_and_restore_drill(
    client: AsyncClient, model: ScriptedProvider, backups: Path, tmp_path_factory: Any
) -> None:
    """The real scripts: back up the test database, restore it into a scratch database,
    and check counts, schema and decryption. Then show the check catches a lost row and
    the wrong encryption key."""
    from app import cli

    h = await auth_headers(client)
    await _tx(client, h, description="Rent", amount="25000")
    await client.post(f"{API}/tasks", json={"title": "Back me up"}, headers=h)
    uploads = tmp_path_factory.mktemp("uploads")
    (uploads / "note.txt").write_text("hello")

    live = make_url(get_settings().database_url).database or ""
    env = {**_pg_env(live), "BACKUP_DIR": str(backups), "UPLOADS_DIR": str(uploads)}
    run = subprocess.run([str(INFRA / "backup.sh")], env=env, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    (folder,) = [p for p in backups.iterdir() if p.is_dir()]
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["counts"]["transactions"] == 1 and manifest["counts"]["tasks"] == 1
    assert not any(p.name.startswith(".partial") for p in backups.iterdir())

    check = f"{live}_restore"
    restore = subprocess.run(
        [str(INFRA / "restore.sh"), "latest", check], env=env, capture_output=True, text=True
    )
    assert restore.returncode == 0, restore.stderr
    try:
        report = await cli.restore_check(check)
        assert report["ok"], report
        assert report["decrypted_samples"] >= 1 and report["rows"] >= 3

        # the wrong key can't read the money
        settings = get_settings()
        good = settings.encryption_key
        from pydantic import SecretStr

        from app.db import encrypted

        object.__setattr__(settings, "encryption_key", SecretStr("A" * 43 + "="))
        encrypted._enc.cache_clear()
        try:
            bad = await cli.restore_check(check)
        finally:
            object.__setattr__(settings, "encryption_key", good)
            encrypted._enc.cache_clear()
        assert not bad["ok"] and any("NEXUS_ENCRYPTION_KEY" in p for p in bad["problems"])

        # a lost row is caught
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(make_url(settings.database_url).set(database=check))
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM tasks"))
        await engine.dispose()
        lost = await cli.restore_check(check)
        assert not lost["ok"] and lost["mismatched"] == {"tasks": {"backup": 1, "restored": 0}}

        # refusing to overwrite the live database without CONFIRM=yes
        live_restore = subprocess.run(
            [str(INFRA / "restore.sh"), "latest", live], env=env, capture_output=True, text=True
        )
        assert live_restore.returncode == 2 and "CONFIRM=yes" in live_restore.stderr

        # a damaged backup is refused
        with (folder / "db.dump").open("ab") as f:
            f.write(b"x")
        damaged = subprocess.run(
            [str(INFRA / "restore.sh"), "latest", check], env=env, capture_output=True, text=True
        )
        assert damaged.returncode == 3 and "damaged" in damaged.stderr
    finally:
        subprocess.run(["dropdb", "--if-exists", check], env=env, check=False)
