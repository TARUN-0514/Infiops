"""HTTP server: POST /v1/audio/transcriptions (multipart `file`) returns {"text": ...};
POST /v1/audio/speech ({"input": ...}) returns WAV audio. Same shapes as the OpenAI audio API,
so NEXUS can also point at whisper.cpp's server or another compatible engine."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from nexus_voice.engines import PiperTTS, SpeechToText, TextToSpeech, WhisperSTT

MAX_AUDIO_BYTES = 10 * 1024 * 1024


class SpeechIn(BaseModel):
    input: str = Field(min_length=1, max_length=2000)
    voice: str | None = None
    model: str | None = None
    response_format: str = "wav"


def create_app(stt: SpeechToText, tts: TextToSpeech) -> FastAPI:
    app = FastAPI(title="NEXUS voice", docs_url=None, redoc_url=None)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "stt_model": stt.name, "tts_voice": tts.name}

    @app.post("/v1/audio/transcriptions")
    @app.post("/inference")
    async def transcriptions(
        file: Annotated[UploadFile, File()],
        language: Annotated[str | None, Form()] = None,
    ) -> dict[str, Any]:
        audio = await file.read(MAX_AUDIO_BYTES + 1)
        if not audio:
            raise HTTPException(400, "Empty audio.")
        if len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Audio is too long.")
        started = time.perf_counter()
        try:
            text = await asyncio.to_thread(stt.transcribe, audio, language)
        except Exception as exc:
            raise HTTPException(500, f"Speech recognition failed: {type(exc).__name__}") from exc
        return {"text": text.strip(), "ms": int((time.perf_counter() - started) * 1000)}

    @app.post("/v1/audio/speech")
    async def speech(body: SpeechIn) -> Response:
        if body.response_format not in ("wav", "pcm"):
            raise HTTPException(400, "Only WAV output is supported.")
        started = time.perf_counter()
        try:
            audio = await asyncio.to_thread(tts.synthesize, body.input)
        except Exception as exc:
            raise HTTPException(500, f"Speech synthesis failed: {type(exc).__name__}") from exc
        ms = int((time.perf_counter() - started) * 1000)
        return Response(audio, media_type="audio/wav", headers={"X-Synthesis-Ms": str(ms)})

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="NEXUS local voice server")
    parser.add_argument("--host", default=os.environ.get("VOICE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("VOICE_PORT", "8880")))
    parser.add_argument("--stt-model", default=os.environ.get("VOICE_STT_MODEL", "base.en"))
    parser.add_argument("--voice", default=os.environ.get("VOICE_TTS_VOICE", "en_US-lessac-medium"))
    parser.add_argument(
        "--data-dir", default=os.environ.get("VOICE_DATA_DIR", str(Path.home() / ".nexus-voice"))
    )
    parser.add_argument("--preload", action="store_true", help="Load both models at start")
    args = parser.parse_args()

    import uvicorn

    data = Path(args.data_dir)
    stt, tts = WhisperSTT(args.stt_model, data), PiperTTS(args.voice, data)
    if args.preload or os.environ.get("VOICE_PRELOAD") == "1":
        stt._load()
        tts._load()
    uvicorn.run(create_app(stt, tts), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
