# Phase 4 — Personalization: custom vocabulary + tone

> Fifth phase of `ROADMAP.md`. Wispr's differentiator, done locally: make the
> pipeline learn *your* words and match the register of the app you're
> dictating into.

## Objective

1. **Custom vocabulary** (`vnote/vocab.py`): a plain-text user dictionary that
   (a) biases ASR toward your terms via faster-whisper `hotwords`, and
   (b) applies deterministic corrections to the transcript afterwards.
   Benefits every path — CLI notes, daemon batch, and streaming partials.
2. **Tone** — a `tone` knob on `clean()` appended to the prompt
   (`vnote-flow --tone casual`), plus **per-app auto-tone**: read the focused
   window's title at delivery time and match it against an `app_tones` map in
   the config file (e.g. `"slack" → "casual"`, `"outlook" → "formal"`).

## The vocabulary file

`~/.config/vnote/vocab.txt` (override: `VNOTE_VOCAB`), one entry per line:

```
# bare line = hotword: bias transcription toward this spelling
TRANSFORM
Dymola
WSLg

# left -> right = correction, applied to the transcript (case-insensitive, whole-word)
jason -> JSON
v note -> vnote
```

Loaded with an mtime cache — edit the file and the next utterance uses it; no
daemon restart. Hotwords are passed to `model.transcribe(hotwords=...)`
(supported since faster-whisper 1.0; we ship 1.2.1); corrections run inside
`transcribe()` so partials and finals both get them.

## Design constraints

- **Zero new dependencies**, as always. Window-title detection is best-effort
  per platform (powershell user32 snippet on WSL/Windows, `xdotool` on X11,
  `osascript` on macOS, none on Wayland) and returns `None` rather than fail.
- **The window title is only fetched when it can matter** — `--clean` active,
  no explicit `--tone`, and a non-empty `app_tones` config — since it costs a
  powershell spawn (~0.5 s) per utterance on WSL.
- **Corrections are deterministic and conservative**: whole-word,
  case-insensitive, replacement text used verbatim. No fuzzy matching.
- Tone is free text injected as "Write in a … tone." — presets are just
  documentation, not code.

## Scope

**In:** `vnote/vocab.py` (+ wiring in `transcribe.py`), `tone` through
`clean()` / `/clean` / `daemon.clean()`, `vnote-flow --tone`,
`client/window.py` + `config.app_tone_for()`, `--config` shows the vocab path,
tests, README.

**Out (later):** learned corrections mined from user edits, `initial_prompt`
style priming, per-app formatting beyond tone, editing vocab via a UI.

## Acceptance criteria

- [ ] With `jason -> JSON` in vocab.txt, a transcript containing "jason" is
      corrected in both batch and streamed paths (live check).
- [ ] Hotwords reach `model.transcribe` (unit check; ASR-quality effect is
      inherently probabilistic).
- [ ] `clean(tone="casual")` changes the prompt; `vnote-flow --tone` and an
      `app_tones` match both reach the daemon (live check for the flag).
- [ ] Editing vocab.txt takes effect without restarting the daemon.
- [ ] No new `[project.dependencies]`; ruff + pytest green, CI-safe.
