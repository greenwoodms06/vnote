# Promote-a-Take Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote any logged flow take into a batch-style session folder after the fact — `vnote --promote`, `POST /promote`, and a tray "Save last take as note" action (spec: `PHASE7.md`).

**Architecture:** Capture is untouched. `history.promote_take()` parses one entry back out of a daily flow log, feeds the existing `output.make_session_dir()`/`write_session()` machinery (WAV moved, not copied), and replaces the entry body with a `[note](…)` pointer. A module lock in `history.py` serializes appends and promotions; the daemon is the single writer, with an in-process CLI fallback when no daemon runs.

**Tech Stack:** Python stdlib only (re/threading/datetime/shutil). Zero new dependencies.

**Repo-specific rules (read first):**
- Run tests ONLY as `uv run python -m pytest ...` — NEVER bare `uv run pytest` (wrong Python, silently skipped suites). Never pipe pytest through `tail`/`head`.
- After `git add` of any NEW file: `git update-index --chmod=-x <file>` (DrvFs sets a bogus exec bit). No new source files in this plan, so this only matters if you create something unplanned.
- `output.py` and `history.py` EACH import `NOTES_DIR` by value. Every test that promotes must monkeypatch BOTH `history.NOTES_DIR` and `output.NOTES_DIR` to the same tmp_path.

---

### Task 1: `history.promote_take()` — parse, build, pointer, lock

**Files:**
- Modify: `vnote/history.py` (whole file shown below)
- Test: `tests/test_history.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_history.py`:

```python
# --- promotion -------------------------------------------------------------------


def _promote_root(monkeypatch, tmp_path):
    from vnote import output

    monkeypatch.setattr(history, "NOTES_DIR", tmp_path)
    monkeypatch.setattr(output, "NOTES_DIR", tmp_path)  # make_session_dir binds its own copy
    return tmp_path / "flow"


def test_promote_last_builds_session_and_leaves_pointer(monkeypatch, tmp_path):
    flow = _promote_root(monkeypatch, tmp_path)
    history.append_take(raw="um hello world", clean="Hello world.", wav=b"RIFF",
                        seconds=4.9, mode="dictation", tone="casual", when=WHEN)
    session = history.promote_take("last")

    assert session.name == "2026-07-06-1432-hello-world"
    assert (session / "audio.wav").read_bytes() == b"RIFF"
    assert not (flow / "audio" / "20260706-143207.wav").exists()  # moved, not copied
    assert (session / "transcript.txt").read_text(encoding="utf-8") == "um hello world\n"
    note = (session / "note.md").read_text(encoding="utf-8")
    assert note.startswith("# Hello world.") and "Hello world." in note
    meta = json.loads((session / "meta.json").read_text(encoding="utf-8"))
    assert meta["source"] == "flow-promoted"
    assert meta["seconds"] == 4.9 and meta["mode"] == "dictation" and meta["tone"] == "casual"

    day = (flow / "2026-07-06.md").read_text(encoding="utf-8")
    assert "## 14:32:07  (4.9s, clean=dictation, tone=casual)" in day  # header kept
    assert f"[note](../{session.name}/note.md)" in day
    assert "**raw:**" not in day  # body replaced by the pointer


def test_promote_by_time_leaves_other_entries_alone(monkeypatch, tmp_path):
    flow = _promote_root(monkeypatch, tmp_path)
    history.append_take(raw="first take", clean=None, wav=None, seconds=1.0,
                        mode=None, tone=None, when=WHEN)
    history.append_take(raw="second take", clean=None, wav=None, seconds=1.0,
                        mode=None, tone=None, when=datetime(2026, 7, 6, 15, 0, 0))
    history.promote_take("14:32:07")
    day = (flow / "2026-07-06.md").read_text(encoding="utf-8")
    assert "**raw:** second take" in day  # untouched
    assert "**raw:** first take" not in day  # promoted away


def test_promote_multiline_text_round_trips(monkeypatch, tmp_path):
    _promote_root(monkeypatch, tmp_path)
    history.append_take(raw="para one\n\npara two", clean=None, wav=None,
                        seconds=2.0, mode=None, tone=None, when=WHEN)
    session = history.promote_take("last")
    assert (session / "transcript.txt").read_text(encoding="utf-8") == "para one\n\npara two\n"


def test_promote_audio_less_take(monkeypatch, tmp_path):
    _promote_root(monkeypatch, tmp_path)
    history.append_take(raw="no audio here", clean=None, wav=None,
                        seconds=1.0, mode=None, tone=None, when=WHEN)
    session = history.promote_take("last")
    assert not (session / "audio.wav").exists()
    assert (session / "note.md").exists()


def test_promote_twice_is_an_error_and_log_unchanged(monkeypatch, tmp_path):
    flow = _promote_root(monkeypatch, tmp_path)
    history.append_take(raw="only take", clean=None, wav=None, seconds=1.0,
                        mode=None, tone=None, when=WHEN)
    history.promote_take("last")
    before = (flow / "2026-07-06.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="already promoted"):
        history.promote_take("last")
    assert (flow / "2026-07-06.md").read_text(encoding="utf-8") == before


def test_promote_unknown_time_and_empty_store(monkeypatch, tmp_path):
    _promote_root(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="no flow history"):
        history.promote_take("last")
    history.append_take(raw="x", clean=None, wav=None, seconds=1.0,
                        mode=None, tone=None, when=WHEN)
    with pytest.raises(ValueError, match="no take at"):
        history.promote_take("09:09:09")
```

