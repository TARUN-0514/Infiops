"""Speech engines. Each loads its model on first use and keeps it in memory."""

from __future__ import annotations

import io
import threading
import wave
from pathlib import Path
from typing import Protocol


class SpeechToText(Protocol):
    name: str

    def transcribe(self, audio: bytes, language: str | None) -> str: ...


class TextToSpeech(Protocol):
    name: str

    def synthesize(self, text: str) -> bytes: ...


class WhisperSTT:
    """faster-whisper on the CPU (int8). The model downloads on first use."""

    def __init__(self, model: str, data_dir: Path, threads: int = 0) -> None:
        self.name, self.data_dir, self.threads = model, data_dir, threads
        self._model: object | None = None
        self._lock = threading.Lock()

    def _load(self) -> object:
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self.name,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=self.threads,
                    download_root=str(self.data_dir / "whisper"),
                )
            return self._model

    def transcribe(self, audio: bytes, language: str | None) -> str:
        model = self._load()
        segments, _ = model.transcribe(  # type: ignore[attr-defined]
            io.BytesIO(audio), language=language or None, beam_size=1, vad_filter=True
        )
        return " ".join(s.text.strip() for s in segments).strip()


class PiperTTS:
    """Piper voices. The voice downloads on first use."""

    def __init__(self, voice: str, data_dir: Path) -> None:
        self.name, self.data_dir = voice, data_dir / "piper"
        self._voice: object | None = None
        self._lock = threading.Lock()

    def _load(self) -> object:
        with self._lock:
            if self._voice is None:
                from piper import PiperVoice
                from piper.download_voices import download_voice

                self.data_dir.mkdir(parents=True, exist_ok=True)
                path = self.data_dir / f"{self.name}.onnx"
                if not path.exists():
                    download_voice(self.name, self.data_dir)
                self._voice = PiperVoice.load(path)
            return self._voice

    def synthesize(self, text: str) -> bytes:
        voice = self._load()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            voice.synthesize_wav(text, wav)  # type: ignore[attr-defined]
        return buf.getvalue()
