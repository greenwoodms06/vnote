"""Tests for the doctor environment checks (shape, not environment-specific results)."""

from vnote import doctor

_MARKS = {doctor.OK, doctor.WARN, doctor.BAD}


def test_each_check_returns_mark_and_message():
    for check in (doctor._check_recorder, doctor._check_gpu, doctor._check_clipboard):
        mark, msg = check()
        assert mark in _MARKS
        assert isinstance(msg, str) and msg


def test_backend_check_handles_both_backends(monkeypatch):
    # claude with no key / package -> a clear non-OK verdict (BAD), never crashes
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    mark, msg = doctor._check_backend("claude")
    assert mark in _MARKS and "claude" in msg.lower() or "anthropic" in msg.lower()

    # ollama check returns a mark regardless of whether a server is running
    mark2, msg2 = doctor._check_backend("ollama")
    assert mark2 in _MARKS
