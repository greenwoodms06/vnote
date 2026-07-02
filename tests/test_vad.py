"""Tests for VAD endpointing against the real bundled Silero model.

Needs numpy + faster-whisper (onnxruntime); skipped automatically on CI where
the heavy deps aren't installed.
"""

from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("faster_whisper")

from vnote import vad  # noqa: E402

_JFK = Path(__file__).resolve().parent.parent / ".testdata" / "jfk.flac"
_BYTES_PER_S = 2 * 16_000
_SILENCE_1S = b"\x00\x00" * 16_000


@pytest.fixture(scope="module")
def jfk_pcm() -> bytes:
    """The 11 s JFK clip as 16 kHz mono s16le (the file itself is 44.1 kHz stereo)."""
    from faster_whisper.audio import decode_audio

    audio = decode_audio(str(_JFK), sampling_rate=16_000)
    return (audio * 32767).astype(np.int16).tobytes()


def test_silence_has_no_spans_and_never_stops():
    assert vad.speech_spans(_SILENCE_1S * 3) == []
    assert vad.should_stop(_SILENCE_1S * 3) is False
    assert vad.should_stop(b"") is False


def test_speech_is_detected(jfk_pcm):
    spans = vad.speech_spans(jfk_pcm)
    assert spans, "expected speech in the JFK clip"
    assert sum(end - start for start, end in spans) > 5.0  # most of the 11 s is speech


def test_stops_only_after_trailing_silence(jfk_pcm):
    # clip ends ~0.5 s after the last word — not yet enough at a 1 s window
    assert vad.should_stop(jfk_pcm, silence_s=1.0) is False
    # 1.5 s of appended silence pushes it over
    assert vad.should_stop(jfk_pcm + _SILENCE_1S + _SILENCE_1S[: _BYTES_PER_S // 2], silence_s=1.0) is True


def test_no_stop_mid_speech(jfk_pcm):
    # 8 s in, JFK is between phrases for ~0.4 s — still well inside the window
    assert vad.should_stop(jfk_pcm[: 8 * _BYTES_PER_S], silence_s=1.0) is False


def test_too_short_clip_short_circuits(jfk_pcm):
    assert vad.should_stop(jfk_pcm[:_BYTES_PER_S], silence_s=1.0) is False
