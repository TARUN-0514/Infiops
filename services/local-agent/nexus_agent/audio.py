"""Audio helpers that don't need a sound card: levels, end-of-speech detection, WAV and
sentence splitting for low-latency speech."""

from __future__ import annotations

import io
import math
import re
import struct
import wave
from array import array

RATE = 16000
FRAME_MS = 80  # openWakeWord wants 1280-sample (80 ms) frames at 16 kHz
FRAME_SAMPLES = RATE * FRAME_MS // 1000


def rms(frame: bytes) -> float:
    """Level of 16-bit mono PCM, 0..1."""
    samples = array("h")
    samples.frombytes(frame[: len(frame) - len(frame) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0


def to_wav(pcm: bytes, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def tone(ms: int, level: float, rate: int = RATE) -> bytes:
    """Test signal: a 440 Hz tone at the given level (0..1)."""
    n = rate * ms // 1000
    amp = int(level * math.sqrt(2) * 32767)
    return struct.pack(
        f"<{n}h", *(int(amp * math.sin(2 * math.pi * 440 * i / rate)) for i in range(n))
    )


class Endpointer:
    """Decides when someone has started and finished speaking.

    Speech starts after `start_ms` above the threshold; it ends after `end_ms` of quiet.
    The threshold adapts upward to steady background noise."""

    def __init__(
        self,
        threshold: float = 0.015,
        start_ms: int = 160,
        end_ms: int = 700,
        max_ms: int = 15000,
        no_speech_ms: int = 6000,
    ) -> None:
        self.base, self.start_ms, self.end_ms = threshold, start_ms, end_ms
        self.max_ms, self.no_speech_ms = max_ms, no_speech_ms
        self.noise = threshold / 3
        self.reset()

    def reset(self) -> None:
        self.started = False
        self.loud_ms = self.quiet_ms = self.total_ms = 0
        self.frames: list[bytes] = []

    @property
    def threshold(self) -> float:
        return max(self.base, self.noise * 3)

    def feed(self, frame: bytes, ms: int = FRAME_MS) -> str:
        """Returns "waiting", "speaking", "done" (speech ended) or "timeout" (nothing said)."""
        level = rms(frame)
        self.total_ms += ms
        loud = level >= self.threshold
        if not self.started:
            self.frames = [*self.frames[-3:], frame]  # keep a little lead-in
            if loud:
                self.loud_ms += ms
                if self.loud_ms >= self.start_ms:
                    self.started = True
            else:
                self.loud_ms = 0
                self.noise = 0.95 * self.noise + 0.05 * level
            if not self.started and self.total_ms >= self.no_speech_ms:
                return "timeout"
            return "speaking" if self.started else "waiting"
        self.frames.append(frame)
        self.quiet_ms = 0 if loud else self.quiet_ms + ms
        if self.quiet_ms >= self.end_ms or self.total_ms >= self.max_ms:
            return "done"
        return "speaking"

    def audio(self) -> bytes:
        return b"".join(self.frames)


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n{2,}")


class SentenceSplitter:
    """Collects streamed text and hands back whole sentences, so speech can start on the
    first sentence while the model is still writing the rest."""

    def __init__(self, min_chars: int = 12) -> None:
        self.buf, self.min_chars = "", min_chars

    def feed(self, text: str) -> list[str]:
        self.buf += text
        out: list[str] = []
        while True:
            cut = next(
                (m for m in _SENTENCE_END.finditer(self.buf) if m.start() >= self.min_chars), None
            )
            if cut is None:
                break
            out.append(self.buf[: cut.start()].strip())
            self.buf = self.buf[cut.end() :]
        return [s for s in out if s]

    def flush(self) -> list[str]:
        rest, self.buf = self.buf.strip(), ""
        return [rest] if rest else []
