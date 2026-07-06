# Phase 7 — Promote a take to a note

> Some flow takes aren't micro-utterances — they're real notes that arrived
> via the hotkey. Rather than forking capture with a record-time mode toggle
> (rejected: mode state you must remember before speaking, decided when you
> have the least information), capture stays uniform and *organization*
> becomes an after-the-fact operation: **promote** any logged take into a
> batch-style session folder, built from data the flow history already holds.

## Objective

1. **Promotion machinery** (`vnote/history.py`): `promote_take(...)` parses
   one entry out of a daily flow log (`## HH:MM:SS  (…)` headers are the
   delimiters; `[audio](…)`, `**raw:**`, `**clean:**` fields read back until
   the next marker), then builds a normal session folder via the existing
   `output.make_session_dir()` + `write_session()` — dated-titled name from
   the take's own timestamp plus a slug of the first words of clean-else-raw;
   `audio.wav` **moved** (not copied) out of `flow/audio/`; `transcript.txt`
   = raw (falling back to clean when raw was omitted at capture time — a
   field absent from the entry is simply absent from the folder's sources);
   `note.md` = clean else raw, title = first ~8 words; `meta.json` =
   `{source: "flow-promoted", seconds, mode, tone}` parsed back from the
   header. The log entry's body is then replaced by a single pointer line
   `[note](../<folder-name>/note.md)` under the original header — the daily
   log remains the complete timeline; promoting twice is a clear error.
2. **Take selection**: `"last"` = the final entry of the newest day file;
   `"HH:MM:SS"` = that entry in the newest day file; `"YYYY-MM-DD HH:MM:SS"`
   = explicit. No match → one-line error, log untouched.
3. **A `POST /promote` endpoint** (`{"take": "last"}` etc.) returning the new
   folder name, plus `daemon.promote(take)` in the client library. All
   history mutations (append + promote) serialize on one module-level lock in
   `history.py` — the daemon is the single writer, appends can't interleave
   with a promotion rewrite.
4. **CLI**: `vnote --promote [TAKE]` (bare = `last`), routed through a
   running daemon like everything else, with the usual in-process fallback
   when no daemon is up (safe: no daemon means no concurrent appends).
5. **Tray action** — an action, not a mode: "Save last take as note" pushes a
   `("promote", 0)` event onto the existing queue; the main loop calls
   `daemon.promote("last")` and reports via the console line. No second
   control path; tray callbacks still only push events / flip shared flags.
6. **Version 0.4.0** — a user-visible feature is a minor release.

## Design constraints

- **Capture is untouched.** Phase 6's append path changes only by taking the
  new lock. No new flags, env vars, or payload fields on the capture side.
- **One writer, serialized.** Only the daemon (or the in-process fallback
  when none runs) touches `voice-notes/`; `history._lock` covers every
  read-modify-write of a day file.
- **Parse markers are reserved.** `## HH:MM:SS  (` at line start delimits
  entries; `**raw:**` / `**clean:**` / `[audio](` / `[note](` at line start
  delimit fields. Multi-line dictation (embedded blank lines from "new
  paragraph") must round-trip; dictated prose that itself begins a line with
  a marker is an accepted, documented parse limit.
- **Zero new dependencies**, core `[project.dependencies]` untouched.

## Scope

**In:** `promote_take` + entry parsing + `_lock` in `vnote/history.py`;
`POST /promote` in `server.py`; `daemon.promote()`; `vnote --promote` in
`cli.py` (daemon-first, in-process fallback); the tray action + event
handling in `client/app.py`/`client/tray.py`; tests (parse round-trip with
multi-line text, promote full / audio-less / already-promoted / by-timestamp
/ no-match, endpoint round-trip, CLI + tray wiring); README; version 0.4.0.

**Out:** the record-time `--separate-notes` toggle (rejected above),
demotion (folder → log), bulk promotion, promoting into a custom title,
editing tooling for the daily log.

## Acceptance criteria

- [ ] `vnote --promote` after a dictated take produces
      `voice-notes/<YYYY-MM-DD-HHMM>-<slug>/` containing `audio.wav` (moved
      — gone from `flow/audio/`), `transcript.txt`, `note.md`, `meta.json`,
      and the log entry's body is now a `[note](…)` pointer under its
      original header (manual, user-verified via the tray action too).
- [ ] `--promote HH:MM:SS` selects the right entry; an unknown time or an
      already-promoted take costs one clear error line and leaves every file
      unchanged.
- [ ] A take whose raw/clean text spans multiple lines/paragraphs promotes
      with the text intact; an audio-less take promotes without `audio.wav`.
- [ ] Appends and promotions cannot interleave (single lock; unit-tested or
      enforced by construction and asserted in review).
- [ ] `vnote --version` reports 0.4.0; ruff + pytest green; no new core deps.
