"""Device pairing for the Windows local agent, and the agent's WebSocket."""

import asyncio
import contextlib
import json
import uuid
from typing import Any

import jwt
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import DB, Auth, SettingsDep, client_ip
from app.api.routes.common import not_found
from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_sessionmaker
from app.models import Device, UserSession
from app.services import auth as auth_service
from app.services import devices as svc
from app.services import operator
from app.services.rate_limit import enforce_rate_limit
from app.services.redis import get_redis

router = APIRouter(tags=["devices"])


class TokenOut(BaseModel):
    device_id: uuid.UUID
    access_token: str
    refresh_token: str
    expires_in: int


@router.get("/devices")
async def list_devices(db: DB, auth: Auth) -> list[dict[str, Any]]:
    rows = list(
        await db.scalars(
            select(Device)
            .where(Device.user_id == auth.user.id, Device.revoked_at.is_(None))
            .order_by(Device.created_at)
        )
    )
    live = await svc.presence([d.id for d in rows])
    return [svc.device_out(d, live.get(d.id)) for d in rows]


@router.post("/devices/pair-code", status_code=201)
async def pair_code(auth: Auth) -> dict[str, Any]:
    minutes = get_settings().pair_code_minutes
    code, expires = await svc.create_pair_code(auth.user.id, minutes)
    return {"code": code, "expires_at": expires.isoformat()}


class PairIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    platform: str | None = Field(default=None, max_length=32)


def _auth_error(err: auth_service.AuthError) -> HTTPException:
    return HTTPException(err.status_code, detail={"code": err.code, "message": err.message})


@router.post("/devices/pair", response_model=TokenOut, status_code=201)
async def pair(body: PairIn, request: Request, db: DB, settings: SettingsDep) -> TokenOut:
    """Called by the local agent with a code the owner made in Settings > Devices."""
    ip = client_ip(request)
    await enforce_rate_limit(f"pair:{ip}", 10, 600)
    try:
        device, tokens = await svc.pair(
            db, settings, code=body.code, name=body.name.strip(), platform=body.platform, ip=ip
        )
    except svc.PairError as exc:
        raise HTTPException(400, detail={"code": "bad_code", "message": str(exc)}) from None
    return TokenOut(
        device_id=device.id,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: uuid.UUID
    refresh_token: str = Field(min_length=10, max_length=200)


@router.post("/devices/token", response_model=TokenOut)
async def device_token(
    body: RefreshIn, request: Request, db: DB, settings: SettingsDep
) -> TokenOut:
    ip = client_ip(request)
    await enforce_rate_limit(f"devtoken:{ip}", 60, 600)
    try:
        tokens = await svc.refresh(
            db, settings, device_id=body.device_id, refresh_token=body.refresh_token, ip=ip
        )
    except auth_service.AuthError as exc:
        raise _auth_error(exc) from None
    return TokenOut(
        device_id=body.device_id,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


async def _owned(db: DB, auth: Auth, device_id: uuid.UUID) -> Device:
    device = await db.get(Device, device_id)
    if device is None or device.user_id != auth.user.id or device.revoked_at is not None:
        not_found("Device not found.")
    return device


class DevicePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    wake_word: bool | None = None
    hands_free: bool | None = None


@router.patch("/devices/{device_id}")
async def update_device(
    device_id: uuid.UUID, body: DevicePatch, db: DB, auth: Auth
) -> dict[str, Any]:
    device = await _owned(db, auth, device_id)
    if body.name is not None:
        device.name = body.name.strip()
    changes = body.model_dump(exclude_none=True, exclude={"name"})
    if changes:
        device.settings = {**svc.DEFAULT_SETTINGS, **device.settings, **changes}
    await db.commit()
    await svc.publish(device.id, svc.settings_message(device))
    live = await svc.presence([device.id])
    return svc.device_out(device, live.get(device.id))


@router.post("/devices/{device_id}/stop")
async def stop_device(device_id: uuid.UUID, db: DB, auth: Auth) -> dict[str, Any]:
    """Kill switch: the agent stops listening at once and hands-free is turned off."""
    device = await _owned(db, auth, device_id)
    device.settings = {**svc.DEFAULT_SETTINGS, **device.settings, "hands_free": False}
    await db.commit()
    await svc.publish(device.id, {"type": "stop"})
    await svc.publish(device.id, svc.settings_message(device))
    live = await svc.presence([device.id])
    return svc.device_out(device, live.get(device.id))


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_device(device_id: uuid.UUID, request: Request, db: DB, auth: Auth) -> None:
    device = await _owned(db, auth, device_id)
    await svc.revoke(db, device, ip=client_ip(request))


# --- agent WebSocket ---------------------------------------------------------------


async def _ws_device(websocket: WebSocket) -> uuid.UUID | None:
    header = websocket.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        payload = decode_access_token(
            header[7:].strip(), get_settings().jwt_secret.get_secret_value()
        )
        session_id = uuid.UUID(payload["sid"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None
    async with get_sessionmaker()() as db:
        session = await db.get(UserSession, session_id)
        if session is None or session.revoked_at is not None:
            return None
        device = await svc.device_for_session(db, session_id)
        return device.id if device else None


async def _handle(device_id: uuid.UUID, msg: dict[str, Any]) -> None:
    kind = msg.get("type")
    if kind == "result":
        await operator.deliver_result(device_id, str(msg.get("id", "")), msg)
        return
    if kind == "hello":
        caps = msg.get("capabilities")
        async with get_sessionmaker()() as db:
            device = await db.get(Device, device_id)
            if device is not None and isinstance(caps, dict):
                device.capabilities = {
                    str(k)[:40]: bool(v) if isinstance(v, bool) else str(v)[:80]
                    for k, v in list(caps.items())[:20]
                }
                device.last_seen_at = svc._now()
                await db.commit()
    mic = msg.get("mic")
    await svc.set_presence(device_id, {"mic": mic if mic in svc.MIC_STATES else "off"})


@router.websocket("/devices/ws")
async def device_socket(websocket: WebSocket) -> None:
    device_id = await _ws_device(websocket)
    if device_id is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    async with get_sessionmaker()() as db:
        device = await db.get(Device, device_id)
        assert device is not None
        await websocket.send_json(svc.settings_message(device))
        policy = await operator.get_policy(db, device.user_id)
        await websocket.send_json({"type": "policy", "policy": policy.model_dump()})
    await svc.set_presence(device_id, {"mic": "off"})
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(svc.channel(device_id))

    async def forward() -> None:
        async for item in pubsub.listen():
            if item.get("type") != "message":
                continue
            msg = json.loads(item["data"])
            await websocket.send_json(msg)
            if msg.get("type") == "revoked":
                await websocket.close(code=4403)
                return

    forwarder = asyncio.create_task(forward())
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if isinstance(msg, dict):
                await _handle(device_id, msg)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        forwarder.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await forwarder
        await pubsub.unsubscribe(svc.channel(device_id))
        await pubsub.aclose()  # type: ignore[no-untyped-call]
        await svc.clear_presence(device_id)
