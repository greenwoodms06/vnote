"""Tests for the custom-vocabulary dictionary (pure logic; the model is faked)."""

from types import SimpleNamespace

import pytest

from vnote import transcribe, vocab

_VOCAB = """\
# my terms
TRANSFORM
Dymola

jason -> JSON
v note -> vnote
"""


@pytest.fixture
def vocab_file(tmp_path, monkeypatch):
    path = tmp_path / "vocab.txt"
    path.write_text(_VOCAB, encoding="utf-8")
    monkeypatch.setenv("VNOTE_VOCAB", str(path))
    monkeypatch.setattr(vocab, "_cache", None)
    return path


def test_missing_file_is_empty_vocab(tmp_path, monkeypatch):
    monkeypatch.setenv("VNOTE_VOCAB", str(tmp_path / "nope.txt"))
    monkeypatch.setattr(vocab, "_cache", None)
    assert vocab.hotwords_string() is None
    assert vocab.apply_corrections("jason stays") == "jason stays"


def test_hotwords_and_corrections_parse(vocab_file):
    assert vocab.hotwords_string() == "TRANSFORM, Dymola"
    assert vocab.apply_corrections("tell jason about the v note tool") == "tell JSON about the vnote tool"


def test_corrections_are_whole_word_and_case_insensitive(vocab_file):
    assert vocab.apply_corrections("Jason said hi") == "JSON said hi"
    assert vocab.apply_corrections("jasonx is not matched") == "jasonx is not matched"


def test_edits_apply_without_restart(vocab_file):
    import os
    import time

    assert vocab.hotwords_string() == "TRANSFORM, Dymola"
    vocab_file.write_text("OnlyWord\n", encoding="utf-8")
    os.utime(vocab_file, (time.time() + 2, time.time() + 2))  # ensure the mtime moves
    assert vocab.hotwords_string() == "OnlyWord"


def test_transcribe_passes_hotwords_and_applies_corrections(vocab_file, monkeypatch):
    seen = {}

    def fake_run(model, audio_path, language, hotwords=None):
        seen["hotwords"] = hotwords
        info = SimpleNamespace(language="en", language_probability=0.9, duration=1.0)
        return "ask jason about the v note daemon", info

    monkeypatch.setattr(transcribe, "_load_model", lambda: object())
    monkeypatch.setattr(transcribe, "_run", fake_run)
    text, meta = transcribe.transcribe("fake.wav")
    assert seen["hotwords"] == "TRANSFORM, Dymola"
    assert text == "ask JSON about the vnote daemon"
    assert meta["language"] == "en"
