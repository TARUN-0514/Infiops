"""Talks to the NEXUS API with the device's own session. Access tokens are short-lived and
refreshed with a rotating device refresh token, which is saved after every rotation."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from nexus_agent.config import AgentConfig

PREFIX = "/api/v1"


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


class Unpaired(ApiError):
    """The device was removed in NEXUS, or its session ended. Pair again."""


def _message(r: httpx.Response) -> str:
    try:
        body = r.json()
        return str(body.get("error", {}).get("message") or body)
    except ValueError:
        return r.text[:200] or f"HTTP {r.status_code}"


class Api:
    def __init__(
        self, config: AgentConfig, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.config = config
        self.http = httpx.AsyncClient(
            base_url=config.server.rstrip("/"), transport=transport, timeout=60
        )
        self.access_token: str | None = None
        self.conversation_id: str | None = None

    async def close(self) -> None:
        await self.http.aclose()

    async def pair(self, code: str, name: str, platform: str) -> None:
        r = await self.http.post(
            f"{PREFIX}/devices/pair", json={"code": code, "name": name, "platform": platform}
        )
        if r.status_code != 201:
            raise ApiError(r.status_code, _message(r))
        body = r.json()
        self.config.device_id, self.config.refresh_token = body["device_id"], body["refresh_token"]
        self.config.name = name
        self.access_token = body["access_token"]
        self.config.save()

    async def refresh(self) -> str:
        if not self.config.paired:
            raise Unpaired(401, "This PC isn't paired. Run: nexus-agent pair")
        r = await self.http.post(
            f"{PREFIX}/devices/token",
            json={"device_id": self.config.device_id, "refresh_token": self.config.refresh_token},
        )
        if r.status_code in (401, 403):
            raise Unpaired(r.status_code, _message(r))
        if r.status_code != 200:
            raise ApiError(r.status_code, _message(r))
        body = r.json()
        self.config.refresh_token = body["refresh_token"]
        self.config.save()
        self.access_token = body["access_token"]
        return self.access_token

    async def token(self) -> str:
        return self.access_token or await self.refresh()

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(2):
            headers = {"Authorization": f"Bearer {await self.token()}"}
            r = await self.http.request(method, PREFIX + path, headers=headers, **kwargs)
            if r.status_code == 401 and attempt == 0:
                self.access_token = None
                continue
            return r
        return r

    async def transcribe(self, wav: bytes) -> str:
        r = await self.request(
            "POST", "/voice/transcribe", files={"file": ("speech.wav", wav, "audio/wav")}
        )
        if r.status_code != 200:
            raise ApiError(r.status_code, _message(r))
        return str(r.json()["text"])

    async def speak(self, text: str) -> bytes:
        r = await self.request("POST", "/voice/speak", json={"text": text})
        if r.status_code != 200:
            raise ApiError(r.status_code, _message(r))
        return r.content

    async def new_conversation(self) -> str:
        r = await self.request("POST", "/chat/conversations")
        if r.status_code != 201:
            raise ApiError(r.status_code, _message(r))
        self.conversation_id = str(r.json()["id"])
        return self.conversation_id

    async def ask(self, text: str) -> AsyncIterator[dict[str, Any]]:
        """Runs one spoken turn through the same assistant as chat; yields its events."""
        cid = self.conversation_id or await self.new_conversation()
        headers = {"Authorization": f"Bearer {await self.token()}"}
        async with self.http.stream(
            "POST",
            f"{PREFIX}/chat/conversations/{cid}/messages",
            json={"text": text, "voice": True},
            headers=headers,
            timeout=httpx.Timeout(10, read=300),
        ) as r:
            if r.status_code != 200:
                await r.aread()
                raise ApiError(r.status_code, _message(r))
            async for line in r.aiter_lines():
                if line.strip():
                    yield json.loads(line)

    def ws_url(self) -> str:
        base = self.config.server.rstrip("/")
        scheme = "wss" if base.startswith("https") else "ws"
        return f"{scheme}://{base.split('://', 1)[1]}{PREFIX}/devices/ws"
