"""System status and alerts.

`status()` checks each part NEXUS depends on and says, in plain words, what is wrong. The
worker records a heartbeat and the outcome of every scheduled job in Redis; the API
counts slow and failed requests per hour. `alert_tick()` (worker, every five minutes)
notifies the owner when a check has failed twice in a row, and again when it recovers,
so a brief blip never pages anyone. Nothing here is estimated: a check with nothing to
measure says so."""

from __future__ import annotations

import functools
import json
import shutil
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, ParamSpec, TypeVar

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import get_gateway
from app.core.config import get_settings
from app.core.logging import log
from app.models import AutomationRun, ConnectedAccount, ModelUsageLog, User
from app.services import notify
from app.services.redis import get_redis

State = Literal["ok", "warn", "error", "off"]
HEARTBEAT = "nexus:worker:heartbeat"
JOBS = "nexus:jobs"
WORKER_STALE = timedelta(minutes=3)
ALERT_KEY = "nexus:alerts:{user}"
CONFIRM_TICKS = 2  # a check must fail this many ticks in a row before an alert

P = ParamSpec("P")
R = TypeVar("R")


def _now() -> datetime:
    return datetime.now(UTC)


# --- recording ------------------------------------------------------------------------


async def heartbeat() -> None:
    await get_redis().set(HEARTBEAT, _now().isoformat())


