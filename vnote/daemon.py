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
    req = urllib.request.Request(
        f"{_base()}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
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


def transcribe(audio_path: Path, language: str | None = None) -> tuple[str, dict]:
    d = _post("/transcribe", {"audio_path": str(audio_path), "language": language}, timeout=600)
    return d["transcript"], d["meta"]


def clean(transcript: str, mode: str = "edit", backend: str = "ollama", model: str | None = None) -> CleanResult:
    d = _post("/clean", {"transcript": transcript, "mode": mode, "backend": backend, "model": model}, timeout=600)
    return CleanResult(title=d["title"], body=d["body"])
