"""Put text into the focused app — the only OS-specific layer (ROADMAP §3).

Default strategy is clipboard-paste: save the clipboard, set it to the text,
send the paste chord, restore. Fast, and robust for Unicode/Markdown. Direct
per-character typing is the fallback (`--inject type`).

Platform notes:
- WSL: the chord is sent Windows-side (powershell SendKeys), so the paste lands
  in whatever Windows app has focus. Non-elevated processes can't inject into
  elevated/admin windows (UIPI) — that fails *silently* by OS design.
- Wayland: needs `wtype` (or `ydotool` + its daemon); pynput can't synthesize
  input on Wayland.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time

from ..output import copy_to_clipboard

_SETTLE_S = 0.15  # clipboard write -> chord: let the clipboard owner change
_RESTORE_S = 0.30  # chord -> restore: let the app read the paste first

_PS_SENDKEYS = "(New-Object -ComObject WScript.Shell).SendKeys('^v')"
_WSL_POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"


def _platform() -> str:
    """One of: wsl, windows, macos, wayland, x11, unknown."""
    if os.environ.get("WSL_DISTRO_NAME") or "microsoft" in platform.release().lower():
        return "wsl"
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def _powershell() -> str | None:
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    if found:
        return found
    return _WSL_POWERSHELL if os.path.exists(_WSL_POWERSHELL) else None


def _paste_chord_cmd(plat: str) -> list[str] | None:
    """A subprocess that sends the paste chord to the focused window, if one exists."""
    if plat == "wsl":
        ps = _powershell()
        return [ps, "-NoProfile", "-Command", _PS_SENDKEYS] if ps else None
    if plat == "wayland":
        if shutil.which("wtype"):
            return ["wtype", "-M", "ctrl", "-P", "v", "-p", "v", "-m", "ctrl"]
        if shutil.which("ydotool"):
            return ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"]  # KEY_LEFTCTRL, KEY_V
        return None
    if plat == "x11" and shutil.which("xdotool"):
        return ["xdotool", "key", "--clearmodifiers", "ctrl+v"]
    return None  # windows / macos / bare x11 -> pynput


def _send_paste(plat: str) -> bool:
    cmd = _paste_chord_cmd(plat)
    if cmd is not None:
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            return True
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        from pynput.keyboard import Controller, Key
    except ImportError:
        return False
    try:
        kb = Controller()
        with kb.pressed(Key.cmd if plat == "macos" else Key.ctrl):
            kb.press("v")
            kb.release("v")
        return True
    except Exception:  # noqa: BLE001 - no display server, etc.
        return False


def _read_clipboard_cmd(plat: str) -> list[str] | None:
    if plat in ("wsl", "windows"):
        ps = _powershell()
        return [ps, "-NoProfile", "-Command", "Get-Clipboard -Raw"] if ps else None
    if plat == "wayland" and shutil.which("wl-paste"):
        return ["wl-paste", "--no-newline"]
    if plat == "x11":
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard", "-o"]
        if shutil.which("xsel"):
            return ["xsel", "--clipboard", "--output"]
    if plat == "macos" and shutil.which("pbpaste"):
        return ["pbpaste"]
    return None


def _read_clipboard(plat: str) -> str | None:
    """Current clipboard text, best-effort (None if unreadable — we just skip the restore)."""
    cmd = _read_clipboard_cmd(plat)
    if cmd is None:
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    text = out.decode("utf-8", errors="replace")
    if plat in ("wsl", "windows"):
        text = text.removesuffix("\r\n")  # powershell appends one newline
    return text


def _type_text(text: str, plat: str) -> bool:
    if plat == "wayland" and shutil.which("wtype"):
        try:
            subprocess.run(["wtype", text], check=True, timeout=30)
            return True
        except (OSError, subprocess.SubprocessError):
            return False
    if plat == "x11" and shutil.which("xdotool"):
        try:
            subprocess.run(["xdotool", "type", "--clearmodifiers", text], check=True, timeout=30)
            return True
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        from pynput.keyboard import Controller
    except ImportError:
        return False
    try:
        Controller().type(text)
        return True
    except Exception:  # noqa: BLE001 - InvalidCharacterException, no display, ...
        return False


def inject(text: str, method: str = "auto") -> bool:
    """Put ``text`` into the focused app. Returns True on (apparent) success."""
    plat = _platform()
    if method == "type":
        return _type_text(text, plat)
    old = _read_clipboard(plat)
    if not copy_to_clipboard(text):
        return _type_text(text, plat) if method == "auto" else False
    time.sleep(_SETTLE_S)
    ok = _send_paste(plat)
    if not ok and method == "auto":
        ok = _type_text(text, plat)
    if old is not None and old != text:
        time.sleep(_RESTORE_S)
        copy_to_clipboard(old)
    return ok