def tracked(name: str) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Wrap a scheduled job so its last run, outcome and error are kept in Redis."""

    def wrap(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(fn)
        async def run(*args: P.args, **kwargs: P.kwargs) -> R:
            started = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
            except Exception as exc:
                await _record(name, ok=False, error=f"{type(exc).__name__}: {exc}"[:300], ms=0)
                raise
            await _record(name, ok=True, error=None, ms=int((time.perf_counter() - started) * 1000))
            return result

        return run

    return wrap


async def _record(name: str, *, ok: bool, error: str | None, ms: int) -> None:
    try:
        r = get_redis()
        raw = await r.hget(JOBS, name)  # type: ignore[misc]
        prev = json.loads(raw) if raw else {}
        now = _now().isoformat()
        entry = {
            "last_run": now,
            "last_ok": now if ok else prev.get("last_ok"),
            "error": None if ok else error,
            "failures": 0 if ok else int(prev.get("failures", 0)) + 1,
            "ms": ms,
        }
        await r.hset(JOBS, name, json.dumps(entry))  # type: ignore[misc]
    except Exception:  # monitoring must never break the job it watches
        log.warning("job_record_failed", job=name)


def _hour_key(at: datetime | None = None) -> str:
    return f"nexus:req:{(at or _now()):%Y%m%d%H}"


async def note_request(status_code: int, ms: float) -> None:
    try:
        r = get_redis()
        key = _hour_key()
        pipe = r.pipeline()
        pipe.hincrby(key, "total", 1)
        if status_code >= 500:
            pipe.hincrby(key, "errors", 1)
        if ms >= get_settings().slow_request_ms:
            pipe.hincrby(key, "slow", 1)
        pipe.expire(key, 60 * 60 * 26)
        await pipe.execute()
    except Exception:  # noqa: S110 - counting is best effort
        pass


# --- checks ---------------------------------------------------------------------------


def _check(key: str, label: str, state: State, detail: str, **extra: Any) -> dict[str, Any]:
    return {"key": key, "label": label, "state": state, "detail": detail, **extra}


def _ago(then: datetime, now: datetime) -> str:
    mins = int((now - then).total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 90:
        return f"{mins} min ago"
    hours = mins // 60
    return f"{hours} h ago" if hours < 48 else f"{hours // 24} days ago"


async def _database(db: AsyncSession) -> dict[str, Any]:
    t = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        return _check("database", "Database", "error", f"Not answering ({type(exc).__name__}).")
    ms = round((time.perf_counter() - t) * 1000, 1)
    state: State = "ok" if ms < 200 else "warn"
    return _check("database", "Database", state, f"Answering in {ms} ms.", ms=ms)


async def _worker(now: datetime) -> list[dict[str, Any]]:
    r = get_redis()
    raw = await r.get(HEARTBEAT)
    out = []
    if raw is None:
        out.append(
            _check(
                "worker",
                "Background worker",
                "error",
                "Never seen. Schedules, syncs, briefings and automations aren't running. "
                "Start it with docker compose up -d worker.",
            )
        )
    else:
        seen = datetime.fromisoformat(raw if isinstance(raw, str) else raw.decode())
        stale = now - seen > WORKER_STALE
        out.append(
            _check(
                "worker",
                "Background worker",
                "error" if stale else "ok",
                f"Last seen {_ago(seen, now)}."
                + (" Schedules, syncs and automations are paused." if stale else ""),
                last_seen=seen.isoformat(),
            )
        )
    jobs = await r.hgetall(JOBS)  # type: ignore[misc]
    failing = []
    for name, value in sorted(jobs.items()):
        name = name if isinstance(name, str) else name.decode()
        entry = json.loads(value)
        if entry.get("error"):
            failing.append(f"{name}: {entry['error']}")
    out.append(
        _check(
            "jobs",
            "Scheduled jobs",
            "off" if not jobs else ("warn" if failing else "ok"),
            "No job has run yet."
            if not jobs
            else ("; ".join(failing)[:400] if failing else f"All {len(jobs)} jobs last ran fine."),
            jobs={
                (k if isinstance(k, str) else k.decode()): json.loads(v) for k, v in jobs.items()
            },
        )
    )
    return out


async def _model(db: AsyncSession, user_id: uuid.UUID, now: datetime) -> dict[str, Any]:
    gw = get_gateway()
    st = await gw.status()
    local = st["local"]
    hour = now - timedelta(hours=1)
    rows = (
        await db.execute(
            select(ModelUsageLog.status, func.count())
            .where(ModelUsageLog.user_id == user_id, ModelUsageLog.at >= hour)
            .group_by(ModelUsageLog.status)
        )
    ).all()
    counts = {s: n for s, n in rows}
    errors, total = counts.get("error", 0), sum(counts.values())
    if not local["enabled"]:
        return _check("model", "Local AI model", "off", "Turned off in settings.")
    if not local["reachable"]:
        return _check(
            "model",
            "Local AI model",
            "error",
            f"Can't reach {local['base_url']}. Start Ollama or LM Studio on your PC.",
        )
    state: State = "warn" if total and errors / total > 0.2 else "ok"
    detail = f"{local['models']['chat']} is answering."
    if total:
        detail += f" {errors} of {total} calls failed in the last hour."
    return _check("model", "Local AI model", state, detail, calls=total, errors=errors)


async def _integrations(db: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    accounts = list(
        await db.scalars(select(ConnectedAccount).where(ConnectedAccount.user_id == user_id))
    )
    if not accounts:
        return _check("sync", "Email and calendar sync", "off", "Nothing connected.")
    broken = [a for a in accounts if a.status != "connected" or a.last_error]
    if broken:
        a = broken[0]
        return _check(
            "sync",
            "Email and calendar sync",
            "error",
            f"{a.account_email}: {a.last_error or a.status}. Reconnect it in Settings.",
        )
    synced = [a.last_sync_at for a in accounts if a.last_sync_at]
    stale_after = timedelta(minutes=max(30, get_settings().sync_interval_minutes * 3))
    if synced and _now() - max(synced) > stale_after:
        return _check(
            "sync", "Email and calendar sync", "warn", f"Last synced {_ago(max(synced), _now())}."
        )
    return _check(
        "sync",
        "Email and calendar sync",
        "ok",
        f"Last synced {_ago(max(synced), _now())}." if synced else "Connected, not synced yet.",
    )


async def _automations(db: AsyncSession, user_id: uuid.UUID, now: datetime) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(AutomationRun.status, func.count())
            .where(
                AutomationRun.user_id == user_id,
                AutomationRun.started_at >= now - timedelta(days=1),
            )
            .group_by(AutomationRun.status)
        )
    ).all()
    counts = {s: n for s, n in rows}
    failed, total = counts.get("failed", 0), sum(counts.values())
    if not total:
        return _check("automations", "Automations", "off", "No runs in the last 24 hours.")
    return _check(
        "automations",
        "Automations",
        "warn" if failed else "ok",
        f"{failed} of {total} runs failed in the last 24 hours."
        if failed
        else f"All {total} runs in the last 24 hours finished.",
    )


def latest_backup() -> dict[str, Any] | None:
    """The newest finished backup's manifest, plus when the restore drill last passed."""
    root = Path(get_settings().backup_dir)
    if not root.is_dir():
        return None
    for m in sorted(root.glob("2*/manifest.json"), reverse=True):
        try:
            data: dict[str, Any] = json.loads(m.read_text())
            data["created_at"] = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        except (OSError, ValueError, KeyError):
            continue
        data["name"] = m.parent.name
        try:
            verified = json.loads((m.parent / "verified.json").read_text())["verified_at"]
            data["verified_at"] = datetime.fromisoformat(verified.replace("Z", "+00:00"))
        except (OSError, ValueError, KeyError):
            data["verified_at"] = None
        return data
    return None


def _backup_error() -> dict[str, Any] | None:
    try:
        data: dict[str, Any] = json.loads(
            (Path(get_settings().backup_dir) / "last-error.json").read_text()
        )
        data["at"] = datetime.fromisoformat(data["at"].replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError):
        return None
    return data


