# Phase 1 — Global hotkey + injection (Flow-mode MVP)

> Second phase of `ROADMAP.md`, building on the Phase 0 warm daemon. Goal: the
> Wispr-Flow experience, batch-style — press a hotkey anywhere, speak, press it
> again, and the text lands in the focused app.

## Objective

A thin client (`vnote-flow`) that runs on the machine that owns the keyboard
and mic: global toggle hotkey → record → POST audio **bytes** to the warm
daemon → paste the transcript into the focused app. The CLI and note mode are
untouched.

**Definition of done:** with a daemon up, `vnote-flow` (on a machine with
pynput) toggles recording on `ctrl+shift+space` and pastes the transcript into
whatever has focus; `vnote-flow --once --print` gives a scriptable single cycle
that works over SSH/WSL with no hotkey libs installed.

## Design constraints

- **Zero new core dependencies.** `pynput` lives in an optional `[flow]` extra;
  the client package imports it lazily. Capture reuses `sounddevice` (already a
  core dep) or the `parec`/`pw-record` CLI path on WSL/Linux.
- **The client must not need the daemon's filesystem.** `/transcribe` learns to
  accept raw audio bytes (`Content-Type: application/octet-stream` or
  `audio/*`); JSON requests keep the Phase-0 path behavior, byte-for-byte.
- **Injection is the only OS-specific layer** (roadmap §3). One
  `inject(text, method)` seam; clipboard-paste (save → set → chord → restore)
  is the default, per-char typing the fallback. Per-OS chord senders:
  - WSL → `powershell.exe … SendKeys('^v')` (Windows gets the keystroke)
  - native Windows / macOS / X11 → `pynput` (X11 prefers `xdotool` if present)
  - Wayland → `wtype`, else `ydotool`
- **Hotkey callbacks run on the OS input thread** — they only enqueue events;
  all real work happens on the main thread.
- **Fast by default:** inject the raw transcript; `--clean MODE` opts into the
  daemon's `/clean` (the fast `dictation` profile is Phase 2).

## Scope

**In:** bytes upload on `/transcribe`, `daemon.transcribe_bytes()` +
`daemon.health()`, `vnote/client/` (`capture.py`, `inject.py`, `hotkey.py`,
`app.py`), `vnote-flow` script + `[flow]` extra, `VNOTE_HOTKEY` /
`VNOTE_INJECT` config knobs, doctor row, tests, README.

**Out (later phases):** VAD auto-stop + dictation cleanup profile (P2),
streaming partials (P3), per-app tone & vocabulary (P4), tray/installer (P5),
hold-to-talk mode, auto-spawning the daemon.

## API addition

`POST /transcribe` with a non-JSON `Content-Type` treats the body as audio
bytes; optional query params `format` (container hint, default `wav`) and
`language`. The daemon writes a temp file, transcribes, deletes it:

```
POST /transcribe?format=flac&language=en   (body: raw audio bytes)
→ 200 { "transcript": "...", "meta": { ... } }   · 400 empty body · 500 error
```

## Acceptance criteria

- [ ] `daemon.transcribe_bytes(flac_bytes)` returns the same transcript as the
      path route (verified live against `.testdata/jfk.flac`).
- [ ] JSON `/transcribe` requests behave exactly as in Phase 0.
- [ ] `vnote-flow --help` works without pynput installed; the hotkey loop gives
      a clear install hint when it's missing.
- [ ] `vnote-flow --once --print` runs a full record → daemon → stdout cycle.
- [ ] `vnote --doctor` reports the injection path; `vnote --config` shows
      hotkey + injection settings.
- [ ] No new entries in `[project.dependencies]`; ruff + pytest pass.
