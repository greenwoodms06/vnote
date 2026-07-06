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