def _backups(now: datetime) -> dict[str, Any]:
    b, err = latest_backup(), _backup_error()
    if err is not None and (b is None or err["at"] > b["created_at"]):
        return _check(
            "backups",
            "Backups",
            "error",
            f"The last backup failed {_ago(err['at'], now)}: {err.get('error', 'unknown error')}. "
            "See docker compose logs backup.",
        )
    if b is None:
        return _check(
            "backups",
            "Backups",
            "warn",
            "No backups yet. Start the backup service: docker compose up -d backup.",
        )
    at = b["created_at"]
    limit = timedelta(hours=get_settings().backup_max_age_hours)
    age = now - at
    state: State = "ok" if age <= limit else ("warn" if age <= limit * 2 else "error")
    detail = f"Last backup {_ago(at, now)} ({b.get('size_mb', '?')} MB)."
    verified = b["verified_at"]
    detail += (
        f" Restore drill passed {_ago(verified, now)}."
        if verified
        else " Not restore-tested yet: run scripts/restore-drill.sh."
    )
    return _check(
        "backups",
        "Backups",
        state,
        detail,
        last=b["name"],
        verified_at=verified.isoformat() if verified else None,
    )


def _disk() -> dict[str, Any]:
    path = Path(get_settings().storage_dir)
    target = path if path.exists() else Path.cwd()
    usage = shutil.disk_usage(target)
    free_pct = round(100 * usage.free / usage.total, 1)
    state: State = "ok" if free_pct >= 10 else ("warn" if free_pct >= 5 else "error")
    return _check(
        "disk",
        "Disk space",
        state,
        f"{usage.free / 1e9:.1f} GB free ({free_pct}%).",
        free_pct=free_pct,
    )


async def _requests(now: datetime) -> dict[str, Any]:
    r = get_redis()
    total = errors = slow = 0
    for h in range(24):
        data = await r.hgetall(_hour_key(now - timedelta(hours=h)))  # type: ignore[misc]
        vals = {(k if isinstance(k, str) else k.decode()): int(v) for k, v in data.items()}
        total += vals.get("total", 0)
        errors += vals.get("errors", 0)
        slow += vals.get("slow", 0)
    if not total:
        return _check("requests", "App responses", "off", "No requests counted yet.")
    state: State = "warn" if errors / total > 0.01 or slow / total > 0.05 else "ok"
    return _check(
        "requests",
        "App responses",
        state,
        f"{total} requests in 24 h: {errors} server errors, {slow} slower than "
        f"{get_settings().slow_request_ms / 1000:g} s.",
        total=total,
        errors=errors,
        slow=slow,
    )


async def status(db: AsyncSession, user: User) -> dict[str, Any]:
    now = _now()
    checks = [await _database(db)]
    try:
        checks += await _worker(now)
        checks.append(await _requests(now))
        redis_ok = True
    except Exception:
        redis_ok = False
        checks.append(
            _check("redis", "Redis", "error", "Not answering. Queues and limits are down.")
        )
    checks += [
        await _model(db, user.id, now),
        await _integrations(db, user.id),
        await _automations(db, user.id, now),
        _backups(now),
        _disk(),
    ]
    if redis_ok:
        checks.insert(1, _check("redis", "Redis", "ok", "Answering."))
    states = {c["state"] for c in checks}
    overall: State = "error" if "error" in states else ("warn" if "warn" in states else "ok")
    return {"overall": overall, "checked_at": now.isoformat(), "checks": checks}


# --- alerts ---------------------------------------------------------------------------


async def alert_tick(db: AsyncSession) -> int:
    """Notify the owner about checks that failed twice in a row, and about recoveries."""
    sent = 0
    r = get_redis()
    for user in list(await db.scalars(select(User).where(User.is_active.is_(True)))):
        report = await status(db, user)
        key = ALERT_KEY.format(user=user.id)
        raw = await r.get(key)
        memory: dict[str, Any] = json.loads(raw) if raw else {}
        for c in report["checks"]:
            if c["key"] == "worker":
                continue  # the worker is running this; the web banner covers it
            prev = memory.get(c["key"], {"streak": 0, "alerted": False})
            failing = c["state"] == "error"
            streak = prev["streak"] + 1 if failing else 0
            alerted = prev["alerted"]
            if failing and streak >= CONFIRM_TICKS and not alerted:
                await notify.notify(
                    db,
                    user.id,
                    kind="system",
                    title=f"NEXUS problem: {c['label']}",
                    body=c["detail"][:300],
                    link="/settings/status",
                )
                alerted, sent = True, sent + 1
            elif not failing and alerted:
                await notify.notify(
                    db,
                    user.id,
                    kind="system",
                    title=f"Fixed: {c['label']}",
                    body=c["detail"][:300],
                    link="/settings/status",
                    send_push=False,
                )
                alerted, sent = False, sent + 1
            memory[c["key"]] = {"streak": streak, "alerted": alerted}
        await r.set(key, json.dumps(memory), ex=60 * 60 * 24 * 7)
    return sent
