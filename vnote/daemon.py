"""Client helpers for a running vnote daemon (stdlib urllib).

Deliberately light: importing this must never pull in faster-whisper/CUDA —
that instant startup is the whole point of routing through the daemon.
``transcribe()`` and ``clean()`` mirror the in-process signatures so cli.py
can call either interchangeably.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

from . import config
from .cleanup import CleanResult  # light: cleanup.py has no heavy top-level imports


def _base() -> str:
    host, port = config.daemon_addr()
    return f"http://{host}:{port}"


def health(timeout: float = 0.3) -> dict | None:
    """The daemon's /health payload, or None if nothing (healthy) is listening."""
    try:
        with urllib.request.urlopen(f"{_base()}/health", timeout=timeout) as r:
            data = json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("status") == "ok" else None


def is_up(timeout: float = 0.3) -> bool:
    return health(timeout) is not None


def _request(req: urllib.request.Request, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as exc:  # daemon reports errors as 400/500 JSON bodies
        try:
            detail = json.loads(exc.read()).get("error")
        except (OSError, ValueError):
            detail = None
        raise RuntimeError(detail or f"daemon error: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:  # daemon vanished mid-run
        raise RuntimeError(f"daemon unreachable: {exc.reason}") from exc
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


def _post(path: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        f"{_base()}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return _request(req, timeout)


def transcribe(audio_path: Path, language: str | None = None) -> tuple[str, dict]:
    d = _post("/transcribe", {"audio_path": str(audio_path), "language": language}, timeout=600)
    return d["transcript"], d["meta"]


def transcribe_bytes(data: bytes, fmt: str = "wav", language: str | None = None) -> tuple[str, dict]:
    """Transcribe in-memory audio — for clients that don't share the daemon's filesystem."""
    query = f"?format={quote(fmt)}" + (f"&language={quote(language)}" if language else "")
    req = urllib.request.Request(
        f"{_base()}/transcribe{query}",
        data=data,
        headers={"Content-Type": "application/octet-stream"},
    )
    d = _request(req, timeout=600)
    return d["transcript"], d["meta"]


def clean(transcript: str, mode: str = "edit", backend: str = "ollama", model: str | None = None) -> CleanResult:
    d = _post("/clean", {"transcript": transcript, "mode": mode, "backend": backend, "model": model}, timeout=600)
    return CleanResult(title=d["title"], body=d["body"])
