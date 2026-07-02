"""vnote daemon: warm models behind a localhost HTTP API.

Run:  vnote --serve   (foreground; Ctrl-C to stop). Stdlib-only, same as the
Ollama client in cleanup.py. Single-user/localhost by design — no auth — and
inference is serialized behind a lock (one GPU; CTranslate2 models aren't
guaranteed concurrency-safe).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__, config

_infer_lock = threading.Lock()
_started = 0.0


def _warm() -> str:
    from . import transcribe  # heavy CUDA/model import stays inside the daemon

    transcribe._load_model()
    return transcribe._device or "cpu"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # keep the console quiet; we print our own lines
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self) -> None:
        if self.path == "/health":
            from . import transcribe

            self._send(200, {
                "status": "ok",
                "version": __version__,
                "device": transcribe._device or "cpu",
                "whisper_model": config.WHISPER_MODEL,
                "uptime_s": round(time.monotonic() - _started, 1),
            })
        else:
            self._send(404, {"error": "not found"})

    def _transcribe(self, audio: Path, language: str | None) -> None:
        from .transcribe import transcribe

        with _infer_lock:
            text, meta = transcribe(audio, language=language)
        self._send(200, {"transcript": text, "meta": meta})

    def _transcribe_body(self, query: dict[str, list[str]]) -> None:
        """Bytes mode: the request body is the audio itself (client machines don't
        share our filesystem). Written to a temp file for the duration of the call."""
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n <= 0:
            return self._send(400, {"error": "empty audio body"})
        fmt = (query.get("format") or ["wav"])[0].lower()
        if not re.fullmatch(r"[a-z0-9]{1,8}", fmt):
            return self._send(400, {"error": f"bad format: {fmt!r}"})
        language = (query.get("language") or [None])[0]
        fd, name = tempfile.mkstemp(prefix="vnote-upload-", suffix=f".{fmt}")
        tmp = Path(name)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(self.rfile.read(n))
            self._transcribe(tmp, language)
        finally:
            tmp.unlink(missing_ok=True)

    def do_POST(self) -> None:
        try:
            url = urlparse(self.path)
            if url.path == "/transcribe":
                ctype = (self.headers.get("Content-Type") or "").partition(";")[0].strip().lower()
                if ctype == "application/octet-stream" or ctype.startswith("audio/"):
                    return self._transcribe_body(parse_qs(url.query))
                data = self._read_json()
                audio = Path(data["audio_path"]).expanduser()
                if not audio.is_file():
                    return self._send(400, {"error": f"no such file: {audio}"})
                self._transcribe(audio, data.get("language"))
            elif url.path == "/clean":
                data = self._read_json()
                from .cleanup import clean

                result = clean(
                    data["transcript"],
                    mode=data.get("mode", "edit"),
                    backend=data.get("backend", "ollama"),
                    model=data.get("model"),
                )
                self._send(200, {"title": result.title, "body": result.body})
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})


def serve() -> int:
    global _started
    host, port = config.daemon_addr()
    try:
        httpd = ThreadingHTTPServer((host, port), _Handler)  # bind first: fail fast if the port is taken
    except OSError as exc:
        print(f"error: cannot listen on {host}:{port}: {exc}", file=sys.stderr)
        print("       (is another `vnote --serve` already running?)", file=sys.stderr)
        return 1
    _started = time.monotonic()
    print(f"vnote daemon — warming {config.WHISPER_MODEL} ...", flush=True)
    device = _warm()
    print(f"  warm on {device}; listening on http://{host}:{port}  (Ctrl-C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.")
    finally:
        httpd.server_close()
    return 0
