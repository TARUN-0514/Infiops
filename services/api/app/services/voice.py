"""Speech on the owner's PC: speech-to-text and text-to-speech servers reached over HTTP.

Nothing here goes to the cloud. If a server isn't running, callers get a clear VoiceError
and the web app falls back (or explains how to start it)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings

_transport: httpx.AsyncBaseTransport | None = None

AUDIO_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/webm",
    "audio/ogg",
    "audio/mpeg",
    "audio/mp4",
}
MAX_SPEAK_CHARS = 1200


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Tests replace the voice servers with a mock transport."""
    global _transport
    _transport = transport


def _http(timeout: float = 30) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=_transport, timeout=timeout)


class VoiceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class Transcript:
    text: str
    ms: int


def _unreachable(what: str, url: str) -> VoiceError:
    return VoiceError(
        f"{what}_unreachable",
        f"Can't reach the {'speech recognition' if what == 'stt' else 'voice'} server at "
        f"{url}. Start the NEXUS voice server (see the Voice section of the README).",
    )


async def transcribe(audio: bytes, filename: str, content_type: str) -> Transcript:
    s = get_settings()
    if not s.voice_enabled:
        raise VoiceError("voice_off", "Voice is turned off (NEXUS_VOICE_ENABLED=false).")
    data = {"response_format": "json", "temperature": "0", "model": "whisper-1"}
    if s.stt_language:
        data["language"] = s.stt_language
    started = time.perf_counter()
    try:
        async with _http(60) as http:
            r = await http.post(
                s.stt_url, files={"file": (filename, audio, content_type)}, data=data
            )
    except httpx.TransportError as exc:
        raise _unreachable("stt", s.stt_url) from exc
    if r.status_code >= 400:
        raise VoiceError(
            "stt_failed", f"Speech recognition failed ({r.status_code}). Check the voice server."
        )
    try:
        body: Any = r.json()
        text = str(body.get("text", "")) if isinstance(body, dict) else ""
    except ValueError:
        text = r.text
    return Transcript(_clean(text), int((time.perf_counter() - started) * 1000))


# whisper marks silence and noise like "[BLANK_AUDIO]" or "(wind blowing)".
_NOISE = re.compile(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", _NOISE.sub(" ", text)).strip()


def speakable(text: str) -> str:
    """Strips markdown so the voice doesn't read symbols aloud."""
    t = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\[(\d+)\]", "", t)  # citation markers
    t = re.sub(r"https?://\S+", "a link", t)
    t = re.sub(r"^\s{0,3}(#{1,6}|>|[-*+]|\d+\.)\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"(\*\*|__|\*|_|~~)(.+?)\1", r"\2", t)
    t = re.sub(r"\s+([.,!?;:])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


async def speak(text: str) -> tuple[bytes, int]:
    s = get_settings()
    if not s.voice_enabled:
        raise VoiceError("voice_off", "Voice is turned off (NEXUS_VOICE_ENABLED=false).")
    clean = speakable(text)[:MAX_SPEAK_CHARS]
    if not clean:
        raise VoiceError("empty", "Nothing to say.")
    started = time.perf_counter()
    try:
        async with _http(60) as http:
            r = await http.post(
                s.tts_url,
                json={
                    "model": "piper",
                    "input": clean,
                    "voice": s.tts_voice,
                    "response_format": "wav",
                },
            )
    except httpx.TransportError as exc:
        raise _unreachable("tts", s.tts_url) from exc
    if r.status_code >= 400 or not r.content:
        raise VoiceError("tts_failed", f"The voice server returned {r.status_code}.")
    return r.content, int((time.perf_counter() - started) * 1000)


def _silent_wav(ms: int = 300, rate: int = 16000) -> bytes:
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * (rate * ms // 1000))
    return buf.getvalue()


async def status() -> dict[str, Any]:
    """Real test calls to both servers. Ready only when each one actually answered."""
    s = get_settings()
    out: dict[str, Any] = {
        "enabled": s.voice_enabled,
        "stt": {"ready": False, "url": s.stt_url, "ms": None, "error": None},
        "tts": {"ready": False, "url": s.tts_url, "voice": s.tts_voice, "ms": None, "error": None},
    }
    if not s.voice_enabled:
        return out
    try:
        t = await transcribe(_silent_wav(), "test.wav", "audio/wav")
        out["stt"].update(ready=True, ms=t.ms)
    except VoiceError as exc:
        out["stt"]["error"] = exc.message
    try:
        _, ms = await speak("Ready.")
        out["tts"].update(ready=True, ms=ms)
    except VoiceError as exc:
        out["tts"]["error"] = exc.message
    return out
