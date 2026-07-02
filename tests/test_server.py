"""Tests for the daemon's HTTP handlers, driven through the real client (no models, no GPU).

Runs the actual server._Handler on an ephemeral port with vnote.transcribe.transcribe
and vnote.cleanup.clean monkeypatched — the handlers import them at call time, so the
fakes are picked up without touching any heavy code path.
"""

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from vnote import cleanup, config, daemon, server, transcribe
from vnote.cleanup import CleanResult

_seen: dict = {}  # what the fake pipeline functions were called with, per test


def _fake_transcribe(audio_path, language=None):
    _seen["path"] = Path(audio_path)
    _seen["bytes"] = Path(audio_path).read_bytes()
    _seen["language"] = language
    return "fake transcript", {"language": language or "en", "device": "fake"}


def _fake_clean(transcript, mode="edit", backend="ollama", model=None, tone=None):
    _seen["clean"] = (transcript, mode, backend, model, tone)
    return CleanResult(title="Fake Title", body="Fake body.")


@pytest.fixture
def live_server(monkeypatch):
    _seen.clear()
    server._sessions.clear()
    monkeypatch.setattr(transcribe, "transcribe", _fake_transcribe)
    monkeypatch.setattr(cleanup, "clean", _fake_clean)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server._Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setattr(config, "daemon_addr", lambda: ("127.0.0.1", httpd.server_address[1]))
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def test_health(live_server):
    h = daemon.health()
    assert h is not None
    assert h["status"] == "ok"
    assert h["whisper_model"] == config.WHISPER_MODEL
    assert "device" in h and "uptime_s" in h


def test_transcribe_path_mode(live_server, tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFFfake")
    text, meta = daemon.transcribe(audio, language="en")
    assert text == "fake transcript"
    assert meta["language"] == "en"
    assert _seen["path"] == audio  # daemon read the file in place, no copy


def test_transcribe_path_mode_missing_file(live_server):
    with pytest.raises(RuntimeError, match="no such file"):
        daemon.transcribe(Path("/definitely/not/here.wav"))


def test_transcribe_bytes_mode(live_server):
    text, meta = daemon.transcribe_bytes(b"FLACDATA", fmt="flac", language="en")
    assert text == "fake transcript"
    assert _seen["bytes"] == b"FLACDATA"  # body landed in the temp file intact
    assert _seen["language"] == "en"
    assert _seen["path"].suffix == ".flac"
    assert not _seen["path"].exists()  # temp upload removed after the call


def test_transcribe_bytes_mode_empty_body(live_server):
    with pytest.raises(RuntimeError, match="empty audio body"):
        daemon.transcribe_bytes(b"")


def test_transcribe_bytes_mode_bad_format(live_server):
    with pytest.raises(RuntimeError, match="bad format"):
        daemon.transcribe_bytes(b"x", fmt="../../etc")


def test_clean_round_trip(live_server):
    result = daemon.clean("hello", mode="summary", backend="ollama", model="m", tone="formal")
    assert result == CleanResult(title="Fake Title", body="Fake body.")
    assert _seen["clean"] == ("hello", "summary", "ollama", "m", "formal")


def test_unknown_path_is_404(live_server):
    with pytest.raises(RuntimeError, match="not found"):
        daemon._post("/bogus", {}, timeout=5)


# --- streaming sessions --------------------------------------------------------


def _wav_frames(wav: bytes) -> int:
    import wave
    from io import BytesIO

    with wave.open(BytesIO(wav), "rb") as w:
        return w.getnframes()


def test_stream_round_trip_with_partials(live_server):
    sess = daemon.StreamSession(language="en")
    quarter_s = b"\x01\x00" * 4_000  # 0.25 s of PCM
    assert sess.append(quarter_s) == ""  # below the 0.5 s partial threshold
    assert sess.append(quarter_s) == "fake transcript"  # threshold crossed -> partial pass
    assert _wav_frames(_seen["bytes"]) == 8_000  # partial saw the full 0.5 s buffer
    assert _seen["language"] == "en"

    text, _meta = sess.finish()
    assert text == "fake transcript"
    assert _wav_frames(_seen["bytes"]) == 8_000  # final saw everything appended

    with pytest.raises(RuntimeError, match="unknown stream session"):  # finish() drops the session
        sess.append(quarter_s)


def test_stream_finish_without_audio_is_an_error(live_server):
    sess = daemon.StreamSession()
    with pytest.raises(RuntimeError, match="no audio"):
        sess.finish()


def test_stream_unknown_sid_is_404(live_server):
    sess = daemon.StreamSession()
    sess.sid = "nope"
    with pytest.raises(RuntimeError, match="unknown stream session"):
        sess.append(b"\x00\x00")


def test_stream_sessions_expire(live_server):
    sess = daemon.StreamSession()
    server._sessions[sess.sid].last_seen -= server._STREAM_TTL_S + 1
    daemon.StreamSession()  # any /stream/start sweeps expired sessions
    with pytest.raises(RuntimeError, match="unknown stream session"):
        sess.append(b"\x00\x00")
