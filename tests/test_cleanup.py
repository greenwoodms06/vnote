"""Tests for the transcript-cleanup response parser (pure, no network)."""

from vnote.cleanup import _build_user_prompt, _parse_response


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
