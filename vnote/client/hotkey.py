"""Global hotkey listening for the flow client (pynput, lazily imported)."""

from __future__ import annotations

from collections.abc import Callable

_INSTALL_HINT = (
    "the global hotkey needs the `pynput` package.\n"
    "    Install the flow extra on the machine that owns the keyboard:\n"
    "        uv pip install -e '.[flow]'    (or: pip install pynput)"
)


def ensure_available() -> None:
    """Raise a friendly RuntimeError if pynput can't be imported here."""
    try:
        import pynput  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(_INSTALL_HINT) from exc


def to_pynput(combo: str) -> str:
    """'ctrl+shift+space' -> '<ctrl>+<shift>+<space>' (pynput GlobalHotKeys syntax)."""
    parts = [p.strip().lower() for p in combo.split("+")]
    if not parts or not all(parts):
        raise ValueError(f"bad hotkey: {combo!r} (expected e.g. 'ctrl+shift+space')")
    return "+".join(p if len(p) == 1 else f"<{p}>" for p in parts)


def listen(combo: str, on_toggle: Callable[[], None]) -> None:
    """Block forever, firing ``on_toggle()`` on each combo press.

    The callback runs on the OS input thread — it must only hand off work
    (e.g. push to a queue), never block.
    """
    ensure_available()
    from pynput import keyboard

    with keyboard.GlobalHotKeys({to_pynput(combo): on_toggle}) as hk:
        hk.join()
