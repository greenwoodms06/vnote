"""Tests for the flow-history writer: entry format, day files, audio naming."""

from datetime import datetime

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
