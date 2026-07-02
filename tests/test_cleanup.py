"""Tests for the transcript-cleanup response parser (pure, no network)."""

import pytest

from vnote import config
from vnote.cleanup import _build_user_prompt, _finish, _parse_response, clean


def test_parse_full_title_and_body():
    raw = "TITLE: My Great Note\n---\nFirst line.\n\nSecond paragraph."
    r = _parse_response(raw, "ignored transcript")
    assert r.title == "My Great Note"
    assert r.body == "First line.\n\nSecond paragraph."


def test_parse_strips_quotes_around_title():
    r = _parse_response('TITLE: "Quoted Title"\n---\nbody', "x")
    assert r.title == "Quoted Title"


def test_parse_fallback_first_line_without_separator():
    raw = "TITLE: No Separator Here\nbut there is a body"
    r = _parse_response(raw, "x")
    assert r.title == "No Separator Here"
    assert r.body == "but there is a body"


def test_parse_no_title_falls_back_to_transcript_words():
    r = _parse_response("just some body with no title marker", "alpha beta gamma delta")
    assert r.title == "alpha beta gamma delta"
    # body is the raw response when no TITLE present
    assert "just some body" in r.body


def test_parse_empty_everything_yields_placeholder_title():
    r = _parse_response("", "")
    assert r.title == "voice note"
    # body falls back to the (empty) transcript
    assert r.body == ""


def test_build_user_prompt_includes_mode_instruction_and_transcript():
    prompt = _build_user_prompt("hello there", "light")
    assert "hello there" in prompt
    assert "filler" in prompt.lower()  # the 'light' instruction mentions filler words


# --- dictation mode (flow client) --------------------------------------------


def test_dictation_finish_is_plain_text_not_title_framed():
    r = _finish("TITLE: looks like a title\n---\nbut dictation takes it verbatim", "orig words here", "dictation")
    assert r.body == "TITLE: looks like a title\n---\nbut dictation takes it verbatim"
    assert r.title == "orig words here"  # fallback title from the transcript; flow ignores it


def test_note_modes_still_parse_title_framing():
    r = _finish("TITLE: A Note\n---\nbody", "x", "edit")
    assert (r.title, r.body) == ("A Note", "body")


def test_dictation_prompt_mentions_spoken_commands():
    prompt = _build_user_prompt("x", "dictation")
    assert "scratch that" in prompt


def test_tone_lands_in_the_prompt():
    assert "Write in a casual tone." in _build_user_prompt("x", "dictation", tone="casual")
    assert "tone" not in _build_user_prompt("x", "light")  # no tone -> no tone sentence


def test_clean_rejects_unknown_mode():
    with pytest.raises(ValueError, match="unknown mode"):
        clean("x", mode="bogus")


def test_dictation_model_resolution_order(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("VNOTE_DICTATION_MODEL", raising=False)
    monkeypatch.delenv("VNOTE_OLLAMA_MODEL", raising=False)

    assert config.dictation_model() == config.ollama_model()  # falls back to the note model
    config.save_config({"dictation_model": "qwen2.5:3b-instruct"})
    assert config.dictation_model() == "qwen2.5:3b-instruct"
    monkeypatch.setenv("VNOTE_DICTATION_MODEL", "llama3.2:3b")
    assert config.dictation_model() == "llama3.2:3b"
