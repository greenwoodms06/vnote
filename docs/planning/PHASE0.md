# Phase 0 — Warm daemon (kickoff spec)

> **How to use this doc:** open a Claude Code session **rooted in this repo**
> (`/mnt/d/Projects/vnote`) and say *"implement PHASE0.md"*. This is the first
> phase of `ROADMAP.md`. It is self-contained; you should not need prior chat
> context.

---

## Objective

Extract the transcribe + clean pipeline behind a **resident localhost daemon**
that keeps the faster-whisper model warm, and make the CLI a **client** of that
daemon **with an in-process fallback**. No user-visible behavior change; the win
is latency — today every `vnote` run cold-loads the Whisper model into VRAM.

**Definition of done:** with `vnote --serve` running in one terminal, repeated
`vnote <file>` runs skip model load and are measurably faster, produce
byte-identical output, and everything still works exactly as before when no
daemon is running.

## Design constraints (respect the project's ethos)

- **Zero new runtime dependencies.** Use the stdlib `http.server` for the
  daemon and `urllib` for the client — the same choice `cleanup.py` already made
  for Ollama. Do **not** add FastAPI/uvicorn/flask/requests.
- **Single-user, localhost only.** Bind to `127.0.0.1`. No auth, no CORS.
- **Serialize inference.** One GPU → guard model calls with a `threading.Lock`
  (CTranslate2 models aren't guaranteed concurrency-safe).
- **Keep the CLI light when the daemon is up:** the daemon path must **not**
  import `transcribe` (i.e. not import `faster_whisper`/CUDA) — that's what makes
  the client start instantly.
- Match the existing code style: stderr status via the `_say`-style pattern,
  short-circuit utility flags like `--doctor`/`--setup`, `from __future__ import
  annotations`, ruff-clean.

## Scope

**In:** `vnote --serve`, `/health` + `/transcribe` + `/clean` endpoints, a
`daemon.py` client, CLI routing with fallback, a `--no-daemon` escape hatch,
`doctor` + `--config` updates, config knobs, tests.

**Out (later phases):** global hotkey, text injection, the Windows/WSL split,
audio-**bytes** upload (Phase 0 passes an audio *path* since client and daemon
share a filesystem), VAD, streaming, auto-spawning the daemon.

---

## Current signatures this builds on (already in the repo)

```python
# vnote/transcribe.py
def transcribe(audio_path: Path, language: str | None = None) -> tuple[str, dict]: ...
_load_model()          # caches the model in a module global (warm for the process)
_device                # "cuda" | "cpu", set after load

# vnote/cleanup.py
def clean(transcript: str, mode="edit", backend="ollama", model=None) -> CleanResult: ...
@dataclass
class CleanResult: title: str; body: str

# vnote/config.py
WHISPER_MODEL, OLLAMA_HOST, CLAUDE_MODEL, NOTES_DIR
def backend() -> str; def ollama_model() -> str
```

The daemon wraps `transcribe()` and `clean()` unchanged; the client mirrors
their signatures so `cli.py` can call either interchangeably.

---

## API contract

All JSON, all on `http://127.0.0.1:<port>` (default port `8760`).

### `GET /health`
→ `200`
```json
{ "status": "ok", "version": "0.1.0", "device": "cuda",
  "whisper_model": "large-v3-turbo", "uptime_s": 12.3 }
```
Used by the CLI to detect a daemon (fast timeout ~0.3 s) and by `doctor`.

### `POST /transcribe`
body: `{ "audio_path": "/abs/path/to/audio.wav", "language": null }`
→ `200` `{ "transcript": "...", "meta": { ...transcribe meta... } }`
→ `400` `{ "error": "no such file: ..." }` · `500` `{ "error": "..." }`

### `POST /clean`
body: `{ "transcript": "...", "mode": "edit", "backend": "ollama", "model": null }`
→ `200` `{ "title": "...", "body": "..." }`
→ `500` `{ "error": "..." }`

---

## Files to add / change

### NEW `vnote/server.py` (reference skeleton — refine as needed)

```python
"""vnote daemon: warm models behind a localhost HTTP API.

Run:  vnote --serve   (foreground; Ctrl-C to stop). Stdlib-only.
Single-user/localhost; inference is serialized behind a lock.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, config

_infer_lock = threading.Lock()
_started = 0.0


def _warm() -> str:
    from .transcribe import _load_model  # heavy import stays inside the daemon
    from . import transcribe
    _load_model()
    return transcribe._device or "cpu"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep the console quiet; we print our own lines
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

    def do_GET(self):
        if self.path == "/health":
            from . import transcribe
            self._send(200, {
                "status": "ok", "version": __version__,
                "device": transcribe._device or "cpu",
                "whisper_model": config.WHISPER_MODEL,
                "uptime_s": round(time.monotonic() - _started, 1),
            })
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            data = self._read_json()
            if self.path == "/transcribe":
                audio = Path(data["audio_path"]).expanduser()
                if not audio.is_file():
                    return self._send(400, {"error": f"no such file: {audio}"})
                from .transcribe import transcribe
                with _infer_lock:
                    text, meta = transcribe(audio, language=data.get("language"))
                self._send(200, {"transcript": text, "meta": meta})
            elif self.path == "/clean":
                from .cleanup import clean
                r = clean(data["transcript"], mode=data.get("mode", "edit"),
                          backend=data.get("backend", "ollama"), model=data.get("model"))
                self._send(200, {"title": r.title, "body": r.body})
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})


def serve() -> int:
    global _started
    host, port = config.daemon_addr()
    _started = time.monotonic()
    print(f"vnote daemon — warming {config.WHISPER_MODEL} ...", flush=True)
    device = _warm()
    print(f"  warm on {device}; listening on http://{host}:{port}  (Ctrl-C to stop)", flush=True)
    httpd = ThreadingHTTPServer((host, port), _Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.")
    finally:
        httpd.server_close()
    return 0
```

### NEW `vnote/daemon.py` (client — light imports only)

```python
"""Client helpers for a running vnote daemon (stdlib urllib)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from . import config
from .cleanup import CleanResult  # light: cleanup.py has no heavy top-level imports


def _base() -> str:
    host, port = config.daemon_addr()
    return f"http://{host}:{port}"


def is_up(timeout: float = 0.3) -> bool:
    try:
        with urllib.request.urlopen(f"{_base()}/health", timeout=timeout) as r:
            return json.loads(r.read()).get("status") == "ok"
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return False


def _post(path: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(f"{_base()}{path}", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


def transcribe(audio_path: Path, language: str | None = None) -> tuple[str, dict]:
    d = _post("/transcribe", {"audio_path": str(audio_path), "language": language}, timeout=600)
    return d["transcript"], d["meta"]


def clean(transcript: str, mode: str = "edit", backend: str = "ollama", model: str | None = None) -> CleanResult:
    d = _post("/clean", {"transcript": transcript, "mode": mode, "backend": backend, "model": model}, timeout=600)
    return CleanResult(title=d["title"], body=d["body"])
```

### CHANGE `vnote/config.py` — add daemon address

```python
DAEMON_HOST = os.environ.get("VNOTE_DAEMON_HOST", "127.0.0.1")
DAEMON_PORT = int(os.environ.get("VNOTE_DAEMON_PORT", "8760"))

def daemon_addr() -> tuple[str, int]:
    return DAEMON_HOST, DAEMON_PORT
```
Also surface both in `cli._show_config()`.

### CHANGE `vnote/cli.py` — route through the daemon, fall back in-process

1. Add args (near the other flags):
   - `--serve` (short-circuit utility action, like `--doctor`).
   - `--no-daemon` (`store_true`) — force in-process for this run.
2. Handle `--serve` in `main()` beside `--doctor`:
   ```python
   if args.serve:
       from . import server
       return server.serve()
   ```
3. Add a resolver and use it for **both** call sites (main flow **and**
   `_do_redo`):
   ```python
   def _pipeline(no_daemon: bool):
       """Return (transcribe_fn, clean_fn): daemon-backed if one is up, else in-process."""
       if not no_daemon:
           from . import daemon
           if daemon.is_up():
               _say("  (using warm daemon)")
               return daemon.transcribe, daemon.clean
       from .transcribe import transcribe
       from .cleanup import clean
       return transcribe, clean
   ```
   Replace the inline `from .transcribe import transcribe` / `from .cleanup
   import clean` uses with `transcribe_fn, clean_fn = _pipeline(args.no_daemon)`
   and call those. `_do_redo` only needs `clean_fn`.

### CHANGE `vnote/doctor.py` — report daemon status

Add a `_check_daemon()` row to `run()`:
```python
from . import daemon
host, port = config.daemon_addr()
if daemon.is_up():
    row = (OK, f"daemon: up at {host}:{port} (models warm)")
else:
    row = (WARN, f"no daemon at {host}:{port} — models load per run; start one: `vnote --serve`")
```

---

## Tests — `tests/test_daemon.py`

Follow the existing pure-logic style (no GPU/mic/network to real services):

- **`is_up()` false** when nothing is listening (point `config.daemon_addr` at a
  closed port via monkeypatch).
- **client round-trip**: start a `ThreadingHTTPServer` on an ephemeral port with
  a stub handler returning canned `/transcribe` and `/clean` JSON; monkeypatch
  `config.daemon_addr` to it; assert `daemon.transcribe` / `daemon.clean` parse
  correctly and that `daemon.clean` returns a `CleanResult`.
- **error propagation**: stub returns `{"error": "..."}` → client raises
  `RuntimeError`.
- **`_pipeline()` routing**: monkeypatch `daemon.is_up` → `True`/`False` and
  assert it returns the daemon vs in-process callables; assert `--no-daemon`
  forces in-process without even calling `is_up`.

Keep GPU/model paths out of CI (same as today).

---

## Acceptance criteria

- [ ] `vnote --serve` warms the model once and logs `warm on cuda`; `GET /health`
      returns `status: ok` with the right device/model.
- [ ] With the daemon up, `vnote .testdata/jfk.flac` output is **identical** to
      the in-process run, and a **second** run is visibly faster (no model-load
      line). Time both: `time vnote --no-daemon .testdata/jfk.flac` vs
      `time vnote .testdata/jfk.flac`.
- [ ] With the daemon down, behavior is **unchanged** from today.
- [ ] `--no-daemon` forces in-process; `vnote --doctor` shows daemon status;
      `vnote --config` shows the daemon address.
- [ ] **No new entries in `[project.dependencies]`.**
- [ ] `uv run ruff check vnote tests` and `uv run pytest -q` pass.

## Suggested commit breakdown

1. `config.py` daemon addr + `--config` display.
2. `server.py` + `--serve`.
3. `daemon.py` client + `cli._pipeline()` routing + `--no-daemon`.
4. `doctor.py` row.
5. `tests/test_daemon.py`.
6. README: a short "Warm daemon (optional, faster)" section.

## Verify by hand (the `/run` or `/verify` skill can drive this)

```bash
uv run vnote --serve                 # terminal A: leave running
uv run vnote --doctor                # terminal B: should show "daemon: up"
time uv run vnote .testdata/jfk.flac # warm — note the time
time uv run vnote --no-daemon .testdata/jfk.flac  # cold — should be slower
```
