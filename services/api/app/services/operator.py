"""Operator: what NEXUS may do on the owner's PC, and the call path to the local agent.

The owner's policy (allowed apps and folders, browser, screen control, pause) is checked here
before a call is sent, and again by the agent on the PC before it acts."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import PurePath, PurePosixPath, PureWindowsPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, UserPreferences
from app.services import devices as dev
from app.services.redis import get_redis

CALL_TIMEOUT = 45.0
LONG_CALL_TIMEOUT = 900.0  # Claude Code runs


class PolicyError(ValueError):
    """Computer control is off, paused, or this kind of action isn't allowed."""


class AllowedApp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    command: str = Field(min_length=1, max_length=400)


class AllowedFolder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=2, max_length=400)
    write: bool = False

    @field_validator("path")
    @classmethod
    def absolute(cls, v: str) -> str:
        p = _pure(v.strip())
        if not p.is_absolute() or ".." in p.parts:
            raise ValueError("Use a full folder path, like C:\\Users\\you\\Documents\\NEXUS.")
        return str(p)


class OperatorPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    apps: list[AllowedApp] = Field(default_factory=list, max_length=40)
    folders: list[AllowedFolder] = Field(default_factory=list, max_length=20)
    browser: bool = False
    screen: bool = False  # computer use: screenshots go to Claude, so off by default
    claude_code: bool = False
    paused: bool = False  # kill switch


def _pure(path: str) -> PurePath:
    if re.match(r"^[A-Za-z]:[\\/]", path) or "\\" in path:
        return PureWindowsPath(path)
    return PurePosixPath(path)


async def get_policy(db: AsyncSession, user_id: uuid.UUID) -> OperatorPolicy:
    # Always re-read: a long run must see the kill switch pressed from another request.
    prefs = await db.get(UserPreferences, user_id, populate_existing=True)
    raw = (prefs.settings if prefs else {}).get("operator", {})
    return OperatorPolicy.model_validate(raw)


async def save_policy(db: AsyncSession, user_id: uuid.UUID, policy: OperatorPolicy) -> None:
    prefs = await db.get(UserPreferences, user_id)
    if prefs is None:
        prefs = UserPreferences(user_id=user_id, settings={})
        db.add(prefs)
    prefs.settings = {**(prefs.settings or {}), "operator": policy.model_dump()}
    await db.commit()
    for device in await _devices(db, user_id):
        await dev.publish(device.id, {"type": "policy", "policy": policy.model_dump()})


def folder_for(policy: OperatorPolicy, path: str, *, write: bool) -> AllowedFolder:
    """The allowed folder that contains path, or ValueError. Lexical check; the agent also
    resolves links on the PC before acting."""
    target = _pure(path.strip())
    if not target.is_absolute() or ".." in target.parts:
        raise ValueError("Use a full path inside an allowed folder.")
    for folder in policy.folders:
        root = _pure(folder.path)
        if type(root) is not type(target):
            continue
        if _parts(target)[: len(root.parts)] == _parts(root):
            if write and not folder.write:
                raise ValueError(
                    f"{folder.path} is read-only for NEXUS. Allow writing in Settings."
                )
            return folder
    raise ValueError(
        "That path isn't in a folder you've allowed. Add it in Settings > Computer control."
    )


def _parts(p: PurePath) -> list[str]:
    # Windows paths are case-insensitive.
    return [s.lower() for s in p.parts] if isinstance(p, PureWindowsPath) else list(p.parts)


def app_for(policy: OperatorPolicy, name: str) -> AllowedApp:
    for app in policy.apps:
        if app.name.lower() == name.strip().lower():
            return app
    allowed = ", ".join(a.name for a in policy.apps) or "none yet"
    raise ValueError(f"'{name}' isn't an allowed app. Allowed: {allowed}.")


async def _devices(db: AsyncSession, user_id: uuid.UUID) -> list[Device]:
    return list(
        await db.scalars(
            select(Device).where(Device.user_id == user_id, Device.revoked_at.is_(None))
        )
    )


async def require(db: AsyncSession, user_id: uuid.UUID, what: str | None = None) -> OperatorPolicy:
    policy = await get_policy(db, user_id)
    if not policy.enabled:
        raise PolicyError("Computer control is off. Turn it on in Settings > Computer control.")
    if policy.paused:
        raise PolicyError("Computer control is paused (kill switch). Resume it in Settings.")
    if what == "browser" and not policy.browser:
        raise PolicyError("Browser control is off. Turn it on in Settings > Computer control.")
    if what == "screen" and not policy.screen:
        raise PolicyError("Screen control is off. Turn it on in Settings > Computer control.")
    if what == "claude_code" and not policy.claude_code:
        raise PolicyError("Claude Code runs are off. Turn them on in Settings > Computer control.")
    return policy


async def online_device(db: AsyncSession, user_id: uuid.UUID) -> Device:
    devices = await _devices(db, user_id)
    live = await dev.presence([d.id for d in devices])
    ready = [d for d in devices if d.id in live and d.capabilities.get("operator")]
    if not ready:
        raise LookupError(
            "Your PC isn't connected. Start the NEXUS app or run `nexus-agent run`, then try again."
        )
    return max(ready, key=lambda d: live[d.id].get("at", ""))


async def call(
    device: Device, tool: str, args: dict[str, Any], wait: float = CALL_TIMEOUT
) -> dict[str, Any]:
    """Asks the agent on the PC to run one action and waits for its answer."""
    call_id = uuid.uuid4().hex
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(f"devcall:{device.id}:{call_id}")
    try:
        await dev.publish(device.id, {"type": "call", "id": call_id, "tool": tool, "input": args})
        deadline = asyncio.get_running_loop().time() + wait
        while (left := deadline - asyncio.get_running_loop().time()) > 0:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=min(left, 5))
            if msg and msg.get("type") == "message":
                result: dict[str, Any] = json.loads(msg["data"])
                if not result.get("ok"):
                    raise ValueError(str(result.get("error") or "The PC refused that action."))
                out = result.get("output")
                return out if isinstance(out, dict) else {"result": out}
        raise TimeoutError
    except TimeoutError:
        raise ValueError(f"Your PC didn't answer within {int(wait)} seconds.") from None
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()  # type: ignore[no-untyped-call]


async def deliver_result(device_id: uuid.UUID, call_id: str, payload: dict[str, Any]) -> None:
    """A device can only answer calls that were sent to it."""
    if re.fullmatch(r"[0-9a-f]{32}", call_id):
        channel = f"devcall:{device_id}:{call_id}"
        await get_redis().publish(channel, json.dumps(payload, default=str))


async def stop_all(db: AsyncSession, user_id: uuid.UUID) -> OperatorPolicy:
    """Kill switch: pause computer control and tell every PC to stop at once."""
    policy = await get_policy(db, user_id)
    policy.paused = True
    await save_policy(db, user_id, policy)
    for device in await _devices(db, user_id):
        await dev.publish(device.id, {"type": "stop", "at": datetime.now(UTC).isoformat()})
    return policy
