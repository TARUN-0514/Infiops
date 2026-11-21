"""Paired devices (the Windows local agent): pairing codes, their own sessions, live presence
and settings pushed over the device WebSocket."""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Device, User, UserSession
from app.services import audit
from app.services import auth as auth_service
from app.services.redis import get_redis

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
PRESENCE_TTL = 45  # seconds; the agent sends a heartbeat every 15
DEFAULT_SETTINGS: dict[str, Any] = {"wake_word": False, "hands_free": False}
MIC_STATES = {"off", "wake", "listening", "thinking", "speaking"}


def _now() -> datetime:
    return datetime.now(UTC)


def normalise_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch in CODE_ALPHABET)


async def create_pair_code(user_id: uuid.UUID, minutes: int) -> tuple[str, datetime]:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    await get_redis().set(f"pair:{raw}", str(user_id), ex=minutes * 60)
    return f"{raw[:4]}-{raw[4:]}", _now() + timedelta(minutes=minutes)


class PairError(Exception):
    pass


async def pair(
    db: AsyncSession,
    settings: Settings,
    *,
    code: str,
    name: str,
    platform: str | None,
    ip: str | None,
) -> tuple[Device, auth_service.IssuedTokens]:
    user_id = await get_redis().getdel(f"pair:{normalise_code(code)}")
    if not user_id:
        raise PairError("That pairing code is wrong or has expired. Make a new one in Settings.")
    user = await db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise PairError("That pairing code is wrong or has expired.")
    tokens = await auth_service.issue_session(
        db, settings, user, user_agent=f"NEXUS local agent ({name})", ip=ip
    )
    device = Device(
        user_id=user.id,
        kind="desktop",
        name=name,
        platform=platform,
        capabilities={},
        settings=dict(DEFAULT_SETTINGS),
        session_id=tokens.session.id,
        last_seen_at=_now(),
    )
    db.add(device)
    await db.flush()
    audit.record(db, "device.paired", user_id=user.id, ip=ip, device_id=str(device.id), name=name)
    await db.commit()
    return device, tokens


async def refresh(
    db: AsyncSession,
    settings: Settings,
    *,
    device_id: uuid.UUID,
    refresh_token: str,
    ip: str | None,
) -> auth_service.IssuedTokens:
    device = await db.get(Device, device_id)
    if device is None or device.revoked_at is not None or device.session_id is None:
        raise auth_service.AuthError("device_revoked", "This device was removed. Pair it again.")
    tokens, _ = await auth_service.refresh(db, settings, refresh_token=refresh_token, ip=ip)
    if tokens.session.id != device.session_id:
        raise auth_service.AuthError("invalid_refresh", "Pair this device again.")
    device = await db.get(Device, device_id)
    assert device is not None
    device.last_seen_at = _now()
    await db.commit()
    return tokens


async def device_for_session(db: AsyncSession, session_id: uuid.UUID) -> Device | None:
    return await db.scalar(
        select(Device).where(Device.session_id == session_id, Device.revoked_at.is_(None))
    )


async def revoke(db: AsyncSession, device: Device, *, ip: str | None) -> None:
    device.revoked_at = _now()
    if device.session_id is not None:
        session = await db.get(UserSession, device.session_id)
        if session is not None:
            await auth_service.revoke_session(db, session, "device_removed", ip=ip)
    audit.record(db, "device.removed", user_id=device.user_id, ip=ip, device_id=str(device.id))
    await db.commit()
    await publish(device.id, {"type": "revoked"})
    await get_redis().delete(_presence_key(device.id))


# --- presence and messages ------------------------------------------------------------


def _presence_key(device_id: uuid.UUID) -> str:
    return f"device:presence:{device_id}"


def channel(device_id: uuid.UUID) -> str:
    return f"device:{device_id}"


async def set_presence(device_id: uuid.UUID, state: dict[str, Any]) -> None:
    await get_redis().set(
        _presence_key(device_id),
        json.dumps({**state, "at": _now().isoformat()}),
        ex=PRESENCE_TTL,
    )


async def clear_presence(device_id: uuid.UUID) -> None:
    await get_redis().delete(_presence_key(device_id))


async def presence(ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    if not ids:
        return {}
    values = await get_redis().mget([_presence_key(i) for i in ids])
    return {i: json.loads(v) for i, v in zip(ids, values, strict=True) if v}


async def publish(device_id: uuid.UUID, message: dict[str, Any]) -> None:
    await get_redis().publish(channel(device_id), json.dumps(message))


def settings_message(device: Device) -> dict[str, Any]:
    return {"type": "settings", "settings": {**DEFAULT_SETTINGS, **device.settings}}


def device_out(device: Device, live: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": str(device.id),
        "name": device.name,
        "kind": device.kind,
        "platform": device.platform,
        "settings": {**DEFAULT_SETTINGS, **device.settings},
        "capabilities": device.capabilities,
        "online": live is not None,
        "mic": (live or {}).get("mic", "off"),
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        "created_at": device.created_at.isoformat(),
    }
