# Phase 6 — Flow history

> First post-roadmap phase (ROADMAP §9: "a lightweight flow-mode history").
> Flow mode is paste-and-forget today — batch note sessions are the only
> record. Save every dictated take (audio, raw transcript, cleaned text) into
> an append-only daily log so dictation can be reviewed and reused, without
> the folder-per-utterance spam ROADMAP §6 ruled out.

## Objective

1. **A daemon-side history store** (`vnote/history.py`): `NOTES_DIR/flow/`
   holds one Markdown file per day (`2026-07-06.md`; one `##` entry per take
   with time, duration, mode/tone, audio link, raw, clean) and a flat
   date-stamped audio directory (`audio/20260706-143207.wav`; `-2` suffix on
   a same-second collision). Flat names can't collide across days and sort
   chronologically.
2. **A `POST /history` endpoint** taking JSON
   `{wav_b64, raw, clean, seconds, mode, tone}` (any of wav_b64/raw/clean may
   be null). The daemon writes the audio first, then the log entry that links
   it — no dangling links. The `server.py` handler is a thin parse-and-call.
3. **Client plumbing**: after delivering a take — batch, streamed, or
   `--once`; injected, printed, or failed injection — the client fires one
   best-effort `daemon.log_history(...)`. `raw` is the ASR transcript
   captured *before* the spoken-command pre-pass and cleanup (that's what
   makes `--clean` judgeable later); `clean` is sent only when cleanup ran.
   Takes under `MIN_SECONDS` stay ignored, as today.
4. **Toggles, everything on by default**: `--no-history` on the CLI skips the
   POST entirely and appears in the tray menu beside the cleanup/VAD toggles
   (same shared-flag pattern — no second control path). Granular switches
   are client-side env vars following the existing `VNOTE_VAD` pattern
   (env-only — no new config.json keys this phase):
   `VNOTE_HISTORY_AUDIO=0` sends no audio, `VNOTE_HISTORY_RAW=0` /
   `VNOTE_HISTORY_CLEAN=0` omit those fields. Policy lives in the client;
   the daemon writes whatever arrives.
5. **Version 0.3.0** — a user-visible feature is a minor release.

## Design constraints

- **Zero new dependencies.** base64 + json + pathlib; core
  `[project.dependencies]` untouched, `[flow]` extra untouched.
- **Dictation never blocks on history.** The POST happens after
  injection/print, with a short timeout; every failure is exactly one console
  line (`history save failed: ...`) and never an exception out of `_deliver`.
- **One writer.** Only the daemon touches `NOTES_DIR/flow/`. The client stays
  thin and keeps working unchanged if client and daemon ever sit on different
  machines.
- **No folder spam.** ROADMAP §6's decision stands: a day of dictation is one
  Markdown file plus flat audio files — never a folder per utterance.

## Scope

**In:** `vnote/history.py`, `POST /history` in `server.py`,
`daemon.log_history()`, threading `wav`/`seconds` into `client/app.py`'s
`_deliver`, the tray toggle, the three env/config switches, tests
(`test_history.py`, `/history` round-trip in `test_server.py`, client wiring
in `test_flow.py`), a README history section, version 0.3.0.

**Out:** retention/pruning, audio compression (FLAC), any history-browsing
UI, changes to batch note sessions, re-clean/re-transcribe tooling.

## Acceptance criteria

- [ ] A hotkey take with `--clean` lands in `voice-notes/flow/<today>.md`
      with raw text, cleaned text, and a working audio link (manual,
      user-verified).
- [ ] `--no-history` (flag or tray toggle) produces no POST and no files;
      `VNOTE_HISTORY_AUDIO=0` logs text with no audio file or link;
      `VNOTE_HISTORY_RAW=0` / `VNOTE_HISTORY_CLEAN=0` omit their fields.
- [ ] Streamed and batch takes produce equivalent history entries; a failed
      injection still logs its take.
- [ ] A `/history` failure costs one console line and the take is still
      delivered.
- [ ] Same-second takes get a `-2`-suffixed audio name; a take after midnight
      starts a new daily file.
- [ ] `vnote --version` reports 0.3.0; ruff + pytest green; no new core deps.
