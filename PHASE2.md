# Phase 2 — VAD auto-stop + fast dictation cleanup

> Third phase of `ROADMAP.md`, on top of the Phase 1 flow client. Goal: hands-off
> endpointing (stop talking → text appears) and a cleanup pass fast enough for
> dictate-anywhere.

## Objective

Three additive pieces:

1. **Silero VAD auto-stop** — in flow mode, recording stops by itself after a
   trailing-silence window; no second hotkey press needed. Opt-in via `--vad`.
2. **A `dictation` cleanup mode** — a light prompt (punctuation, fillers, obey
   spoken commands, *no* TITLE/reorganization) on a small warm model, so cleaned
   dictation costs a few hundred ms instead of a 14B editorial pass.
3. **A deterministic spoken-command pre-pass** (`vnote/commands.py`) — "new
   line", "new paragraph", "scratch that" handled by string rules before (or
   without) any LLM, so `--raw`-style flow injection gets them too.

## Design constraints

- **Zero new dependencies, again.** Silero VAD ships inside faster-whisper
  (`faster_whisper.vad.get_speech_timestamps`, ONNX model bundled, onnxruntime
  already a transitive dep). The client machine has faster-whisper installed —
  it's a core dep — so client-side VAD costs one lazy import, no model load.
- **VAD is opt-in (`--vad` / `VNOTE_VAD=1`)**: a silence cutoff mid-thought is
  worse than a second key press; the toggle stays the default. The hotkey still
  force-stops a `--vad` recording.
- **Deterministic commands stay conservative.** Only rules that can't misfire on
  normal prose: `new line` / `new paragraph` / `scratch that`. Punctuation words
  ("period", "comma") are left to the dictation LLM prompt — Whisper usually
  punctuates already, and "the trial period" must survive.
- **`dictation` is a mode, not a new axis.** `clean(mode="dictation")` uses its
  own system prompt (plain text out, no TITLE) and its own default model
  (`VNOTE_DICTATION_MODEL` > config `dictation_model` > the regular Ollama
  model). The note-mode CLI (`--light/--edit/--summary`) is untouched; the
  daemon's `/clean` passes `mode` through unchanged.

## Scope

**In:** `vnote/vad.py` (trailing-silence endpointing over raw PCM),
`Recorder.pcm_snapshot()`, `--vad` + `--vad-silence` in `vnote-flow`,
`dictation` mode in `cleanup.py` + `config.dictation_model()`,
`vnote/commands.py` pre-pass wired into the flow client, tests, README.

**Out (later):** streaming partials (P3), per-app tone/vocabulary (P4), VAD in
the note-mode CLI, continuous/always-listening mode, punctuation-word commands.

## Acceptance criteria

- [ ] `vad.should_stop()` is False on silence-only and mid-speech audio, True
      once ≥`silence_s` of trailing silence follows real speech (verified live
      against `.testdata/jfk.flac`).
- [ ] `vnote-flow --vad`: hotkey once, speak, pause → auto-stop, text lands.
- [ ] `clean(mode="dictation")` returns plain text (no `TITLE:`), and the live
      daemon `/clean` round-trip works against local Ollama.
- [ ] `apply_commands("foo new line bar")` → `"foo\nbar"`; "scratch that" drops
      the previous sentence; plain prose passes through byte-identical.
- [ ] CI stays green with no heavy deps installed (VAD tests skip cleanly).
- [ ] No new entries in `[project.dependencies]`; ruff + pytest pass.
