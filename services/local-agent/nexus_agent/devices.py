"""Microphone, speaker and wake word on the real PC (sounddevice + openWakeWord)."""

from __future__ import annotations

import asyncio
import io
import wave
from collections.abc import AsyncIterator
from typing import Any, Protocol

from nexus_agent.audio import FRAME_SAMPLES, RATE


class AudioIO(Protocol):
    def frames(self) -> AsyncIterator[bytes]: ...

    def play(self, wav: bytes) -> None: ...

    def stop(self) -> None: ...

    @property
    def playing(self) -> bool: ...

    async def wait(self) -> None: ...


class WakeWord(Protocol):
    name: str

    def detect(self, frame: bytes) -> bool: ...

    def reset(self) -> None: ...


class SoundDeviceIO:
    def __init__(self) -> None:
        import sounddevice as sd

        self.sd = sd
        self._done = asyncio.Event()
        self._done.set()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def frames(self) -> AsyncIterator[bytes]:
        loop = asyncio.get_running_loop()
        self._loop = loop
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)

        def push(chunk: bytes) -> None:
            if not queue.full():  # drop audio rather than block the sound card
                queue.put_nowait(chunk)

        def callback(data: Any, _frames: int, _time: Any, _status: Any) -> None:
            loop.call_soon_threadsafe(push, bytes(data))

        # echo cancellation is up to Windows; keep the speaker volume moderate.
        with self.sd.RawInputStream(
            samplerate=RATE, blocksize=FRAME_SAMPLES, channels=1, dtype="int16", callback=callback
        ):
            while True:
                yield await queue.get()

    def play(self, wav: bytes) -> None:
        import numpy as np

        with wave.open(io.BytesIO(wav)) as w:
            rate, channels = w.getframerate(), w.getnchannels()
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        if channels > 1:
            data = data.reshape(-1, channels)
        self._done.clear()
        loop = self._loop or asyncio.get_running_loop()

        def wait_then_signal() -> None:
            self.sd.wait()
            loop.call_soon_threadsafe(self._done.set)

        self.sd.play(data, rate)
        # sounddevice has no completion callback for play(); wait in a thread.
        loop.run_in_executor(None, wait_then_signal)

    def stop(self) -> None:
        self.sd.stop()
        self._done.set()

    @property
    def playing(self) -> bool:
        return not self._done.is_set()

    async def wait(self) -> None:
        await self._done.wait()


class OpenWakeWord:
    """openWakeWord with a pretrained model ("hey_jarvis") or a path to your own .onnx model."""

    def __init__(self, model: str, threshold: float = 0.5) -> None:
        import numpy as np
        import openwakeword
        from openwakeword.model import Model

        if not model.endswith((".onnx", ".tflite")):
            openwakeword.utils.download_models([model])
        self.np, self.threshold = np, threshold
        self.model = Model(wakeword_models=[model], inference_framework="onnx")
        self.name = model

    def detect(self, frame: bytes) -> bool:
        scores = self.model.predict(self.np.frombuffer(frame, dtype=self.np.int16))
        return any(float(s) >= self.threshold for s in scores.values())

    def reset(self) -> None:
        self.model.reset()
