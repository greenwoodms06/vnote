"""Tests for argument parsing (no audio, no models touched)."""

from vnote.cli import _parse_args


def test_defaults():
    a = _parse_args([])
    assert a.mode == "edit"
    assert a.backend is None  # resolved later from saved choice / env / built-in
    assert a.raw is False
    assert a.no_clipboard is False
    assert a.audio is None
    assert a.serve is False
    assert a.no_daemon is False


def test_mode_flags_are_mutually_exclusive_values():
    assert _parse_args(["--light"]).mode == "light"
    assert _parse_args(["--summary"]).mode == "summary"
    assert _parse_args(["--edit"]).mode == "edit"


def test_backend_and_audio_and_flags():
    a = _parse_args(["memo.m4a", "--backend", "claude", "--raw", "--no-clipboard"])
    assert a.audio == "memo.m4a"
    assert a.backend == "claude"
    assert a.raw is True
    assert a.no_clipboard is True
