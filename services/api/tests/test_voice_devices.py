import json
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.ai.providers import ScriptedProvider
from app.api.routes import devices as device_routes
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.session import get_sessionmaker
from app.models import AuditLog, Device, UserSession
from app.services import devices as dev
from app.services import voice
from app.services.redis import get_redis
from tests.conftest import auth_headers

API = "/api/v1"


class FakeVoice:
    """The local voice server, in memory."""

    def __init__(self) -> None:
        self.down = False
        self.stt_calls: list[dict[str, Any]] = []
        self.tts_calls: list[dict[str, Any]] = []
        self.transcript = "What's on my calendar today?"

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("refused")
        if request.url.path.endswith("/transcriptions"):
            body = request.content
            self.stt_calls.append({"size": len(body), "has_language": b'name="language"' in body})
            return httpx.Response(200, json={"text": f" [BLANK_AUDIO] {self.transcript} "})
        if request.url.path.endswith("/speech"):
            payload = json.loads(request.content)
            self.tts_calls.append(payload)
            return httpx.Response(
                200, content=b"RIFF....WAVE", headers={"content-type": "audio/wav"}
            )
        return httpx.Response(404)


@pytest.fixture
def fake_voice() -> Iterator[FakeVoice]:
    fake = FakeVoice()
    voice.set_transport(httpx.MockTransport(fake.handler))
    yield fake
    voice.set_transport(None)


# --- voice ---------------------------------------------------------------------------


