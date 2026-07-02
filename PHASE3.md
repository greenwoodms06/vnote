# Phase 3 — Streaming partials

> Fourth phase of `ROADMAP.md`. Goal: RealtimeSTT-style live text while you
> speak, and a near-instant final at stop — the biggest *perceived*-latency win.

## Objective

Stream audio to the daemon during recording instead of uploading one blob at
the end. The daemon transcribes the growing buffer as it arrives and hands back
interim "partials"; on stop, only the tail is new work, so the final transcript
lands in a few hundred ms. `vnote-flow --stream` shows partials as a live
console line and injects the final as usual.

## Design constraints

- **Still zero new dependencies — so no WebSockets.** stdlib has none, and a
  hand-rolled RFC 6455 isn't worth it for one client. Chunked HTTP does the
  job: a stateful stream session addressed by id, raw PCM chunks in POST
  bodies. (WebSockets can come back in a later phase if latency data demands.)
- **No worker threads in the daemon.** Partials are computed *synchronously on
  append* whenever ≥0.5 s of new audio has arrived — the client pumps from a
  background thread anyway, so a blocking append costs nothing, and the design
  stays deterministic and testable. Whisper re-transcribes the whole buffer
  each pass (no LocalAgreement) — on a warm 4090 that's fine for minutes-long
  dictation; partials just refresh more slowly as the take grows.
- **Partials are best-effort; the final is not.** A failed partial pass is
  swallowed; a failed `finish` makes the client fall back to the Phase-1 batch
  upload — it still holds the full WAV, so streaming can never lose audio.
- **Opt-in (`--stream` / `VNOTE_STREAM=1`)**, same pattern as `--vad`. Composes
  with `--vad`, `--clean`, `--once`.
- Sessions are GC'd after 120 s of inactivity, so crashed clients can't leak
  buffers.

## API addition

```
POST /stream/start                 {"language": null}  → {"session_id": "..."}
POST /stream/append?sid=ID         raw s16le 16 kHz mono PCM chunk
                                   → {"partial": "text so far"}   (may lag; "" at first)
POST /stream/finish?sid=ID         → {"transcript": "...", "meta": {...}}  (drops the session)
```

`append`/`finish` on an unknown or expired sid → 404. `finish` with no audio
→ 400.

## Scope

**In:** the three `/stream/*` endpoints + session GC, `vnote/audio.py`
(shared PCM→WAV helper), `daemon.StreamSession` client, `vnote-flow --stream`
(pump thread + live partial line + batch fallback), tests, README.

**Out (later):** LocalAgreement/context-carry incremental decoding, WebSockets,
streaming partials into the *focused app* (needs erase-and-retype injection),
CLI note-mode streaming, cleanup of partials (final only).

## Acceptance criteria

- [ ] Streamed and batch transcription of the same audio produce the same
      final transcript (live check against `.testdata/jfk.flac`, chunked).
- [ ] Partials evolve as chunks arrive (visible in the live check) and never
      block the recording.
- [ ] `finish` latency for the tail of a long take is well under batch
      re-upload latency (measure in the live check).
- [ ] Killing the session mid-stream (client fallback path) still delivers the
      full transcript via the batch route.
- [ ] Unknown/expired sid → clean client error; sessions GC after the TTL.
- [ ] No new `[project.dependencies]`; ruff + pytest green (CI without heavy
      deps included).
