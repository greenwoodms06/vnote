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
