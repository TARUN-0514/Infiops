"""Voice: speech-to-text and text-to-speech through the local voice server."""

from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import Auth
from app.core.config import get_settings
from app.services import voice as svc
from app.services.rate_limit import enforce_rate_limit

router = APIRouter(tags=["voice"])


def _error(exc: svc.VoiceError) -> HTTPException:
    code = 503 if exc.code.endswith("unreachable") or exc.code == "voice_off" else 502
    if exc.code == "empty":
        code = 400
    return HTTPException(code, detail={"code": exc.code, "message": exc.message})


@router.get("/voice/status")
async def voice_status(auth: Auth) -> dict[str, Any]:
    return await svc.status()


@router.post("/voice/transcribe")
async def transcribe(auth: Auth, file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    await enforce_rate_limit(f"stt:{auth.user.id}", 120, 60)
    ctype = (file.content_type or "").split(";")[0].strip().lower()
    if ctype not in svc.AUDIO_TYPES:
        raise HTTPException(
            415, detail={"code": "bad_audio", "message": "Send WAV, WebM, Ogg or MP3 audio."}
        )
    limit = get_settings().voice_max_upload_mb * 1024 * 1024
    audio = await file.read(limit + 1)
    if not audio:
        raise HTTPException(400, detail={"code": "bad_audio", "message": "No audio received."})
    if len(audio) > limit:
        raise HTTPException(413, detail={"code": "too_large", "message": "That clip is too long."})
    try:
        result = await svc.transcribe(audio, file.filename or "speech.wav", ctype)
    except svc.VoiceError as exc:
        raise _error(exc) from None
    return {"text": result.text, "ms": result.ms}


class SpeakIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=4000)


@router.post("/voice/speak")
async def speak(body: SpeakIn, auth: Auth) -> Response:
    await enforce_rate_limit(f"tts:{auth.user.id}", 240, 60)
    try:
        audio, ms = await svc.speak(body.text)
    except svc.VoiceError as exc:
        raise _error(exc) from None
    return Response(
        audio, media_type="audio/wav", headers={"X-Voice-Ms": str(ms), "Cache-Control": "no-store"}
    )
