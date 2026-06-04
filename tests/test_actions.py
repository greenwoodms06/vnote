"""Tests for --redo resolution and parsing of the new utility flags."""

import pytest

from vnote.cli import _parse_args, _resolve_redo


def _make_session(tmp_path, with_meta=True):
    d = tmp_path / "2026-06-04-0900-some-note"
    d.mkdir()
    (d / "transcript.txt").write_text("the raw transcript text\n", encoding="utf-8")
    if with_meta:
        (d / "meta.json").write_text('{"title": "Some Note"}\n', encoding="utf-8")
    return d


def test_resolve_redo_from_session_dir(tmp_path):
    d = _make_session(tmp_path)
    text, session = _resolve_redo(d)
    assert text == "the raw transcript text"
    assert session == d


def test_resolve_redo_from_transcript_file_in_session(tmp_path):
    d = _make_session(tmp_path)
    text, session = _resolve_redo(d / "transcript.txt")
    assert text == "the raw transcript text"
    assert session == d  # recognized as part of a session (has meta.json) -> writable


def test_resolve_redo_bare_transcript_has_no_session(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("just some text", encoding="utf-8")
    text, session = _resolve_redo(f)
    assert text == "just some text"
    assert session is None


def test_resolve_redo_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        _resolve_redo(tmp_path / "does-not-exist")


def test_resolve_redo_dir_without_transcript_raises(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError):
        _resolve_redo(tmp_path / "empty")


def test_new_flags_parse():
    a = _parse_args(["--doctor"])
    assert a.doctor is True
    assert _parse_args(["--config"]).show_config is True
    assert _parse_args(["--setup"]).setup is True
    assert _parse_args(["--redo", "somedir"]).redo == "somedir"
    assert _parse_args(["--stdout"]).to_stdout is True
    assert _parse_args(["-o"]).open_editor is True
    assert _parse_args(["--open"]).open_editor is True


def test_action_flags_default_false():
    a = _parse_args([])
    assert a.doctor is False and a.show_config is False and a.setup is False
    assert a.redo is None and a.to_stdout is False and a.open_editor is False
