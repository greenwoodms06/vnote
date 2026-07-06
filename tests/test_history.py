"""Tests for the flow-history writer: entry format, day files, audio naming."""

import json
from datetime import datetime

import pytest

from vnote import history

WHEN = datetime(2026, 7, 6, 14, 32, 7)


def _flow_root(monkeypatch, tmp_path):
    monkeypatch.setattr(history, "NOTES_DIR", tmp_path)
    return tmp_path / "flow"


def test_full_take_writes_audio_then_linked_entry(monkeypatch, tmp_path):
    flow = _flow_root(monkeypatch, tmp_path)
    day = history.append_take(raw="um hello", clean="Hello.", wav=b"RIFF",
                              seconds=4.9, mode="dictation", tone="casual", when=WHEN)
    assert day == flow / "2026-07-06.md"
    audio = flow / "audio" / "20260706-143207.wav"
    assert audio.read_bytes() == b"RIFF"
    text = day.read_text(encoding="utf-8")
    assert "## 14:32:07  (4.9s, clean=dictation, tone=casual)" in text
    assert "[audio](audio/20260706-143207.wav)" in text
    assert "**raw:** um hello" in text
    assert "**clean:** Hello." in text


def test_raw_only_take_without_audio(monkeypatch, tmp_path):
    flow = _flow_root(monkeypatch, tmp_path)
    day = history.append_take(raw="hi", clean=None, wav=None,
                              seconds=2.1, mode=None, tone=None, when=WHEN)
    text = day.read_text(encoding="utf-8")
    assert "## 14:32:07  (2.1s, raw)" in text
    assert "audio" not in text and not (flow / "audio").exists()
    assert "**clean:**" not in text


def test_same_second_collision_suffixes(monkeypatch, tmp_path):
    flow = _flow_root(monkeypatch, tmp_path)
    history.append_take(raw="a", clean=None, wav=b"ONE", seconds=1.0, mode=None, tone=None, when=WHEN)
    history.append_take(raw="b", clean=None, wav=b"TWO", seconds=1.0, mode=None, tone=None, when=WHEN)
    assert (flow / "audio" / "20260706-143207.wav").read_bytes() == b"ONE"
    assert (flow / "audio" / "20260706-143207-2.wav").read_bytes() == b"TWO"


def test_takes_append_and_days_roll_over(monkeypatch, tmp_path):
    flow = _flow_root(monkeypatch, tmp_path)
    history.append_take(raw="one", clean=None, wav=None, seconds=1.0, mode=None, tone=None, when=WHEN)
    history.append_take(raw="two", clean=None, wav=None, seconds=1.0, mode=None, tone=None,
                        when=datetime(2026, 7, 7, 0, 0, 1))
    assert "**raw:** one" in (flow / "2026-07-06.md").read_text(encoding="utf-8")
    assert "**raw:** two" in (flow / "2026-07-07.md").read_text(encoding="utf-8")


# --- promotion -------------------------------------------------------------------


def _promote_root(monkeypatch, tmp_path):
    from vnote import output

    monkeypatch.setattr(history, "NOTES_DIR", tmp_path)
    monkeypatch.setattr(output, "NOTES_DIR", tmp_path)  # make_session_dir binds its own copy
    return tmp_path / "flow"


def test_promote_last_builds_session_and_leaves_pointer(monkeypatch, tmp_path):
    flow = _promote_root(monkeypatch, tmp_path)
    history.append_take(raw="um hello world", clean="Hello world.", wav=b"RIFF",
                        seconds=4.9, mode="dictation", tone="casual", when=WHEN)
    session = history.promote_take("last")

    assert session.name == "2026-07-06-1432-hello-world"
    assert (session / "audio.wav").read_bytes() == b"RIFF"
    assert not (flow / "audio" / "20260706-143207.wav").exists()  # moved, not copied
    assert (session / "transcript.txt").read_text(encoding="utf-8") == "um hello world\n"
    note = (session / "note.md").read_text(encoding="utf-8")
    assert note.startswith("# Hello world.") and "Hello world." in note
    meta = json.loads((session / "meta.json").read_text(encoding="utf-8"))
    assert meta["source"] == "flow-promoted"
    assert meta["seconds"] == 4.9 and meta["mode"] == "dictation" and meta["tone"] == "casual"

    day = (flow / "2026-07-06.md").read_text(encoding="utf-8")
    assert "## 14:32:07  (4.9s, clean=dictation, tone=casual)" in day  # header kept
    assert f"[note](../{session.name}/note.md)" in day
    assert "**raw:**" not in day  # body replaced by the pointer


def test_promote_by_time_leaves_other_entries_alone(monkeypatch, tmp_path):
    flow = _promote_root(monkeypatch, tmp_path)
    history.append_take(raw="first take", clean=None, wav=None, seconds=1.0,
                        mode=None, tone=None, when=WHEN)
    history.append_take(raw="second take", clean=None, wav=None, seconds=1.0,
                        mode=None, tone=None, when=datetime(2026, 7, 6, 15, 0, 0))
    history.promote_take("14:32:07")
    day = (flow / "2026-07-06.md").read_text(encoding="utf-8")
    assert "**raw:** second take" in day  # untouched
    assert "**raw:** first take" not in day  # promoted away


def test_promote_multiline_text_round_trips(monkeypatch, tmp_path):
    _promote_root(monkeypatch, tmp_path)
    history.append_take(raw="para one\n\npara two", clean=None, wav=None,
                        seconds=2.0, mode=None, tone=None, when=WHEN)
    session = history.promote_take("last")
    assert (session / "transcript.txt").read_text(encoding="utf-8") == "para one\n\npara two\n"


def test_promote_audio_less_take(monkeypatch, tmp_path):
    _promote_root(monkeypatch, tmp_path)
    history.append_take(raw="no audio here", clean=None, wav=None,
                        seconds=1.0, mode=None, tone=None, when=WHEN)
    session = history.promote_take("last")
    assert not (session / "audio.wav").exists()
    assert (session / "note.md").exists()


def test_promote_twice_is_an_error_and_log_unchanged(monkeypatch, tmp_path):
    flow = _promote_root(monkeypatch, tmp_path)
    history.append_take(raw="only take", clean=None, wav=None, seconds=1.0,
                        mode=None, tone=None, when=WHEN)
    history.promote_take("last")
    before = (flow / "2026-07-06.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="already promoted"):
        history.promote_take("last")
    assert (flow / "2026-07-06.md").read_text(encoding="utf-8") == before


def test_promote_unknown_time_and_empty_store(monkeypatch, tmp_path):
    _promote_root(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="no flow history"):
        history.promote_take("last")
    history.append_take(raw="x", clean=None, wav=None, seconds=1.0,
                        mode=None, tone=None, when=WHEN)
    with pytest.raises(ValueError, match="no take at"):
        history.promote_take("09:09:09")
