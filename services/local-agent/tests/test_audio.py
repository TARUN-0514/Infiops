import wave
from io import BytesIO

from nexus_agent.audio import FRAME_MS, Endpointer, SentenceSplitter, rms, to_wav, tone

QUIET, LOUD = tone(FRAME_MS, 0.002), tone(FRAME_MS, 0.1)


def test_levels_and_wav() -> None:
    assert rms(b"") == 0.0
    assert abs(rms(LOUD) - 0.1) < 0.01
    assert rms(QUIET) < 0.005
    with wave.open(BytesIO(to_wav(LOUD))) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        assert w.getnframes() == 1280


def test_endpointer_finds_start_and_end_of_speech() -> None:
    ep = Endpointer(threshold=0.015)
    assert [ep.feed(QUIET) for _ in range(5)] == ["waiting"] * 5
    assert ep.feed(LOUD) == "waiting"  # 80 ms is not enough to start
    assert ep.feed(LOUD) == "speaking"
    for _ in range(10):
        assert ep.feed(LOUD) == "speaking"
    results = [ep.feed(QUIET) for _ in range(9)]
    assert results[-1] == "done" and results[:-1] == ["speaking"] * 8  # 700 ms of quiet
    assert len(ep.audio()) > 12 * len(LOUD)  # speech plus lead-in


def test_endpointer_gives_up_when_nothing_is_said() -> None:
    ep = Endpointer(threshold=0.015, no_speech_ms=800)
    assert [ep.feed(QUIET) for _ in range(10)][-1] == "timeout"


def test_endpointer_caps_long_speech() -> None:
    ep = Endpointer(threshold=0.015, max_ms=1000)
    out = [ep.feed(LOUD) for _ in range(13)]
    assert out[-1] == "done"


def test_sentence_splitter_streams_whole_sentences() -> None:
    sp = SentenceSplitter()
    got: list[str] = []
    for chunk in ["You have two ", "meetings today. The first is", " at 10. ", "Then lunch", "!"]:
        got += sp.feed(chunk)
    assert got == ["You have two meetings today.", "The first is at 10."]
    assert sp.flush() == ["Then lunch!"]
    assert sp.flush() == []


def test_sentence_splitter_joins_tiny_sentences() -> None:
    sp = SentenceSplitter()
    assert sp.feed("Yes. Done. I moved the meeting to Friday at 3. Anything else?") == [
        "Yes. Done. I moved the meeting to Friday at 3."
    ]
    assert sp.flush() == ["Anything else?"]