async def test_transcribe_and_speak(client: AsyncClient, fake_voice: FakeVoice) -> None:
    h = await auth_headers(client)
    r = await client.post(
        f"{API}/voice/transcribe",
        files={"file": ("speech.wav", b"RIFF" + b"\x00" * 3000, "audio/wav")},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "What's on my calendar today?"  # noise markers removed
    assert fake_voice.stt_calls[0]["has_language"]

    r = await client.post(
        f"{API}/voice/speak",
        json={"text": "**You have** two meetings [1]. See https://example.com"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav" and r.content.startswith(b"RIFF")
    assert fake_voice.tts_calls[0]["input"] == "You have two meetings. See a link"
    assert fake_voice.tts_calls[0]["voice"] == get_settings().tts_voice


async def test_voice_errors_are_honest(client: AsyncClient, fake_voice: FakeVoice) -> None:
    h = await auth_headers(client)
    r = await client.post(
        f"{API}/voice/transcribe", files={"file": ("a.txt", b"hello", "text/plain")}, headers=h
    )
    assert r.status_code == 415
    fake_voice.down = True
    r = await client.post(
        f"{API}/voice/transcribe", files={"file": ("a.wav", b"RIFF", "audio/wav")}, headers=h
    )
    assert r.status_code == 503
    assert "voice server" in r.json()["error"]["message"]
    status = (await client.get(f"{API}/voice/status", headers=h)).json()
    assert status["stt"]["ready"] is False and status["tts"]["ready"] is False
    assert status["stt"]["error"]
    fake_voice.down = False
    status = (await client.get(f"{API}/voice/status", headers=h)).json()
    assert status["stt"]["ready"] and status["tts"]["ready"]
    r = await client.post(f"{API}/voice/speak", json={"text": "```code```"}, headers=h)
    assert r.status_code == 400
    assert (await client.post(f"{API}/voice/speak", json={"text": "hi"})).status_code == 401


async def test_spoken_turn_asks_for_short_plain_reply(
    client: AsyncClient, model: ScriptedProvider
) -> None:
    h = await auth_headers(client)
    cid = (await client.post(f"{API}/chat/conversations", headers=h)).json()["id"]
    model.push("You have two meetings today.")
    long_plan = "Plan a step-by-step roadmap for my week"
    r = await client.post(
        f"{API}/chat/conversations/{cid}/messages",
        json={"text": long_plan, "voice": True},
        headers=h,
    )
    events = [json.loads(line) for line in r.text.splitlines() if line]
    assert events[-1]["type"] == "run.finished"
    req = model.requests[0]
    system = " ".join(b["text"] for b in req.system)
    assert "This turn is spoken" in system and "/no_think" in system
    assert req.effort == "low"
    assert events[0]["job"] == "chat"  # voice never routes to the slow planning model


# --- devices ---------------------------------------------------------------------------


async def _pair(client: AsyncClient, h: dict[str, str]) -> dict[str, Any]:
    code = (await client.post(f"{API}/devices/pair-code", headers=h)).json()["code"]
    r = await client.post(
        f"{API}/devices/pair",
        json={"code": code.lower(), "name": "Tarun's PC", "platform": "windows"},
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def test_pairing_gives_the_agent_its_own_session(client: AsyncClient) -> None:
    h = await auth_headers(client)
    tokens = await _pair(client, h)
    agent = {"Authorization": f"Bearer {tokens['access_token']}"}
    # The agent can use the normal API with its own token.
    assert (await client.get(f"{API}/auth/me", headers=agent)).status_code == 200
    devices = (await client.get(f"{API}/devices", headers=h)).json()
    assert len(devices) == 1
    d = devices[0]
    assert d["name"] == "Tarun's PC" and d["online"] is False and d["mic"] == "off"
    assert d["settings"] == {"wake_word": False, "hands_free": False}
    sessions = (await client.get(f"{API}/auth/sessions", headers=h)).json()
    assert any("local agent" in (s.get("user_agent") or "") for s in sessions)

    # A code works once.
    code = (await client.post(f"{API}/devices/pair-code", headers=h)).json()["code"]
    ok = await client.post(f"{API}/devices/pair", json={"code": code, "name": "A"})
    again = await client.post(f"{API}/devices/pair", json={"code": code, "name": "B"})
    assert ok.status_code == 201 and again.status_code == 400
    assert "expired" in again.json()["error"]["message"]


async def test_device_token_rotates_and_reuse_ends_it(client: AsyncClient) -> None:
    h = await auth_headers(client)
    t = await _pair(client, h)
    r = await client.post(
        f"{API}/devices/token",
        json={"device_id": t["device_id"], "refresh_token": t["refresh_token"]},
    )
    assert r.status_code == 200
    new = r.json()
    assert new["refresh_token"] != t["refresh_token"]
    # Reusing the old token is treated as theft: the session ends.
    r = await client.post(
        f"{API}/devices/token",
        json={"device_id": t["device_id"], "refresh_token": t["refresh_token"]},
    )
    assert r.status_code == 401
    r = await client.post(
        f"{API}/devices/token",
        json={"device_id": t["device_id"], "refresh_token": new["refresh_token"]},
    )
    assert r.status_code == 401


async def test_settings_stop_and_remove(client: AsyncClient) -> None:
    h = await auth_headers(client)
    t = await _pair(client, h)
    did = t["device_id"]
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(dev.channel(uuid.UUID(did)))
    await pubsub.get_message(timeout=5)  # subscribe confirmation

    r = await client.patch(f"{API}/devices/{did}", json={"wake_word": True}, headers=h)
    assert r.json()["settings"] == {"wake_word": True, "hands_free": False}
    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5)
    assert msg and json.loads(msg["data"])["settings"]["wake_word"] is True

    await client.patch(f"{API}/devices/{did}", json={"hands_free": True}, headers=h)
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=5)
    r = await client.post(f"{API}/devices/{did}/stop", headers=h)
    assert r.json()["settings"]["hands_free"] is False
    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5)
    assert msg and json.loads(msg["data"]) == {"type": "stop"}

    assert (await client.delete(f"{API}/devices/{did}", headers=h)).status_code == 204
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=5)  # settings
    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5)
    assert msg and json.loads(msg["data"]) == {"type": "revoked"}
    await pubsub.aclose()  # type: ignore[no-untyped-call]
    # The agent's session ends with it.
    agent = {"Authorization": f"Bearer {t['access_token']}"}
    assert (await client.get(f"{API}/auth/me", headers=agent)).status_code == 401
    assert (await client.get(f"{API}/devices", headers=h)).json() == []
    async with get_sessionmaker()() as db:
        actions = set(await db.scalars(select(AuditLog.action)))
        assert {"device.paired", "device.removed"} <= actions


