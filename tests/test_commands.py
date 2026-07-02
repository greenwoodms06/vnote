"""Tests for the deterministic spoken-command pre-pass (pure string logic)."""

from vnote.commands import apply_commands


def test_plain_prose_passes_through_unchanged():
    text = "This sentence has no commands in it. Neither does this one."
    assert apply_commands(text) == text


def test_new_line_variants():
    assert apply_commands("foo new line bar") == "foo\nbar"
    assert apply_commands("foo newline bar") == "foo\nbar"
    assert apply_commands("foo, new line, bar") == "foo\nbar"  # pause commas consumed
    assert apply_commands("foo NEW LINE bar") == "foo\nbar"


def test_new_line_keeps_real_trailing_punctuation():
    # the speaker dictated a period, then asked for a line break
    assert apply_commands("First point. New line second point") == "First point.\nsecond point"


def test_new_paragraph():
    assert apply_commands("Intro sentence. New paragraph. The details follow.") == (
        "Intro sentence.\n\nThe details follow."
    )


def test_scratch_that_drops_previous_sentence():
    assert apply_commands("I like apples. Scratch that. I like oranges.") == "I like oranges."


def test_scratch_that_mid_sentence_drops_back_to_boundary():
    assert apply_commands("First part stays. this bit goes scratch that and this stays") == (
        "First part stays. and this stays"
    )


def test_scratch_that_at_start_is_a_noop_delete():
    assert apply_commands("Scratch that. Hello.") == "Hello."


def test_multiple_scratches():
    assert apply_commands("One. Two. Scratch that. Three. Scratch that. Four.") == "One. Four."


def test_scratch_respects_spoken_new_line_boundary():
    # no written punctuation at all — the spoken "new line" is the only boundary
    assert apply_commands("first point new line second point scratch that third point") == (
        "first point\nthird point"
    )


def test_scratch_without_any_boundary_drops_everything_before():
    assert apply_commands("all of this goes scratch that only this stays") == "only this stays"


def test_scratch_in_comma_run_deletes_only_the_last_clause():
    # continuous dictation: Whisper punctuates with commas, no full stops anywhere
    assert apply_commands(
        "today I did stuff, met with John, reviewed the code, scratch that, reviewed the docs"
    ) == "today I did stuff, met with John, reviewed the docs"
