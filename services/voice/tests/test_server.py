from fastapi.testclient import TestClient

from nexus_voice.server import create_app


class FakeSTT:
    name = "fake-stt"

    def __init__(self) -> None:
        self.calls: list[tuple[int, str | None]] = []

    def transcribe(self, audio: bytes, language: str | None) -> str:
        self.calls.append((len(audio), language))
        return "  what's on my calendar today "


class FakeTTS:
    name = "fake-voice"

    def synthesize(self, text: str) -> bytes:
        return b"RIFF" + text.encode()


class BrokenSTT(FakeSTT):
    def transcribe(self, audio: bytes, language: str | None) -> str:
        raise RuntimeError("model missing")


def client(stt: FakeSTT | None = None) -> TestClient:
    return TestClient(create_app(stt or FakeSTT(), FakeTTS()))


def test_health_names_models() -> None:
    assert client().get("/health").json() == {
        "status": "ok",
        "stt_model": "fake-stt",
        "tts_voice": "fake-voice",
    }


def test_transcribe_openai_and_whisper_cpp_paths() -> None:
    stt = FakeSTT()
    c = client(stt)
    for path in ("/v1/audio/transcriptions", "/inference"):
        r = c.post(
            path, files={"file": ("a.wav", b"RIFFdata", "audio/wav")}, data={"language": "en"}
        )
        assert r.status_code == 200
        assert r.json()["text"] == "what's on my calendar today"
    assert stt.calls == [(8, "en"), (8, "en")]


def test_transcribe_rejects_empty_and_reports_engine_errors() -> None:
    assert (
        client().post("/inference", files={"file": ("a.wav", b"", "audio/wav")}).status_code == 400
    )
    r = client(BrokenSTT()).post("/inference", files={"file": ("a.wav", b"x", "audio/wav")})
    assert r.status_code == 500
    assert "RuntimeError" in r.json()["detail"]


def test_speech_returns_wav() -> None:
    r = client().post("/v1/audio/speech", json={"input": "Hello Tarun"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content == b"RIFFHello Tarun"
    assert "x-synthesis-ms" in r.headers
    assert client().post("/v1/audio/speech", json={"input": ""}).status_code == 422
    assert (
        client().post("/v1/audio/speech", json={"input": "x", "response_format": "mp3"}).status_code
        == 400
    )
