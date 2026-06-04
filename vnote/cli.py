"""``vnote`` — record a voice note (or take an audio file), transcribe, clean up.

    vnote                      record from mic, Enter to stop, transcribe + clean
    vnote memo.m4a             process an existing audio file
    vnote --light / --summary  cleanup intensity (default: --edit)
    vnote --raw                transcript only, skip the LLM cleanup
    vnote --backend claude     use the optional Claude cloud backend instead of Ollama
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from . import __version__, config, firstrun
from .config import CLAUDE_MODEL, DEFAULT_MODE, MODES


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="vnote", description="Local voice notes: record -> transcribe -> tidy up.")
    p.add_argument("audio", nargs="?", help="existing audio file to process; omit to record from the mic")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--light", action="store_const", const="light", dest="mode", help="light cleanup (faithful)")
    mode.add_argument("--edit", action="store_const", const="edit", dest="mode", help="editorial cleanup (default)")
    mode.add_argument("--summary", action="store_const", const="summary", dest="mode", help="condensed rewrite")
    p.add_argument("--raw", action="store_true", help="skip the LLM cleanup; keep only the transcript")
    p.add_argument("--backend", choices=("ollama", "claude"), default=None,
                   help="cleanup backend (default: ollama, or your saved first-run choice)")
    p.add_argument("--model", help="override the cleanup model name")
    p.add_argument("--language", help="force transcription language (e.g. 'en'); default: auto-detect")
    p.add_argument("--no-clipboard", action="store_true", help="do not copy the result to the clipboard")
    p.add_argument("--keep-temp-audio", action="store_true",
                   help="when recording, also keep the temp wav if writing fails")
    p.add_argument("--version", action="version", version=f"vnote {__version__}")
    p.set_defaults(mode=DEFAULT_MODE)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    assert args.mode in MODES

    # First-run setup (interactive TTY only; a no-op otherwise), then resolve the
    # backend: explicit --backend flag > saved choice / env > built-in default.
    firstrun.run(args.backend)
    backend = args.backend or config.backend()

    started = datetime.now()
    tmp_wav: Path | None = None

    # 1. Obtain audio.
    if args.audio:
        audio_path = Path(args.audio).expanduser()
        if not audio_path.is_file():
            print(f"error: no such file: {audio_path}", file=sys.stderr)
            return 2
        print(f"Using audio file: {audio_path}")
        rec_duration = None
    else:
        from .record import record_to_wav

        tmp_wav = Path(tempfile.mkdtemp(prefix="vnote-")) / "audio.wav"
        try:
            rec_duration = record_to_wav(tmp_wav)
        except Exception as exc:  # noqa: BLE001
            print(f"error: recording failed: {exc}", file=sys.stderr)
            return 1
        if rec_duration < 0.5:
            print("Nothing recorded (too short). Aborting.", file=sys.stderr)
            return 1
        print(f"Recorded {rec_duration:.1f}s.")
        audio_path = tmp_wav

    # 2. Transcribe.
    print("Transcribing ...")
    t0 = time.monotonic()
    from .transcribe import transcribe

    try:
        transcript, tmeta = transcribe(audio_path, language=args.language)
    except Exception as exc:  # noqa: BLE001
        print(f"error: transcription failed: {exc}", file=sys.stderr)
        return 1
    transcribe_s = round(time.monotonic() - t0, 1)
    if not transcript:
        print("Transcript is empty (no speech detected?). Aborting.", file=sys.stderr)
        return 1
    print(f"  {len(transcript)} chars in {transcribe_s}s (lang={tmeta.get('language')}).")

    # 3. Clean up (unless --raw).
    note_body: str | None = None
    title: str
    cleanup_s = None
    cleanup_backend = None
    cleanup_model = None
    if args.raw:
        words = transcript.split()
        title = " ".join(words[:6]) if words else "voice note"
    else:
        print(f"Cleaning up via {backend} ({args.mode}) ...")
        t0 = time.monotonic()
        from .cleanup import clean

        try:
            result = clean(transcript, mode=args.mode, backend=backend, model=args.model)
        except (NotImplementedError, RuntimeError, ValueError) as exc:
            print(f"\nCleanup unavailable: {exc}\n", file=sys.stderr)
            print("Keeping the raw transcript instead.", file=sys.stderr)
            words = transcript.split()
            title = " ".join(words[:6]) if words else "voice note"
        else:
            cleanup_s = round(time.monotonic() - t0, 1)
            title = result.title
            note_body = result.body
            cleanup_backend = backend
            cleanup_model = args.model or (config.ollama_model() if backend == "ollama" else CLAUDE_MODEL)
            print(f"  done in {cleanup_s}s.")

    # 4. Write session folder.
    from .output import copy_to_clipboard, make_session_dir, write_session

    session_dir = make_session_dir(title, when=started)
    meta = {
        "created": started.isoformat(timespec="seconds"),
        "source": "file" if args.audio else "mic",
        "source_path": str(audio_path) if args.audio else None,
        "recording_duration_s": rec_duration,
        "transcribe_seconds": transcribe_s,
        "cleanup_mode": None if args.raw else args.mode,
        "cleanup_backend": cleanup_backend,
        "cleanup_model": cleanup_model,
        "cleanup_seconds": cleanup_s,
        "title": title,
        **tmeta,
    }
    written = write_session(
        session_dir,
        audio_src=audio_path,
        transcript=transcript,
        note_md=note_body,
        title=title,
        meta=meta,
    )

    # 5. Clipboard.
    clip_target = note_body if note_body is not None else transcript
    clipped = False
    if not args.no_clipboard:
        clipped = copy_to_clipboard(clip_target if note_body is None else f"# {title}\n\n{note_body.strip()}\n")

    # 6. Report.
    print()
    print(f"📁 {session_dir}")
    for name in ("audio", "transcript", "note", "meta"):
        if name in written:
            print(f"   {name:10s} {written[name].name}")
    if clipped:
        print('   → copied to clipboard')
    elif not args.no_clipboard:
        print('   (clipboard copy failed — no clipboard tool found; see README)')

    # Clean up the temp recording dir; the wav has been copied into the session.
    if tmp_wav is not None and not args.keep_temp_audio:
        try:
            tmp_wav.unlink(missing_ok=True)
            tmp_wav.parent.rmdir()
        except OSError:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
