"""Deterministic spoken-command pre-pass for dictation (ROADMAP §5, Phase 2).

Applied to the transcript before (or without) any LLM, so raw flow-mode
injection honors the essentials too. Only commands worth handling by rule live
here — "new line" / "new paragraph" / "scratch that". Punctuation words
("period", "comma") are deliberately left to the dictation LLM prompt: Whisper
usually punctuates already, and "the trial period" must survive. ("new line"
can in principle collide with prose too — accepted, every dictation tool maps
it.)
"""

from __future__ import annotations

import re

# A comma right before the command is a pause artifact ("foo, new line, bar") —
# consume it. A period is real punctuation the speaker asked for — keep it.
_NEW_PARAGRAPH = re.compile(r",?\s*\bnew paragraph\b[,.]?\s*", re.IGNORECASE)
_NEW_LINE = re.compile(r",?\s*\bnew ?line\b[,.]?\s*", re.IGNORECASE)
_SCRATCH = re.compile(r",?\s*\bscratch that\b[,.!]?\s*", re.IGNORECASE)

def _drop_last_sentence(text: str) -> str:
    """Everything up to (and including) the last sentence boundary; '' if there is none."""
    text = text.rstrip().rstrip(".!?")  # a trailing ender belongs to the sentence being dropped
    cut = max(text.rfind(ch) for ch in ".!?\n")
    return text[: cut + 1] if cut != -1 else ""


def apply_commands(text: str) -> str:
    """Apply spoken editing commands; text without commands passes through unchanged."""
    # Line-break commands first, so a spoken "new line" already counts as a
    # sentence boundary when "scratch that" looks backwards for one.
    text = _NEW_PARAGRAPH.sub("\n\n", text)
    text = _NEW_LINE.sub("\n", text)
    while (m := _SCRATCH.search(text)) is not None:
        kept = _drop_last_sentence(text[: m.start()])
        text = f"{kept} {text[m.end():]}".strip()
    return re.sub(r"[ \t]*\n[ \t]*", "\n", text).strip()
