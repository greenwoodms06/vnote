"""Best-effort active-window title, for per-app tone (ROADMAP Phase 4).

Returns None whenever the platform can't tell us (Wayland, missing tools) —
callers treat that as "no app context", never as an error.
"""

from __future__ import annotations

import shutil
import subprocess

from .inject import _platform, _powershell

# GetForegroundWindow + GetWindowText via a powershell-hosted user32 shim.
_PS_TITLE = """
Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public class VnoteWin {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder t, int c);
}
'@
$b = New-Object System.Text.StringBuilder 512
[void][VnoteWin]::GetWindowText([VnoteWin]::GetForegroundWindow(), $b, 512)
$b.ToString()
"""

_OSASCRIPT = 'tell application "System Events" to get name of first process whose frontmost is true'


def _title_cmd(plat: str) -> list[str] | None:
    if plat in ("wsl", "windows"):
        ps = _powershell()
        return [ps, "-NoProfile", "-Command", _PS_TITLE] if ps else None
    if plat == "x11" and shutil.which("xdotool"):
        return ["xdotool", "getactivewindow", "getwindowname"]
    if plat == "macos" and shutil.which("osascript"):
        return ["osascript", "-e", _OSASCRIPT]
    return None  # wayland etc.


def active_window_title() -> str | None:
    cmd = _title_cmd(_platform())
    if cmd is None:
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    title = out.decode("utf-8", errors="replace").strip()
    return title or None
