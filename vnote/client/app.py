"""``vnote-flow`` — dictate into the focused app via a running vnote daemon.

    vnote-flow                 press ctrl+shift+space to talk, again to stop & paste
    vnote-flow --once          one cycle, no hotkey: record now, press Enter to stop
    vnote-flow --print         print the text to stdout instead of pasting
    vnote-flow --clean edit    LLM-clean the transcript before pasting (default: raw)

Runs on the machine that owns the keyboard and mic. On WSL setups that's the
Windows side — install `vnote[flow]` under Windows Python and point
VNOTE_DAEMON_HOST/PORT at the WSL daemon (plain localhost works under NAT).
Requires a running daemon (`vnote --serve`); this client stays thin on purpose.
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time

from .. import __version__, config, daemon
from ..commands import apply_commands
from ..config import MODES
from .capture import Recorder
from .inject import inject

MIN_SECONDS = 0.5  # same too-short guard as the CLI


def _say(*args: object) -> None:
    print(*args, file=sys.stderr)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="vnote-flow", description="Global push-to-talk dictation via the vnote daemon.")
    p.add_argument("--hotkey", default=config.HOTKEY,
                   help=f"toggle combo (default: {config.HOTKEY}; env VNOTE_HOTKEY)")
    p.add_argument("--clean", nargs="?", const="dictation", choices=("dictation", *MODES), default=None,
                   help="LLM-clean before injecting: bare --clean means the fast dictation profile "
                        "(default: raw transcript)")
    p.add_argument("--backend", choices=("ollama", "claude"), default=None, help="cleanup backend for --clean")
    p.add_argument("--model", help="override the cleanup model for --clean")
    p.add_argument("--language", help="force transcription language (e.g. 'en'); default: auto-detect")
    p.add_argument("--inject", choices=("auto", "paste", "type"), default=config.INJECT, dest="inject_method",
                   help="how to put text into the focused app (default: %(default)s; env VNOTE_INJECT)")
    p.add_argument("--print", action="store_true", dest="to_stdout",
                   help="print the text to stdout instead of injecting it")
    p.add_argument("--once", action="store_true",
                   help="single cycle without a hotkey: record now, press Enter to stop")
    p.add_argument("--version", action="version", version=f"vnote-flow {__version__}")
    return p.parse_args(argv)


def _process(wav: bytes, seconds: float, args: argparse.Namespace) -> None:
    """One utterance: bytes -> daemon -> (optional clean) -> inject/print."""
    if seconds < MIN_SECONDS:
        _say("  (too short; ignored)")
        return
    t0 = time.monotonic()
    try:
        text, _meta = daemon.transcribe_bytes(wav, language=args.language)
    except RuntimeError as exc:
        _say(f"error: transcription failed: {exc}")
        return
    text = apply_commands(text.strip())
    if not text:
        _say("  (no speech detected)")
        return
    if args.clean:
        try:
            result = daemon.clean(text, mode=args.clean, backend=args.backend or config.backend(), model=args.model)
            text = result.body.strip()  # body only — no title header when typing into an app
        except RuntimeError as exc:
            _say(f"  (cleanup failed: {exc}; using the raw transcript)")
    _say(f"  {len(text)} chars in {round(time.monotonic() - t0, 1)}s")
    if args.to_stdout:
        print(text, flush=True)
    elif inject(text, method=args.inject_method):
        _say("  → injected")
    else:
        _say("  (injection failed — the text may still be on the clipboard)")


def _run_once(args: argparse.Namespace) -> int:
    rec = Recorder()
    rec.start()
    _say("● recording — press Enter to stop.")
    try:
        input()
    except EOFError:
        pass
    wav, seconds = rec.stop()
    _say(f"  {seconds:.1f}s recorded.")
    _process(wav, seconds, args)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    health = daemon.health()
    if health is None:
        host, port = config.daemon_addr()
        print(f"error: no vnote daemon at {host}:{port} — start one first:  vnote --serve", file=sys.stderr)
        return 1
    host, port = config.daemon_addr()
    _say(f"vnote-flow → daemon at {host}:{port} ({health.get('whisper_model')} on {health.get('device')})")

    if args.once:
        return _run_once(args)

    # Validate the hotkey setup before starting the listener thread.
    from .hotkey import ensure_available, listen, to_pynput

    try:
        ensure_available()
        to_pynput(args.hotkey)
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    events: queue.Queue[str] = queue.Queue()
    listen_error: list[BaseException] = []

    def _listen() -> None:  # pynput can still die at runtime (e.g. display gone)
        try:
            listen(args.hotkey, lambda: events.put("toggle"))
        except BaseException as exc:  # noqa: BLE001
            listen_error.append(exc)
            events.put("quit")

    threading.Thread(target=_listen, daemon=True).start()
    _say(f"ready — press {args.hotkey} to dictate, again to stop (Ctrl-C quits).")

    recorder: Recorder | None = None
    try:
        while True:
            if events.get() == "quit":
                print(f"error: hotkey listener failed: {listen_error[0]}", file=sys.stderr)
                return 1
            if recorder is None:
                recorder = Recorder()
                recorder.start()
                _say("● recording — press the hotkey again to stop.")
            else:
                wav, seconds = recorder.stop()
                recorder = None
                _say(f"  {seconds:.1f}s recorded.")
                _process(wav, seconds, args)
                _say("ready.")
    except KeyboardInterrupt:
        _say("\nbye.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
