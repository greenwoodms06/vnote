"""LLM cleanup: turn a raw transcript into a tidy, well-organized note.

Pluggable backends: ``ollama`` (local, default) and ``claude`` (optional cloud
backend — needs the ``claude`` extra and ``ANTHROPIC_API_KEY``).
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import CLAUDE_MODEL, OLLAMA_HOST, ollama_model

# --- prompt construction -----------------------------------------------------

_MODE_INSTRUCTIONS = {
    "light": (
        "Lightly clean the transcript: remove filler words (um, uh, you know, like), "
        "false starts and accidental repetitions; fix grammar, punctuation and capitalization; "
        "correct obvious mis-transcriptions using context. Keep the speaker's wording, content "
        "and order intact. Do not reorganize."
    ),
    "edit": (
        "Edit the transcript into a clean, well-organized note: remove filler words, false starts "
        "and repetitions; fix grammar and punctuation; correct obvious mis-transcriptions; group "
        "related thoughts into paragraphs; add headings or bullet lists where the content naturally "
        "calls for it; smooth transitions. Preserve all of the speaker's points and detail — do not "
        "summarize anything away and do not invent content."
    ),
    "summary": (
        "Rewrite the transcript as a tight, well-organized note: everything in 'edit' mode, plus "
        "cut tangents and trim verbose passages so the result is noticeably more concise than the "
        "original while keeping every substantive point. Use headings and bullets freely."
    ),
}

_SYSTEM = (
    "You are an editor that turns spoken, dictated transcripts into clean written notes. "
    "The transcript may contain spoken meta-instructions from the speaker about formatting or edits "
    "(e.g. 'make that a bulleted list', 'scratch that last bit', 'put a heading here'). Follow such "
    "instructions and do not include them as literal text in the output. Write in the speaker's own "
    "voice. Output GitHub-flavored Markdown.\n\n"
    "Respond in exactly this format and nothing else:\n"
    "TITLE: <a short 3-7 word title>\n"
    "---\n"
    "<the cleaned note in Markdown>"
)


def _build_user_prompt(transcript: str, mode: str) -> str:
    return f"{_MODE_INSTRUCTIONS[mode]}\n\nTRANSCRIPT:\n\"\"\"\n{transcript}\n\"\"\""


def _parse_response(raw: str, transcript: str) -> CleanResult:
    raw = raw.strip()
    title = None
    body = raw
    m = re.match(r"\s*TITLE:\s*(.+?)\s*\n\s*-{3,}\s*\n(.*)", raw, re.DOTALL)
    if m:
        title = m.group(1).strip().strip("\"'")
        body = m.group(2).strip()
    else:
        # Fallback: maybe just "TITLE: ..." on line 1, rest is body.
        first, _, rest = raw.partition("\n")
        fm = re.match(r"\s*TITLE:\s*(.+)", first)
        if fm and rest.strip():
            title = fm.group(1).strip().strip("\"'")
            body = rest.strip()
    if not title:
        words = re.findall(r"[A-Za-z0-9']+", transcript)
        title = " ".join(words[:6]) if words else "voice note"
    return CleanResult(title=title, body=body or transcript)


@dataclass
class CleanResult:
    title: str
    body: str


# --- backends ----------------------------------------------------------------


def clean(transcript: str, mode: str = "edit", backend: str = "ollama", model: str | None = None) -> CleanResult:
    if backend == "ollama":
        return _clean_ollama(transcript, mode, model or ollama_model())
    if backend == "claude":
        return _clean_claude(transcript, mode, model or CLAUDE_MODEL)
    raise ValueError(f"unknown backend: {backend!r} (expected 'ollama' or 'claude')")


# --- Ollama ---


def _ollama_get(path: str, timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}{path}", timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return None


def _ensure_ollama_running() -> None:
    if _ollama_get("/api/version") is not None:
        return
    print("  starting ollama serve ...")
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ollama is not installed or not on PATH (see https://ollama.com)") from exc
    for _ in range(40):  # up to ~10s
        time.sleep(0.25)
        if _ollama_get("/api/version") is not None:
            return
    raise RuntimeError("ollama serve did not come up; try running 'ollama serve' manually")


def _ensure_model_present(model: str) -> None:
    tags = _ollama_get("/api/tags", timeout=5.0) or {}
    names = {m.get("name", "") for m in tags.get("models", [])}
    # Ollama lists e.g. "qwen2.5:14b-instruct"; also accept the bare base name.
    if model in names or any(n == model or n.startswith(model + ":") for n in names):
        return
    raise RuntimeError(
        f"Ollama model {model!r} is not pulled yet.\n"
        f"    Run once:  ollama pull {model}"
    )


def _clean_ollama(transcript: str, mode: str, model: str) -> CleanResult:
    _ensure_ollama_running()
    _ensure_model_present(model)
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.3},
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _build_user_prompt(transcript, mode)},
        ],
    }
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read())
    content = (data.get("message") or {}).get("content", "")
    if not content.strip():
        raise RuntimeError(f"empty response from Ollama model {model!r}")
    return _parse_response(content, transcript)


# --- Claude (optional cloud backend) ---


def _clean_claude(transcript: str, mode: str, model: str) -> CleanResult:
    """Clean up via the Anthropic API. Opt-in: needs the `claude` extra + a key.

    Reuses the same system prompt, user prompt and response parser as the local
    backend so the two produce the same TITLE/--- output shape.
    """
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "The Claude backend needs the `anthropic` package.\n"
            "    Install the extra:  uv pip install -e '.[claude]'   (or: uv pip install anthropic)\n"
            "    Or use the default local backend:  --backend ollama"
        ) from exc

    try:
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    except Exception as exc:  # noqa: BLE001 - SDK raises if no key is configured
        raise RuntimeError(
            f"Could not initialize the Anthropic client: {exc}\n"
            "    Set ANTHROPIC_API_KEY (see .env.example), or use --backend ollama."
        ) from exc

    try:
        resp = client.messages.create(
            model=model,
            max_tokens=8192,
            temperature=0.3,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _build_user_prompt(transcript, mode)}],
        )
    except anthropic.APIError as exc:
        raise RuntimeError(f"Anthropic API error: {exc}") from exc

    content = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
    if not content.strip():
        raise RuntimeError(f"empty response from Claude model {model!r}")
    return _parse_response(content, transcript)