async def test_other_owner_cannot_touch_device(client: AsyncClient) -> None:
    h = await auth_headers(client)
    t = await _pair(client, h)
    r = await client.patch(f"{API}/devices/{uuid.uuid4()}", json={"wake_word": True}, headers=h)
    assert r.status_code == 404
    r = await client.patch(f"{API}/devices/{t['device_id']}", json={"wake_word": True})
    assert r.status_code == 401


class FakeSocket:
    def __init__(self, auth: str | None) -> None:
        self.headers = {"authorization": auth} if auth else {}


async def test_socket_auth_and_presence(client: AsyncClient) -> None:
    h = await auth_headers(client)
    t = await _pair(client, h)
    did = uuid.UUID(t["device_id"])
    ok = await device_routes._ws_device(FakeSocket(f"Bearer {t['access_token']}"))  # type: ignore[arg-type]
    assert ok == did
    # A normal browser session is not a device.
    assert await device_routes._ws_device(FakeSocket(h["Authorization"])) is None  # type: ignore[arg-type]
    assert await device_routes._ws_device(FakeSocket(None)) is None  # type: ignore[arg-type]
    assert await device_routes._ws_device(FakeSocket("Bearer nope")) is None  # type: ignore[arg-type]

    await device_routes._handle(
        did,
        {"type": "hello", "capabilities": {"wake_word": True, "version": "0.1.0"}, "mic": "wake"},
    )
    d = (await client.get(f"{API}/devices", headers=h)).json()[0]
    assert d["online"] is True and d["mic"] == "wake"
    assert d["capabilities"] == {"wake_word": True, "version": "0.1.0"}
    await device_routes._handle(did, {"type": "state", "mic": "rm -rf"})
    assert (await client.get(f"{API}/devices", headers=h)).json()[0]["mic"] == "off"

    # Revoked session: the socket is refused.
    async with get_sessionmaker()() as db:
        device = await db.get(Device, did)
        assert device is not None and device.session_id is not None
        session = await db.get(UserSession, device.session_id)
        assert session is not None
        token = create_access_token(
            session.user_id, session.id, get_settings().jwt_secret.get_secret_value(), 5
        )
    await client.delete(f"{API}/devices/{did}", headers=h)
    assert await device_routes._ws_device(FakeSocket(f"Bearer {token}")) is None  # type: ignore[arg-type]


# --- home layout -----------------------------------------------------------------------


async def test_home_layout_round_trip(client: AsyncClient) -> None:
    h = await auth_headers(client)
    r = await client.get(f"{API}/preferences/home", headers=h)
    assert r.json() == {"mode": "expanded", "widgets": []}
    layout = {
        "mode": "compact",
        "widgets": [
            {"id": "schedule", "size": "l", "hidden": False},
            {"id": "inbox", "size": "s", "hidden": True},
            {"id": "schedule", "size": "s", "hidden": True},
        ],
    }
    r = await client.put(f"{API}/preferences/home", json=layout, headers=h)
    assert r.status_code == 200
    assert r.json()["widgets"] == layout["widgets"][:2]  # duplicates dropped
    assert (await client.get(f"{API}/preferences/home", headers=h)).json()["mode"] == "compact"
    bad = {"mode": "giant", "widgets": []}
    assert (await client.put(f"{API}/preferences/home", json=bad, headers=h)).status_code == 422
    bad2 = {"mode": "compact", "widgets": [{"id": "<script>"}]}
    assert (await client.put(f"{API}/preferences/home", json=bad2, headers=h)).status_code == 422
