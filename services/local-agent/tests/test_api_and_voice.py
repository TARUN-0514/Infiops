import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from nexus_agent.api import Api, ApiError, Unpaired
from nexus_agent.audio import FRAME_MS, tone
from nexus_agent.config import AgentConfig
from nexus_agent.runtime import Agent, VoiceSession

QUIET, LOUD = tone(FRAME_MS, 0.002), tone(FRAME_MS, 0.1)


class FakeServer:
    def __init__(self) -> None:
        self.refresh_count = 0
        self.valid_access = "access-1"
        self.refresh_token = "refresh-1"
        self.reply = "You have two meetings today. The first is at ten."
        self.spoken: list[str] = []
        self.asked: list[dict[str, Any]] = []
        self.transcript = "What's on today?"

    def handler(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path == "/api/v1/devices/pair":
            body = json.loads(req.content)
            if body["code"] != "ABCD-2345":
                return httpx.Response(
                    400, json={"error": {"message": "That pairing code is wrong."}}
                )
            return httpx.Response(
                201,
                json={
                    "device_id": "dev-1",
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 900,
                },
            )
        if path == "/api/v1/devices/token":
            body = json.loads(req.content)
            if body["refresh_token"] != self.refresh_token:
                return httpx.Response(401, json={"error": {"message": "This device was removed."}})
            self.refresh_count += 1
            self.refresh_token = f"refresh-{self.refresh_count + 1}"
            self.valid_access = f"access-{self.refresh_count + 1}"
            return httpx.Response(
                200,
                json={
                    "device_id": "dev-1",
                    "access_token": self.valid_access,
                    "refresh_token": self.refresh_token,
                    "expires_in": 900,
                },
            )
        if req.headers.get("authorization") != f"Bearer {self.valid_access}":
            return httpx.Response(401, json={"error": {"message": "Sign in."}})
        if path == "/api/v1/voice/transcribe":
            return httpx.Response(200, json={"text": self.transcript, "ms": 120})
        if path == "/api/v1/voice/speak":
            self.spoken.append(json.loads(req.content)["text"])
            return httpx.Response(200, content=b"RIFFwav")
        if path == "/api/v1/chat/conversations":
            return httpx.Response(201, json={"id": "conv-1"})
        if path == "/api/v1/chat/conversations/conv-1/messages":
            body = json.loads(req.content)
            self.asked.append(body)
            words = self.reply.split(" ")
            lines = (
                [{"type": "run.started"}]
                + [{"type": "text.delta", "text": w + " "} for w in words]
                + [{"type": "run.finished"}]
            )
            return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines).encode())
        return httpx.Response(404)


def make_api(server: FakeServer, paired: bool = True) -> Api:
    cfg = AgentConfig(server="http://nexus.test")
    if paired:
        cfg.device_id, cfg.refresh_token = "dev-1", "refresh-1"
    return Api(cfg, transport=httpx.MockTransport(server.handler))


async def test_pair_saves_config_and_bad_code_fails() -> None:
    server = FakeServer()
    api = make_api(server, paired=False)
    with pytest.raises(ApiError, match="wrong"):
        await api.pair("ZZZZ-ZZZZ", "PC", "windows")
    await api.pair("ABCD-2345", "Tarun's PC", "windows")
    saved = AgentConfig.load()
    assert (saved.device_id, saved.refresh_token, saved.name) == (
        "dev-1",
        "refresh-1",
        "Tarun's PC",
    )
    assert oct(saved.path.stat().st_mode & 0o777) == oct(0o600)


async def test_expired_access_token_is_refreshed_and_rotation_saved() -> None:
    server = FakeServer()
    api = make_api(server)
    api.access_token = "stale"
    assert await api.transcribe(b"RIFF") == "What's on today?"
    assert server.refresh_count == 1
    assert AgentConfig.load().refresh_token == "refresh-2"
    assert api.ws_url() == "ws://nexus.test/api/v1/devices/ws"


async def test_removed_device_is_reported() -> None:
    server = FakeServer()
    server.refresh_token = "something-else"
    with pytest.raises(Unpaired):
        await make_api(server).refresh()


class FakeAudio:
    def __init__(self) -> None:
        self.played: list[bytes] = []
        self.stopped = 0
        self._done = asyncio.Event()
        self._done.set()

    async def frames(self) -> AsyncIterator[bytes]:
        if False:
            yield b""

    def play(self, wav: bytes) -> None:
        self.played.append(wav)
        self._done.clear()
        asyncio.get_running_loop().call_later(0.01, self._done.set)

    def stop(self) -> None:
        self.stopped += 1
        self._done.set()

    @property
    def playing(self) -> bool:
        return not self._done.is_set()

    async def wait(self) -> None:
        await self._done.wait()


class FakeWake:
    name = "hey_jarvis"

    def __init__(self) -> None:
        self.armed = False

    def detect(self, frame: bytes) -> bool:
        return self.armed

    def reset(self) -> None:
        self.armed = False


async def _settle(session: VoiceSession) -> None:
    if session.turn:
        await session.turn


async def test_wake_word_turn_speaks_reply_sentence_by_sentence() -> None:
    server, audio, wake = FakeServer(), FakeAudio(), FakeWake()
    states: list[str] = []

    async def on_state(s: str) -> None:
        states.append(s)

    session = VoiceSession(make_api(server), audio, wake, threshold=0.015, on_state=on_state)
    await session.apply({"wake_word": True})
    assert session.state == "wake"
    await session.feed(LOUD)  # loud but no wake word: nothing happens
    assert session.state == "wake"
    wake.armed = True
    await session.feed(QUIET)
    assert session.state == "listening"
    for f in [LOUD] * 8 + [QUIET] * 9:
        await session.feed(f)
    assert session.state == "thinking"
    await _settle(session)
    assert server.asked == [{"text": "What's on today?", "voice": True}]
    assert server.spoken == ["You have two meetings today.", "The first is at ten."]
    assert len(audio.played) == 2
    assert session.last_latency_ms is not None
    assert states == ["wake", "listening", "thinking", "speaking", "wake"]


async def test_hands_free_keeps_listening_and_barge_in_interrupts() -> None:
    server, audio = FakeServer(), FakeAudio()
    server.reply = "Here is a long answer. " * 3
    session = VoiceSession(make_api(server), audio, None, threshold=0.015, on_state=_noop)
    await session.apply({"hands_free": True})
    assert session.state == "listening"
    for f in [LOUD] * 4 + [QUIET] * 9:
        await session.feed(f)
    # Interrupt while it speaks.
    while session.state != "speaking":  # noqa: ASYNC110
        await asyncio.sleep(0.001)
    audio._done.clear()  # keep "playing" until interrupted
    for f in [LOUD] * 3:
        await session.feed(f)
    assert session.state == "listening" and audio.stopped >= 1
    assert session.turn is None


async def test_kill_switch_and_settings() -> None:
    server, audio = FakeServer(), FakeAudio()
    agent = Agent(make_api(server), audio, None)
    assert agent.voice is not None
    await agent.handle({"type": "settings", "settings": {"hands_free": True}})
    assert agent.voice.state == "listening"
    await agent.handle({"type": "stop"})
    assert agent.voice.state == "off" and agent.voice.settings["hands_free"] is False
    await agent.handle({"type": "revoked"})
    assert agent.stopped.is_set()
    assert agent.capabilities()["wake_word"] is False


async def _noop(_: str) -> None:
    return None
