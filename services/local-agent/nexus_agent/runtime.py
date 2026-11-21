"""The agent's main loop: the link to NEXUS (WebSocket) and the voice conversation.

Voice states, sent to NEXUS so the app can show a mic indicator:
  off       microphone closed (wake word and hands-free both off)
  wake      listening only for the wake word, on this PC
  listening recording what you say
  thinking  waiting for NEXUS to answer
  speaking  reading the answer; talk over it to interrupt
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from nexus_agent import __version__
from nexus_agent.api import Api, ApiError, Unpaired
from nexus_agent.audio import FRAME_MS, Endpointer, SentenceSplitter, rms, to_wav
from nexus_agent.devices import AudioIO, WakeWord
from nexus_agent.operator import Operator

log = logging.getLogger("nexus_agent")

BARGE_IN_MS = 240  # this much loud speech while NEXUS talks stops it
FOLLOW_UP_MS = 8000  # hands-free: how long to wait for a follow-up


class VoiceSession:
    def __init__(
        self,
        api: Api,
        audio: AudioIO,
        wake: WakeWord | None,
        *,
        threshold: float,
        on_state: Callable[[str], Awaitable[None]],
    ) -> None:
        self.api, self.audio, self.wake = api, audio, wake
        self.threshold, self.on_state = threshold, on_state
        self.settings: dict[str, Any] = {"wake_word": False, "hands_free": False}
        self.state = "off"
        self.turn: asyncio.Task[None] | None = None
        self.endpoint = Endpointer(threshold)
        self.loud_ms = 0
        self.last_latency_ms: int | None = None
        self.transcripts: list[str] = []

    @property
    def active(self) -> bool:
        return bool(self.settings.get("wake_word") or self.settings.get("hands_free"))

    def idle_state(self) -> str:
        if self.settings.get("wake_word") and self.wake is not None:
            return "wake"
        return "listening" if self.settings.get("hands_free") else "off"

    async def set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            log.info("voice: %s", state)
            await self.on_state(state)

    async def apply(self, settings: dict[str, Any]) -> None:
        self.settings = {**self.settings, **settings}
        if self.state in ("off", "wake") or not self.active:
            await self.interrupt()
            await self.go_idle()

    async def go_idle(self) -> None:
        self.endpoint = Endpointer(self.threshold)
        if self.wake:
            self.wake.reset()
        await self.set_state(self.idle_state())

    async def interrupt(self) -> None:
        self.audio.stop()
        if self.turn and not self.turn.done():
            self.turn.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.turn
        self.turn = None

    async def stop(self) -> None:
        """Kill switch from NEXUS."""
        self.settings["hands_free"] = False
        await self.interrupt()
        await self.go_idle()

    async def listen_now(self) -> None:
        await self.interrupt()
        self.endpoint = Endpointer(self.threshold, no_speech_ms=FOLLOW_UP_MS)
        await self.set_state("listening")

    async def feed(self, frame: bytes) -> None:
        """One 80 ms microphone frame."""
        if self.state == "off":
            return
        if self.state == "wake":
            if self.wake is not None and self.wake.detect(frame):
                await self.listen_now()
            return
        if self.state == "listening":
            result = self.endpoint.feed(frame)
            if result == "done":
                audio = self.endpoint.audio()
                await self.set_state("thinking")
                self.turn = asyncio.create_task(self._turn(audio, time.perf_counter()))
            elif result == "timeout":
                await self.go_idle()
            return
        if self.state == "speaking":
            self.loud_ms = self.loud_ms + FRAME_MS if rms(frame) >= self.threshold * 2 else 0
            if self.loud_ms >= BARGE_IN_MS:
                self.loud_ms = 0
                log.info("voice: interrupted")
                await self.listen_now()
                self.endpoint.feed(frame)

    async def _say(self, text: str) -> None:
        try:
            wav = await self.api.speak(text)
        except ApiError as exc:
            log.warning("voice: can't speak: %s", exc.message)
            return
        await self.set_state("speaking")
        self.audio.play(wav)
        await self.audio.wait()

    async def _turn(self, pcm: bytes, ended: float) -> None:
        try:
            text = await self.api.transcribe(to_wav(pcm))
            if not text:
                await self.go_idle()
                return
            self.transcripts.append(text)
            log.info("you said: %s", text)
            splitter = SentenceSplitter()
            pending: list[asyncio.Task[bytes]] = []
            first = True

            async def play_ready(wait_all: bool) -> None:
                nonlocal first
                while pending and (wait_all or pending[0].done()):
                    task = pending.pop(0)
                    try:
                        wav = await task
                    except ApiError as exc:
                        log.warning("voice: can't speak: %s", exc.message)
                        continue
                    if first:
                        self.last_latency_ms = int((time.perf_counter() - ended) * 1000)
                        log.info("first audio after %d ms", self.last_latency_ms)
                        first = False
                    await self.set_state("speaking")
                    self.audio.play(wav)
                    await self.audio.wait()

            async for event in self.api.ask(text):
                kind = event.get("type")
                sentences: list[str] = []
                if kind == "text.delta":
                    sentences = splitter.feed(str(event.get("text", "")))
                elif kind == "error":
                    sentences = [str(event.get("message", "Something went wrong."))]
                for s in sentences:
                    pending.append(asyncio.create_task(self.api.speak(s)))
                if not self.audio.playing:
                    await play_ready(False)
            for s in splitter.flush():
                pending.append(asyncio.create_task(self.api.speak(s)))
            await play_ready(True)
        except ApiError as exc:
            log.warning("voice: %s", exc.message)
            await self._say(exc.message)
        if self.settings.get("hands_free"):
            await self.listen_now()
        else:
            await self.go_idle()


class Agent:
    """Keeps the WebSocket to NEXUS open and runs the voice session."""

    def __init__(self, api: Api, audio: AudioIO | None, wake: WakeWord | None) -> None:
        self.api, self.audio, self.wake = api, audio, wake
        self.ws: Any = None
        self.voice = (
            VoiceSession(
                api, audio, wake, threshold=api.config.speech_threshold, on_state=self.send_state
            )
            if audio is not None
            else None
        )
        self.stopped = asyncio.Event()
        self.operator = Operator(control=api.config.control)
        self.tools: dict[str, bool] = {}
        if api.config.control:
            from nexus_agent import browser, claude_code, screen

            for name, mod in (
                ("browser", browser),
                ("screen", screen),
                ("claude_code", claude_code),
            ):
                self.tools[name] = mod.available()
                if self.tools[name]:
                    mod.install(self.operator)
        self.calls: set[asyncio.Task[None]] = set()

    async def send(self, msg: dict[str, Any]) -> None:
        if self.ws is not None:
            with contextlib.suppress(Exception):
                await self.ws.send(json.dumps(msg))

    async def send_state(self, mic: str) -> None:
        await self.send({"type": "state", "mic": mic})

    def capabilities(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "microphone": self.audio is not None,
            "wake_word": self.wake is not None,
            "wake_word_model": self.wake.name if self.wake else "",
            "operator": self.operator.control,
            **self.tools,
        }

    async def _call(self, msg: dict[str, Any]) -> None:
        await self.send(await self.operator.handle_call(msg))

    async def handle(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "settings" and self.voice:
            await self.voice.apply(msg.get("settings") or {})
        elif kind == "policy" and isinstance(msg.get("policy"), dict):
            self.operator.set_policy(msg["policy"])
        elif kind == "call":
            # Run alongside the socket so a long action (Claude Code) doesn't block Stop.
            task = asyncio.create_task(self._call(msg))
            self.calls.add(task)
            task.add_done_callback(self.calls.discard)
        elif kind == "stop":
            if msg.get("scope") == "all":  # the computer-control kill switch
                await self.operator.stop()
            if self.voice:
                await self.voice.stop()
        elif kind == "revoked":
            log.error("This PC was removed in NEXUS. Pair it again to use it.")
            self.stopped.set()

    async def link(self) -> None:
        import websockets

        delay = 1.0
        while not self.stopped.is_set():
            try:
                token = await self.api.token()
                async with websockets.connect(
                    self.api.ws_url(), additional_headers={"Authorization": f"Bearer {token}"}
                ) as ws:
                    self.ws, delay = ws, 1.0
                    mic = self.voice.state if self.voice else "off"
                    await self.send(
                        {"type": "hello", "capabilities": self.capabilities(), "mic": mic}
                    )
                    log.info("connected to %s", self.api.config.server)
                    heartbeat = asyncio.create_task(self._heartbeat())
                    try:
                        async for raw in ws:
                            await self.handle(json.loads(raw))
                            if self.stopped.is_set():
                                return
                    finally:
                        heartbeat.cancel()
            except Unpaired as exc:
                log.error("%s", exc.message)
                self.stopped.set()
                return
            except Exception as exc:
                code = getattr(getattr(exc, "rcvd", None), "code", None)
                if code == 4401:
                    self.api.access_token = None
                elif code == 4403:
                    log.error("This PC was removed in NEXUS. Pair it again.")
                    self.stopped.set()
                    return
                log.warning("link down (%s); retrying in %.0fs", type(exc).__name__, delay)
            self.ws = None
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(15)
            await self.send_state(self.voice.state if self.voice else "off")

    async def listen(self) -> None:
        if self.audio is None or self.voice is None:
            return
        async for frame in self.audio.frames():
            if self.stopped.is_set():
                return
            await self.voice.feed(frame)

    async def run(self) -> None:
        tasks = [asyncio.create_task(self.link()), asyncio.create_task(self.listen())]
        await self.stopped.wait()
        await self.operator.stop()
        for t in [*tasks, *self.calls]:
            t.cancel()
        await asyncio.wait([*tasks, *self.calls], timeout=3)
        if self.voice:
            await self.voice.interrupt()
