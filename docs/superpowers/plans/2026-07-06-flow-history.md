# Flow History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save every flow-mode dictation take — audio, raw transcript, cleaned text — into an append-only daily log under `voice-notes/flow/`, on by default with a master flag and granular env switches (spec: `PHASE6.md`).

**Architecture:** The client (the only place a take's audio + raw + cleaned coexist) fires one best-effort `POST /history` after delivering each take; a new daemon-side `vnote/history.py` writes one Markdown file per day plus flat date-stamped WAVs. Policy (what to send) is client-side; mechanism (writing) is daemon-side.

**Tech Stack:** Python stdlib only (base64/json/pathlib/datetime). Zero new dependencies — core `[project.dependencies]` and the `[flow]` extra stay untouched.

**Repo-specific rules (read first):**
- Run tests as `uv run python -m pytest` — NEVER bare `uv run pytest` (resolves to the wrong Python and silently skips suites). Never pipe pytest through `tail`/`head` (masks the exit code).
- This repo sits on a Windows DrvFs mount: after `git add` of any NEW file, run `git update-index --chmod=-x <file>` or it enters git executable.
- Restarting the daemon for manual checks: stop it by port (`ss -ltnp | grep 8760`), never `pgrep -f`/pattern-kill.

---

### Task 1: `vnote/history.py` — the daemon-side writer

**Files:**
- Create: `vnote/history.py`
- Test: `tests/test_history.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history.py`:

```python
"""Tests for the flow-history writer: entry format, day files, audio naming."""

from datetime import datetime

from vnote import history

WHEN = datetime(2026, 7, 6, 14, 32, 7)


def _flow_root(monkeypatch, tmp_path):
    monkeypatch.setattr(history, "NOTES_DIR", tmp_path)
    return tmp_path / "flow"


def test_full_take_writes_audio_then_linked_entry(monkeypatch, tmp_path):
    flow = _flow_root(monkeypatch, tmp_path)
    day = history.append_take(raw="um hello", clean="Hello.", wav=b"RIFF",
                              seconds=4.9, mode="dictation", tone="casual", when=WHEN)
    assert day == flow / "2026-07-06.md"
    audio = flow / "audio" / "20260706-143207.wav"
    assert audio.read_bytes() == b"RIFF"
    text = day.read_text(encoding="utf-8")
    assert "## 14:32:07  (4.9s, clean=dictation, tone=casual)" in text
    assert "[audio](audio/20260706-143207.wav)" in text
    assert "**raw:** um hello" in text
    assert "**clean:** Hello." in text


def test_raw_only_take_without_audio(monkeypatch, tmp_path):
    flow = _flow_root(monkeypatch, tmp_path)
    day = history.append_take(raw="hi", clean=None, wav=None,
                              seconds=2.1, mode=None, tone=None, when=WHEN)
    text = day.read_text(encoding="utf-8")
    assert "## 14:32:07  (2.1s, raw)" in text
    assert "audio" not in text and not (flow / "audio").exists()
    assert "**clean:**" not in text


def test_same_second_collision_suffixes(monkeypatch, tmp_path):
    flow = _flow_root(monkeypatch, tmp_path)
    history.append_take(raw="a", clean=None, wav=b"ONE", seconds=1.0, mode=None, tone=None, when=WHEN)
    history.append_take(raw="b", clean=None, wav=b"TWO", seconds=1.0, mode=None, tone=None, when=WHEN)
    assert (flow / "audio" / "20260706-143207.wav").read_bytes() == b"ONE"
    assert (flow / "audio" / "20260706-143207-2.wav").read_bytes() == b"TWO"


def test_takes_append_and_days_roll_over(monkeypatch, tmp_path):
    flow = _flow_root(monkeypatch, tmp_path)
    history.append_take(raw="one", clean=None, wav=None, seconds=1.0, mode=None, tone=None, when=WHEN)
    history.append_take(raw="two", clean=None, wav=None, seconds=1.0, mode=None, tone=None,
                        when=datetime(2026, 7, 7, 0, 0, 1))
    assert "**raw:** one" in (flow / "2026-07-06.md").read_text(encoding="utf-8")
    assert "**raw:** two" in (flow / "2026-07-07.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_history.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vnote.history'` (or ImportError at collection).

- [ ] **Step 3: Write the implementation**

Create `vnote/history.py`:

```python
"""Append-only flow-dictation history under NOTES_DIR/flow/.

One Markdown file per day plus a flat, date-stamped audio directory — a day
of dictation is one file, never a folder per utterance (ROADMAP §6/§9).
Only the daemon writes here; clients send takes through POST /history.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import NOTES_DIR


def _free_audio_path(base: Path, when: datetime) -> Path:
    """First unused date-stamped name: -2, -3, ... on same-second collisions."""
    stem = when.strftime("%Y%m%d-%H%M%S")
    path = base / f"{stem}.wav"
    n = 2
    while path.exists():
        path = base / f"{stem}-{n}.wav"
        n += 1
    return path


def append_take(
    raw: str | None,
    clean: str | None,
    wav: bytes | None,
    seconds: float,
    mode: str | None,
    tone: str | None,
    when: datetime | None = None,
) -> Path:
    """Write one take — audio first, then the day's entry linking it — and
    return the day file. None fields are simply omitted from the entry."""
    when = when or datetime.now()
    flow = NOTES_DIR / "flow"
    audio = None
    if wav:
        audio = _free_audio_path(flow / "audio", when)
        audio.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(wav)
    head = [f"{seconds:.1f}s", f"clean={mode}" if mode else "raw"]
    if tone:
        head.append(f"tone={tone}")
    entry = [f"## {when:%H:%M:%S}  ({', '.join(head)})"]
    if audio is not None:
        entry.append(f"[audio](audio/{audio.name})")
    if raw is not None:
        entry.append(f"**raw:** {raw}")
    if clean is not None:
        entry.append(f"**clean:** {clean}")
    day = flow / f"{when:%Y-%m-%d}.md"
    day.parent.mkdir(parents=True, exist_ok=True)
    with day.open("a", encoding="utf-8") as f:
        f.write("\n\n".join(entry) + "\n\n")
    return day
```

Note `NOTES_DIR` is imported by value on purpose — tests (and the server tests in Task 2) monkeypatch `history.NOTES_DIR`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_history.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add vnote/history.py tests/test_history.py
git update-index --chmod=-x vnote/history.py tests/test_history.py
git commit -m "feat: flow-history writer — daily Markdown log + date-stamped audio

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `POST /history` endpoint + `daemon.log_history()` client

**Files:**
- Modify: `vnote/server.py` (import block + the `do_POST` route chain, currently `vnote/server.py:163`)
- Modify: `vnote/daemon.py` (import block + new function at the end)
- Test: `tests/test_server.py` (append at end)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
# --- flow history ----------------------------------------------------------------


def test_history_round_trip(live_server, tmp_path, monkeypatch):
    from vnote import history

    monkeypatch.setattr(history, "NOTES_DIR", tmp_path)
    daemon.log_history(wav=b"RIFFDATA", raw="um hello", clean="Hello.",
                       seconds=3.2, mode="dictation", tone="casual")
    md = next((tmp_path / "flow").glob("*.md")).read_text(encoding="utf-8")
    assert "**raw:** um hello" in md and "**clean:** Hello." in md
    wavs = list((tmp_path / "flow" / "audio").glob("*.wav"))
    assert len(wavs) == 1 and wavs[0].read_bytes() == b"RIFFDATA"
    assert f"[audio](audio/{wavs[0].name})" in md


def test_history_without_audio_writes_text_only(live_server, tmp_path, monkeypatch):
    from vnote import history

    monkeypatch.setattr(history, "NOTES_DIR", tmp_path)
    daemon.log_history(wav=None, raw="just text", clean=None, seconds=1.5)
    md = next((tmp_path / "flow").glob("*.md")).read_text(encoding="utf-8")
    assert "**raw:** just text" in md
    assert not (tmp_path / "flow" / "audio").exists()
```

(The monkeypatch works because the `/history` handler imports `history` lazily at call time, matching how the other handlers import `transcribe`/`clean`.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_server.py -v -k history`
Expected: FAIL — `AttributeError: module 'vnote.daemon' has no attribute 'log_history'`.

- [ ] **Step 3: Implement the endpoint and the client function**

In `vnote/daemon.py`, change the import block (top of file) from:

```python
import json
import urllib.error
import urllib.request
```

to:

```python
import base64
import json
import urllib.error
import urllib.request
```

and append at the end of `vnote/daemon.py`:

```python
def log_history(
    wav: bytes | None,
    raw: str | None,
    clean: str | None,
    seconds: float,
    mode: str | None = None,
    tone: str | None = None,
) -> None:
    """Save one flow take to the daemon's history store (voice-notes/flow/)."""
    payload = {
        "wav_b64": base64.b64encode(wav).decode() if wav else None,
        "raw": raw,
        "clean": clean,
        "seconds": seconds,
        "mode": mode,
        "tone": tone,
    }
    _post("/history", payload, timeout=30)
```

In `vnote/server.py`, add `import base64` to the stdlib import block (top of file, alphabetical). Then in `do_POST` (`vnote/server.py:163`), add a route branch after the `elif url.path == "/clean":` block's `self._send(...)` line and before `elif url.path == "/stream/start":`:

```python
            elif url.path == "/history":
                data = self._read_json()
                from . import history

                history.append_take(
                    raw=data.get("raw"),
                    clean=data.get("clean"),
                    wav=base64.b64decode(data["wav_b64"]) if data.get("wav_b64") else None,
                    seconds=float(data.get("seconds") or 0.0),
                    mode=data.get("mode"),
                    tone=data.get("tone"),
                )
                self._send(200, {"saved": True})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_server.py -v`
Expected: all pass (the two new tests plus the existing ones).

- [ ] **Step 5: Commit**

```bash
git add vnote/server.py vnote/daemon.py tests/test_server.py
git commit -m "feat: POST /history endpoint + daemon.log_history()

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: client plumbing — `--no-history`, env switches, `_deliver` wiring

**Files:**
- Modify: `vnote/config.py` (flow-client section, `vnote/config.py:94-104`)
- Modify: `vnote/client/app.py` (`_parse_args`, `_deliver`, `_process`, `_finish_take`)
- Test: `tests/test_config.py` (append), `tests/test_flow.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_env_on_defaults_on_and_honors_off_values(monkeypatch):
    from vnote import config as cfg

    monkeypatch.delenv("VNOTE_HISTORY_AUDIO", raising=False)
    assert cfg._env_on("VNOTE_HISTORY_AUDIO") is True
    for off in ("0", "false", "no", "off"):
        monkeypatch.setenv("VNOTE_HISTORY_AUDIO", off)
        assert cfg._env_on("VNOTE_HISTORY_AUDIO") is False
    monkeypatch.setenv("VNOTE_HISTORY_AUDIO", "1")
    assert cfg._env_on("VNOTE_HISTORY_AUDIO") is True
```

Append to `tests/test_flow.py` (module has `from vnote.client.app import _parse_args` already; the new tests import `app` locally):

```python
# --- history wiring ---------------------------------------------------------------


def _history_harness(monkeypatch):
    """Fake injection + history transport; returns the dict log_history was called with."""
    from vnote.client import app

    logged = {}

    def fake_log(wav, raw, clean, seconds, mode=None, tone=None):
        logged.update(wav=wav, raw=raw, clean=clean, seconds=seconds, mode=mode, tone=tone)

    monkeypatch.setattr(app.daemon, "log_history", fake_log)
    monkeypatch.setattr(app, "inject", lambda text, method=None: True)
    return app, logged


def test_deliver_logs_raw_take(monkeypatch):
    app, logged = _history_harness(monkeypatch)
    app._deliver(" hello there ", _parse_args([]), t0=0.0, wav=b"WAV", seconds=2.5)
    assert logged == {"wav": b"WAV", "raw": "hello there", "clean": None,
                      "seconds": 2.5, "mode": None, "tone": None}


def test_deliver_logs_cleaned_take(monkeypatch):
    from vnote.cleanup import CleanResult

    app, logged = _history_harness(monkeypatch)
    monkeypatch.setattr(app.daemon, "clean",
                        lambda text, **kw: CleanResult(title="", body="Hello there."))
    app._deliver("um hello there", _parse_args(["--clean", "--tone", "casual"]),
                 t0=0.0, wav=b"WAV", seconds=3.0)
    assert logged["raw"] == "um hello there"
    assert logged["clean"] == "Hello there."
    assert logged["mode"] == "dictation" and logged["tone"] == "casual"


def test_no_history_flag_skips_logging(monkeypatch):
    app, logged = _history_harness(monkeypatch)
    app._deliver("hello", _parse_args(["--no-history"]), t0=0.0, wav=b"WAV", seconds=1.0)
    assert logged == {}


def test_history_env_switches_drop_fields(monkeypatch):
    app, logged = _history_harness(monkeypatch)
    monkeypatch.setattr(app.config, "HISTORY_AUDIO", False)
    monkeypatch.setattr(app.config, "HISTORY_RAW", False)
    app._deliver("hello", _parse_args([]), t0=0.0, wav=b"WAV", seconds=1.0)
    assert logged["wav"] is None and logged["raw"] is None


def test_history_failure_is_one_console_line(monkeypatch, capsys):
    from vnote.client import app

    def boom(**kw):
        raise RuntimeError("daemon unreachable: nope")

    monkeypatch.setattr(app.daemon, "log_history", boom)
    monkeypatch.setattr(app, "inject", lambda text, method=None: True)
    app._deliver("hello", _parse_args([]), t0=0.0, wav=b"WAV", seconds=1.0)  # must not raise
    assert "history save failed" in capsys.readouterr().err


def test_flow_history_default_and_flag():
    assert _parse_args([]).history is True
    assert _parse_args(["--no-history"]).history is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_config.py tests/test_flow.py -v -k "env_on or history"`
Expected: FAIL — `AttributeError: module 'vnote.config' has no attribute '_env_on'`, and the flow tests fail on the missing `--no-history` flag / `_deliver` signature.

- [ ] **Step 3: Implement config switches**

In `vnote/config.py`, replace the flow-client block (`vnote/config.py:94-104`, currently starting `# --- flow client (`vnote-flow`) ---` and the `_env_bool` def) with:

```python
# --- flow client (`vnote-flow`) ---
def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _env_on(name: str) -> bool:
    """Default-on switch: only an explicit 0/false/no/off disables it."""
    return os.environ.get(name, "").strip().lower() not in ("0", "false", "no", "off")


HOTKEY = os.environ.get("VNOTE_HOTKEY", "ctrl+shift+space")
INJECT = os.environ.get("VNOTE_INJECT", "auto")  # auto | paste | type
VAD = _env_bool("VNOTE_VAD")
VAD_SILENCE = float(os.environ.get("VNOTE_VAD_SILENCE", "1.0"))  # trailing-silence stop window, seconds
STREAM = _env_bool("VNOTE_STREAM")
TRAY = _env_bool("VNOTE_TRAY")
HISTORY = _env_on("VNOTE_HISTORY")  # flow takes -> voice-notes/flow/ (PHASE6)
HISTORY_AUDIO = _env_on("VNOTE_HISTORY_AUDIO")
HISTORY_RAW = _env_on("VNOTE_HISTORY_RAW")
HISTORY_CLEAN = _env_on("VNOTE_HISTORY_CLEAN")
```

- [ ] **Step 4: Implement the client wiring**

In `vnote/client/app.py`:

(a) In `_parse_args`, after the `--tray` argument (`vnote/client/app.py:63-65`) and before `--version`, add:

```python
    p.add_argument("--no-history", action="store_false", dest="history", default=config.HISTORY,
                   help="don't save takes to the daemon's flow history (env VNOTE_HISTORY=0)")
```

(b) Replace the whole `_deliver` function (`vnote/client/app.py:89-112`) with:

```python
def _deliver(text: str, args: argparse.Namespace, t0: float,
             wav: bytes | None = None, seconds: float = 0.0) -> None:
    """Transcript -> spoken commands -> (optional clean) -> inject/print -> history."""
    raw = text.strip()  # the ASR transcript pre-commands — what history logs as raw
    # With --clean, leave "scratch that" for the LLM — it can merge the correction
    # semantically; the deterministic rule can only cut back to a clause boundary.
    text = apply_commands(raw, scratch=not args.clean)
    if not text:
        _say("  (no speech detected)")
        return
    cleaned = None
    tone = None
    if args.clean:
        tone = args.tone or _app_tone()
        try:
            result = daemon.clean(text, mode=args.clean, backend=args.backend or config.backend(),
                                  model=args.model, tone=tone)
            cleaned = text = result.body.strip()  # body only — no title header when typing into an app
        except RuntimeError as exc:
            _say(f"  (cleanup failed: {exc}; using the raw transcript)")
            text = apply_commands(text)  # no LLM after all — scratch deterministically
    _say(f"  {len(text)} chars in {round(time.monotonic() - t0, 1)}s")
    if args.to_stdout:
        print(text, flush=True)
    elif inject(text, method=args.inject_method):
        _say("  → injected")
    else:
        _say("  (injection failed — the text may still be on the clipboard)")
    _log_history(raw, cleaned, wav, seconds, args, tone)


def _log_history(raw: str, cleaned: str | None, wav: bytes | None, seconds: float,
                 args: argparse.Namespace, tone: str | None) -> None:
    """Best-effort history save — one console line on failure, never an exception."""
    if not args.history:
        return
    try:
        daemon.log_history(
            wav=wav if config.HISTORY_AUDIO else None,
            raw=raw if config.HISTORY_RAW else None,
            clean=cleaned if config.HISTORY_CLEAN else None,
            seconds=seconds,
            mode=args.clean if cleaned is not None else None,
            tone=tone,
        )
    except RuntimeError as exc:
        _say(f"  (history save failed: {exc})")
```

(c) In `_process` (`vnote/client/app.py:115-126`), change the last line from `_deliver(text, args, t0)` to:

```python
    _deliver(text, args, t0, wav=wav, seconds=seconds)
```

(d) In `_finish_take` (`vnote/client/app.py:197-213`), in the streamed-success branch change `_deliver(text, args, t0)` to:

```python
            _deliver(text, args, t0, wav=wav, seconds=seconds)
```

(The batch fallback `_process(wav, seconds, args)` already threads them via (c).)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_config.py tests/test_flow.py -v`
Expected: all pass, including the six new tests.

- [ ] **Step 6: Commit**

```bash
git add vnote/config.py vnote/client/app.py tests/test_config.py tests/test_flow.py
git commit -m "feat: save flow takes to history — --no-history + VNOTE_HISTORY_* switches

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: tray "Save history" toggle

**Files:**
- Modify: `vnote/client/tray.py:36-47`
- Test: `tests/test_tray.py`

- [ ] **Step 1: Extend the tests (they'll fail first)**

In `tests/test_tray.py`, update `_tray()` so the namespace carries the new shared flag — change:

```python
    args = argparse.Namespace(clean=None, vad=False)
```

to:

```python
    args = argparse.Namespace(clean=None, vad=False, history=True)
```

and append to `test_tray_menu_toggles_shared_flags_and_quits` (after the existing toggle assertions, before any quit assertion if present — keep the quit check last):

```python
    by_text["Save history"](tray._icon)
    assert args.history is False
    by_text["Save history"](tray._icon)
    assert args.history is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_tray.py -v`
Expected: FAIL with `KeyError: 'Save history'` — or SKIP if this box has no tray backend; if skipped, rely on Step 4's full-suite run and proceed (the test is exercised on machines with a backend).

- [ ] **Step 3: Add the menu item**

In `vnote/client/tray.py`, inside `__init__` (`vnote/client/tray.py:36-47`), add a callback after `toggle_vad` and a menu row after the VAD item:

```python
        def toggle_history(icon, item) -> None:
            args.history = not args.history
```

```python
        menu = pystray.Menu(
            pystray.MenuItem("vnote-flow", None, enabled=False),
            pystray.MenuItem("LLM cleanup", toggle_clean, checked=lambda item: bool(args.clean)),
            pystray.MenuItem("Auto-stop (VAD)", toggle_vad, checked=lambda item: bool(args.vad)),
            pystray.MenuItem("Save history", toggle_history, checked=lambda item: bool(args.history)),
            pystray.MenuItem("Quit", lambda icon, item: events.put(("exit", 0))),
        )
```

(ASCII only in tray strings — pystray's X11 backend writes titles latin-1.)

- [ ] **Step 4: Run the tests**

Run: `uv run python -m pytest tests/test_tray.py -v` then the full `uv run python -m pytest -q`
Expected: pass (or clean skip on a backend-less box) and full suite green.

- [ ] **Step 5: Commit**

```bash
git add vnote/client/tray.py tests/test_tray.py
git commit -m "feat: tray Save-history toggle

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: README section, version 0.3.0, full verification

**Files:**
- Modify: `README.md` (insert before `### Always-on (optional)`, currently `README.md:180`; add rows to the env table under `## Config (env vars)`, `README.md:219`)
- Modify: `pyproject.toml:3`, `vnote/__init__.py:3`

- [ ] **Step 1: README — history subsection**

Insert immediately before the `### Always-on (optional)` heading:

```markdown
### Dictation history

Every flow take is saved by default — audio, raw transcript, and cleaned
text — as an append-only daily log next to your batch notes:

    voice-notes/flow/
      2026-07-06.md               # one ## entry per take: raw, clean, audio link
      audio/20260706-143207.wav

`--no-history` (also a tray toggle) turns saving off for a session. Granular
switches, all on by default: `VNOTE_HISTORY_AUDIO=0` keeps the text but drops
the WAVs; `VNOTE_HISTORY_RAW=0` / `VNOTE_HISTORY_CLEAN=0` omit those fields.
The daemon owns the files (they land in its `voice-notes/`); the client sends
each take to `POST /history` best-effort — dictation never blocks on history.

```

- [ ] **Step 2: README — env table rows**

The `## Config (env vars)` table is two columns (`| var | default |`). Add these rows directly after the `| `VNOTE_TRAY` | ... |` row (`README.md:239`):

```markdown
| `VNOTE_HISTORY` | on (vnote-flow: `0` = don't save takes to `voice-notes/flow/`) |
| `VNOTE_HISTORY_AUDIO` | on (vnote-flow: `0` = keep text, drop the WAVs) |
| `VNOTE_HISTORY_RAW` | on (vnote-flow: `0` = omit raw transcripts) |
| `VNOTE_HISTORY_CLEAN` | on (vnote-flow: `0` = omit cleaned text) |
```

- [ ] **Step 3: Version bump**

- `pyproject.toml:3`: `version = "0.2.0"` → `version = "0.3.0"`
- `vnote/__init__.py:3`: `__version__ = "0.2.0"` → `__version__ = "0.3.0"`

- [ ] **Step 4: Full verification**

Run: `uv run ruff check .` — expected: `All checks passed!`
Run: `uv run python -m pytest -q` — expected: all pass (106 existing + 12 new = 118), exit 0. Do not pipe through tail.
Run: `uv run vnote --version` — expected: `vnote 0.3.0` (or the repo's version-line format).

- [ ] **Step 5: Commit**

```bash
git add README.md pyproject.toml vnote/__init__.py
git commit -m "docs: dictation-history section; version 0.3.0

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Post-plan notes for the executor

- **Manual acceptance (user-run, not yours):** a real hotkey take landing in `voice-notes/flow/<today>.md` with a playable audio link (PHASE6.md, first acceptance box). The Windows client is a **copy** — the user must `py -m pip install --upgrade "D:\Projects\vnote[flow]"` (or re-run `scripts\install-windows-client.ps1`) before hand-testing, and the WSL daemon must be restarted to pick up `/history` (stop it by port, not pattern).
- Spec-to-task map: PHASE6 objective 1 → Task 1; objective 2 → Task 2; objectives 3-4 → Tasks 3-4; objective 5 → Task 5. Streamed/batch equivalence is structural (both routes call `_deliver` with `wav`/`seconds`; Task 3c/3d).