Also add the two imports these tests need at the top of `tests/test_history.py` (it currently imports only `datetime` and `history`):

```python
import json

import pytest
```

(Final import block: `import json`, blank line, `from datetime import datetime`, blank line, `import pytest`, blank line, `from vnote import history` — let ruff settle the exact order via `uv run ruff check --fix tests/test_history.py` if needed.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_history.py -v`
Expected: the 4 existing tests pass; the 6 new ones FAIL with `AttributeError: module 'vnote.history' has no attribute 'promote_take'`.

- [ ] **Step 3: Replace `vnote/history.py` with the full implementation**

The whole file (existing `append_take` gains the lock; everything below `# --- promotion` is new):

```python
"""Append-only flow-dictation history under NOTES_DIR/flow/.

One Markdown file per day plus a flat, date-stamped audio directory — a day
of dictation is one file, never a folder per utterance (ROADMAP §6/§9).
Only the daemon writes here; clients send takes through POST /history.
A take that turns out to be a real note is promoted (PHASE7): rebuilt into a
batch-style session folder, its log body replaced by a pointer line. One
lock serializes every mutation — appends can't interleave with a promotion's
read-modify-write.
"""

from __future__ import annotations

import re
import shutil
import threading
from datetime import datetime
from pathlib import Path

from .config import NOTES_DIR

_lock = threading.Lock()


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
    with _lock:
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


# --- promotion (PHASE7): one logged take -> a batch-style session folder -----

# [ \t]* not \s*: \s can backtrack across the newline and shift match.end(),
# which promote_take uses as the body-splice offset.
_HEADER_RE = re.compile(r"^## (\d\d:\d\d:\d\d)  \((.*)\)[ \t]*$", re.MULTILINE)


def _parse_header(params: str) -> dict:
    """'4.9s, clean=dictation, tone=casual' | '2.1s, raw' -> fields."""
    out: dict = {"seconds": 0.0, "mode": None, "tone": None}
    for part in (p.strip() for p in params.split(",")):
        if part.startswith("clean="):
            out["mode"] = part[len("clean="):]
        elif part.startswith("tone="):
            out["tone"] = part[len("tone="):]
        elif part.endswith("s") and part != "raw":
            try:
                out["seconds"] = float(part[:-1])
            except ValueError:
                pass
    return out


def _field(body: str, marker: str) -> str | None:
    """Text of a '**marker:** ...' paragraph, up to the next field marker.
    re.S lets multi-line dictation (embedded blank lines) round-trip."""
    m = re.search(
        rf"^\*\*{marker}:\*\* (.*?)(?=^\*\*raw:\*\*|^\*\*clean:\*\*|\Z)",
        body, re.MULTILINE | re.DOTALL,
    )
    return m.group(1).strip() if m else None


def _locate(take: str) -> tuple[Path, str | None]:
    """Resolve a take spec to (day file, HH:MM:SS or None-for-last)."""
    flow = NOTES_DIR / "flow"
    if " " in take:  # 'YYYY-MM-DD HH:MM:SS'
        date_s, time_s = take.split(" ", 1)
        day = flow / f"{date_s}.md"
        if not day.is_file():
            raise ValueError(f"no flow log for {date_s}")
        return day, time_s.strip()
    days = sorted(flow.glob("????-??-??.md"))
    if not days:
        raise ValueError("no flow history yet")
    return days[-1], None if take == "last" else take


def promote_take(take: str = "last") -> Path:
    """Promote one logged take into its own session folder; return that folder.

    take: 'last' (newest entry of the newest day), 'HH:MM:SS' (newest day),
    or 'YYYY-MM-DD HH:MM:SS'. Raises ValueError with a one-line reason when
    the take is missing, textless, or already promoted; the log is untouched
    on every error path.
    """
    from .output import make_session_dir, write_session

    with _lock:
        day, time_s = _locate(take)
        text = day.read_text(encoding="utf-8")
        matches = list(_HEADER_RE.finditer(text))
        if not matches:
            raise ValueError(f"no takes in {day.name}")
        if time_s is None:
            idx = len(matches) - 1
        else:
            idx = next((i for i, m in enumerate(matches) if m.group(1) == time_s), -1)
            if idx < 0:
                raise ValueError(f"no take at {time_s} in {day.name}")
        header = matches[idx]
        body_start = header.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end]

        if re.search(r"^\[note\]\(", body, re.MULTILINE):
            raise ValueError(f"take {header.group(1)} was already promoted")
        raw = _field(body, "raw")
        clean = _field(body, "clean")
        if raw is None and clean is None:
            raise ValueError(f"take {header.group(1)} has no text to promote")
        fields = _parse_header(header.group(2))

        when = datetime.strptime(f"{day.stem} {header.group(1)}", "%Y-%m-%d %H:%M:%S")
        title = " ".join((clean or raw).split()[:8])
        session = make_session_dir(title, when=when)

        audio_dst = None
        audio_m = re.search(r"^\[audio\]\(audio/([^)]+)\)", body, re.MULTILINE)
        if audio_m:
            src = NOTES_DIR / "flow" / "audio" / audio_m.group(1)
            if src.is_file():
                audio_dst = session / "audio.wav"
                shutil.move(src, audio_dst)  # moved, not copied — one home for the take

        write_session(
            session,
            audio_src=audio_dst,
            transcript=raw or clean or "",
            note_md=clean or raw,
            title=title,
            meta={
                "created": when.isoformat(timespec="seconds"),
                "source": "flow-promoted",
                "promoted_from": f"flow/{day.name}",
                "seconds": fields["seconds"],
                "mode": fields["mode"],
                "tone": fields["tone"],
            },
        )

        pointer = f"[note](../{session.name}/note.md)\n\n"
        day.write_text(text[:body_start] + "\n\n" + pointer + text[body_end:], encoding="utf-8")
        return session
```

Notes: two takes in the same second — `time_s` selection picks the first; acceptable, the writer disambiguates only audio names. `write_session`'s same-path check makes `audio_src=audio_dst` a no-op copy, so the move is the only audio I/O.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_history.py -v`
Expected: 10 passed. Then `uv run ruff check .` → `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add vnote/history.py tests/test_history.py
git commit -m "feat: promote a flow take to a session folder (history.promote_take)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `POST /promote` + `daemon.promote()`

**Files:**
- Modify: `vnote/server.py` (route chain in `do_POST` — add after the `/history` branch's `self._send(200, {"saved": True})` line, before `elif url.path == "/stream/start":`)
- Modify: `vnote/daemon.py` (append at end)
- Test: `tests/test_server.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server.py`:

```python
def test_promote_round_trip(live_server, tmp_path, monkeypatch):
    from vnote import history, output

    monkeypatch.setattr(history, "NOTES_DIR", tmp_path)
    monkeypatch.setattr(output, "NOTES_DIR", tmp_path)
    daemon.log_history(wav=b"RIFFDATA", raw="promote me", clean="Promote me.",
                       seconds=2.0, mode="dictation", tone=None)
    name = daemon.promote("last")
    assert (tmp_path / name / "note.md").exists()
    assert (tmp_path / name / "audio.wav").read_bytes() == b"RIFFDATA"
    day = next((tmp_path / "flow").glob("*.md")).read_text(encoding="utf-8")
    assert f"[note](../{name}/note.md)" in day


def test_promote_empty_store_is_client_error(live_server, tmp_path, monkeypatch):
    from vnote import history, output

    monkeypatch.setattr(history, "NOTES_DIR", tmp_path)
    monkeypatch.setattr(output, "NOTES_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="no flow history"):
        daemon.promote("last")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_server.py -v -k promote`
Expected: FAIL with `AttributeError: module 'vnote.daemon' has no attribute 'promote'`.

- [ ] **Step 3: Implement endpoint and client**

In `vnote/server.py` `do_POST`, insert after the `/history` branch (after its `self._send(200, {"saved": True})`):

```python
            elif url.path == "/promote":
                data = self._read_json()
                from . import history

                try:
                    session = history.promote_take(data.get("take") or "last")
                except ValueError as exc:
                    return self._send(400, {"error": str(exc)})
                self._send(200, {"note": session.name})
```

Append to `vnote/daemon.py`:

```python
def promote(take: str = "last") -> str:
    """Promote a logged flow take to its own note folder; returns the folder name."""
    return _post("/promote", {"take": take}, timeout=30)["note"]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_server.py -v`
Expected: all pass (17 in this file).

- [ ] **Step 5: Commit**

```bash
git add vnote/server.py vnote/daemon.py tests/test_server.py
git commit -m "feat: POST /promote endpoint + daemon.promote()

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `vnote --promote` CLI

**Files:**
- Modify: `vnote/cli.py` (docstring, `_parse_args`, a `_do_promote` helper, short-circuit in `main`)
- Test: `tests/test_cli.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
# --- --promote -------------------------------------------------------------------


def test_promote_flag_in_process(monkeypatch, tmp_path, capsys):
    from datetime import datetime

    from vnote import cli, daemon, history, output

    monkeypatch.setattr(daemon, "is_up", lambda timeout=0.3: False)  # force in-process path
    monkeypatch.setattr(history, "NOTES_DIR", tmp_path)
    monkeypatch.setattr(output, "NOTES_DIR", tmp_path)
    history.append_take(raw="promote me please and thanks", clean=None, wav=None,
                        seconds=1.0, mode=None, tone=None, when=datetime(2026, 7, 6, 9, 0, 0))
    assert cli.main(["--promote"]) == 0
    assert "promoted" in capsys.readouterr().err
    assert any(p.name.startswith("2026-07-06-0900-") for p in tmp_path.iterdir())


def test_promote_flag_error_exits_nonzero(monkeypatch, tmp_path, capsys):
    from vnote import cli, daemon, history, output

    monkeypatch.setattr(daemon, "is_up", lambda timeout=0.3: False)
    monkeypatch.setattr(history, "NOTES_DIR", tmp_path)
    monkeypatch.setattr(output, "NOTES_DIR", tmp_path)
    assert cli.main(["--promote"]) == 1
    assert "error:" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run python -m pytest tests/test_cli.py -v -k promote`
Expected: FAIL — argparse exits 2 on the unknown `--promote` flag (SystemExit), or `AttributeError` once parsing is reached.

- [ ] **Step 3: Implement**

(a) In the `vnote/cli.py` module docstring, add one line after the `--redo` line:

```
    vnote --promote [TAKE]     turn a dictated flow take into its own note folder
```

(b) In `_parse_args`, in the "Utility actions" group after `--serve`:

```python
    p.add_argument("--promote", nargs="?", const="last", metavar="TAKE",
                   help="promote a flow-history take to its own note folder: bare = the last "
                        "take, 'HH:MM:SS' = that take in the newest day, "
                        "'YYYY-MM-DD HH:MM:SS' = explicit")
```

(c) Add this helper after `_pipeline` (`vnote/cli.py:113`):

```python
def _do_promote(args: argparse.Namespace) -> int:
    """Daemon-first (it may be appending takes concurrently); in-process fallback."""
    name = None
    if not args.no_daemon:
        from . import daemon

        if daemon.is_up():
            try:
                name = daemon.promote(args.promote)
            except RuntimeError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
    if name is None:
        from . import history

        try:
            name = history.promote_take(args.promote).name
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    _say(f"📁 promoted → {config.NOTES_DIR / name}")
    return 0
```

(d) In `main()`, add to the utility short-circuits, after the `if args.serve:` block:

```python
    if args.promote:
        return _do_promote(args)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run python -m pytest tests/test_cli.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add vnote/cli.py tests/test_cli.py
git commit -m "feat: vnote --promote (daemon-first, in-process fallback)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: tray "Save last take as note" action

**Files:**
- Modify: `vnote/client/tray.py` (menu), `vnote/client/app.py` (event loop in `main()`)
- Test: `tests/test_tray.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tray.py`:

```python
def test_tray_promote_action_pushes_event():
    tray, _args, events = _tray()
    by_text = {str(i.text): i for i in list(tray._icon.menu.items)}
    by_text["Save last take as note"](tray._icon)
    assert events.get_nowait() == ("promote", 0)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_tray.py -v`
Expected: FAIL with `KeyError: 'Save last take as note'` (or clean SKIP on a backend-less box — then rely on the full-suite run and proceed).

- [ ] **Step 3: Implement**

In `vnote/client/tray.py`, add a menu row between "Save history" and "Quit" (an action — it pushes an event; it does NOT flip a flag):

```python
            pystray.MenuItem("Save last take as note",
                             lambda icon, item: events.put(("promote", 0))),
```

In `vnote/client/app.py` `main()`, in the event loop, add a handler after the `if kind == "exit":` block and before the `vad-stop` check:

```python
            if kind == "promote":  # tray action: last take -> its own note folder
                try:
                    name = daemon.promote("last")
                except RuntimeError as exc:
                    _say(f"  (promote failed: {exc})")
                else:
                    _say(f"  → note: {name}")
                continue
```

(The three-line handler has no unit test — driving `main()`'s loop needs a full harness; the tray test covers the wiring and the manual acceptance box covers the click-through, per the same honest-testing stance as PHASE5.)

- [ ] **Step 4: Run the tests**

Run: `uv run python -m pytest tests/test_tray.py -v` then `uv run python -m pytest -q`
Expected: tray tests pass (or clean skip); full suite green, exit 0.

- [ ] **Step 5: Commit**

```bash
git add vnote/client/tray.py vnote/client/app.py tests/test_tray.py
git commit -m "feat: tray action — save the last take as its own note

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: README, version 0.4.0, full verification

**Files:**
- Modify: `README.md` (extend the `### Dictation history` section added in 0.3.0)
- Modify: `pyproject.toml:3`, `vnote/__init__.py:3`, plus the `uv.lock` re-lock

- [ ] **Step 1: README**

At the end of the `### Dictation history` section (after its env-switches paragraph, before `### Always-on (optional)`), append:

```markdown
A take that turns out to be a real note can be **promoted** — rebuilt as its
own dated-titled session folder, same layout as batch notes, with the WAV
moved in and a pointer left under the take's timestamp in the daily log:

    vnote --promote                    # the last take
    vnote --promote 14:32:07           # that take, newest day
    vnote --promote "2026-07-05 09:15:00"

The tray menu's "Save last take as note" does the same with one click.

```

- [ ] **Step 2: Version bump**

- `pyproject.toml:3`: `version = "0.3.0"` → `version = "0.4.0"`
- `vnote/__init__.py:3`: `__version__ = "0.3.0"` → `__version__ = "0.4.0"`

- [ ] **Step 3: Full verification**

Run: `uv run ruff check .` — expected `All checks passed!`
Run: `uv run python -m pytest -q` — expected: ALL tests pass, exit 0 (~130; exact count is not a gate). Do not pipe through tail.
Run: `uv run vnote --version` — expected `vnote 0.4.0` (this also regenerates `uv.lock` for the new version — that re-lock BELONGS in this commit).

- [ ] **Step 4: Commit**

```bash
git add README.md pyproject.toml vnote/__init__.py uv.lock
git commit -m "docs: promote-a-take in README; version 0.4.0

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Post-plan notes for the executor

- **Manual acceptance (user-run, not yours):** dictate → `vnote --promote` (or the tray action) → folder appears beside the batch sessions, log entry becomes a pointer (PHASE7.md acceptance box 1). Requires a daemon restart AND a Windows client reinstall (`py -m pip install --upgrade "D:\Projects\vnote[flow]"`) — the Windows install is a copy.
- Spec-to-task map: PHASE7 objectives 1-2 → Task 1; objective 3 → Task 2; objective 4 → Task 3; objective 5 → Task 4; objective 6 → Task 5. The lock (objective 3) is asserted by construction in Task 1's implementation (every mutation path is inside `with _lock:`).
