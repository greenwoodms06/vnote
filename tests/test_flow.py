"""Tests for the flow client's pure logic: hotkey syntax, WAV framing, platform
detection, chord command selection, and the inject() orchestration (all clipboard
and keystroke side effects faked — nothing touches the real desktop)."""

import shutil
import sys
import wave
from io import BytesIO

import pytest

from vnote.audio import wav_bytes as _wav_bytes
from vnote.client import inject as inj
from vnote.client.app import _parse_args
from vnote.client.hotkey import to_pynput

# --- hotkey syntax -------------------------------------------------------------


def test_to_pynput_wraps_named_keys():
    assert to_pynput("ctrl+shift+space") == "<ctrl>+<shift>+<space>"
    assert to_pynput("ctrl+v") == "<ctrl>+v"
    assert to_pynput("F9") == "<f9>"


def test_to_pynput_rejects_junk():
    with pytest.raises(ValueError):
        to_pynput("")
    with pytest.raises(ValueError):
        to_pynput("ctrl++space")


# --- wav framing ---------------------------------------------------------------


def test_wav_bytes_is_valid_16k_mono():
    pcm = b"\x00\x00" * 1600  # 0.1 s of silence, s16le
    with wave.open(BytesIO(_wav_bytes(pcm)), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 16_000
        assert w.getsampwidth() == 2
        assert w.getnframes() == 1600


# --- platform detection ----------------------------------------------------------


def _fake_linux(monkeypatch, release="6.8.0-generic"):
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(inj.platform, "release", lambda: release)
    monkeypatch.setattr(sys, "platform", "linux")


def test_platform_wsl_via_env(monkeypatch):
    _fake_linux(monkeypatch)
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    assert inj._platform() == "wsl"


def test_platform_wsl_via_kernel_release(monkeypatch):
    _fake_linux(monkeypatch, release="6.6.87.2-microsoft-standard-WSL2")
    assert inj._platform() == "wsl"


def test_platform_wayland_vs_x11_vs_unknown(monkeypatch):
    _fake_linux(monkeypatch)
    assert inj._platform() == "unknown"
    monkeypatch.setenv("DISPLAY", ":0")
    assert inj._platform() == "x11"
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")  # wayland wins over a stale DISPLAY
    assert inj._platform() == "wayland"


def test_platform_windows_and_macos(monkeypatch):
    _fake_linux(monkeypatch)
    monkeypatch.setattr(sys, "platform", "win32")
    assert inj._platform() == "windows"
    monkeypatch.setattr(sys, "platform", "darwin")
    assert inj._platform() == "macos"


# --- chord command selection ----------------------------------------------------


def test_chord_cmd_wsl_uses_powershell_sendkeys(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/powershell.exe" if "powershell" in name else None)
    cmd = inj._paste_chord_cmd("wsl")
    assert cmd is not None and "powershell" in cmd[0] and "SendKeys" in cmd[-1]


def test_chord_cmd_wayland_prefers_wtype_then_ydotool(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}" if name == "wtype" else None)
    assert inj._paste_chord_cmd("wayland")[0] == "wtype"
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}" if name == "ydotool" else None)
    assert inj._paste_chord_cmd("wayland")[0] == "ydotool"
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert inj._paste_chord_cmd("wayland") is None


def test_chord_cmd_windows_defers_to_pynput(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert inj._paste_chord_cmd("windows") is None
    assert inj._paste_chord_cmd("macos") is None


# --- inject() orchestration -------------------------------------------------------


@pytest.fixture
def fake_desktop(monkeypatch):
    """Fake every side-effecting piece of inject(); record the call order."""
    calls = []
    state = {"clipboard": "previous contents", "paste_ok": True, "type_ok": True, "copy_ok": True}
    monkeypatch.setattr(inj, "_platform", lambda: "wsl")
    monkeypatch.setattr(inj, "_read_clipboard", lambda plat: state["clipboard"])
    monkeypatch.setattr(inj, "copy_to_clipboard", lambda text: calls.append(("copy", text)) or state["copy_ok"])
    monkeypatch.setattr(inj, "_send_paste", lambda plat: calls.append(("paste", plat)) or state["paste_ok"])
    monkeypatch.setattr(inj, "_type_text", lambda text, plat: calls.append(("type", text)) or state["type_ok"])
    monkeypatch.setattr(inj, "_SETTLE_S", 0)
    monkeypatch.setattr(inj, "_RESTORE_S", 0)
    return calls, state


def test_inject_paste_then_restore(fake_desktop):
    calls, _ = fake_desktop
    assert inj.inject("hello") is True
    assert calls == [("copy", "hello"), ("paste", "wsl"), ("copy", "previous contents")]


def test_inject_skips_restore_when_clipboard_unreadable(fake_desktop, monkeypatch):
    calls, _ = fake_desktop
    monkeypatch.setattr(inj, "_read_clipboard", lambda plat: None)
    assert inj.inject("hello") is True
    assert calls == [("copy", "hello"), ("paste", "wsl")]


def test_inject_auto_falls_back_to_typing(fake_desktop):
    calls, state = fake_desktop
    state["paste_ok"] = False
    assert inj.inject("hello", method="auto") is True
    assert ("type", "hello") in calls
    assert calls[-1] == ("copy", "previous contents")  # still restores


def test_inject_paste_method_does_not_type(fake_desktop):
    calls, state = fake_desktop
    state["paste_ok"] = False
    assert inj.inject("hello", method="paste") is False
    assert all(kind != "type" for kind, _ in calls)


def test_inject_type_method_never_touches_clipboard(fake_desktop):
    calls, _ = fake_desktop
    assert inj.inject("hello", method="type") is True
    assert calls == [("type", "hello")]


# --- vnote-flow arg parsing --------------------------------------------------------


def test_flow_defaults():
    a = _parse_args([])
    assert a.hotkey == "ctrl+shift+space"
    assert a.clean is None  # raw transcript by default — latency first
    assert a.inject_method == "auto"
    assert a.once is False and a.to_stdout is False
    assert a.vad is False and a.vad_silence == 1.0
    assert a.stream is False
    assert a.tone is None


def test_flow_flags():
    a = _parse_args(["--once", "--print", "--clean", "light", "--inject", "type", "--vad", "--vad-silence", "0.8"])
    assert a.once and a.to_stdout
    assert a.clean == "light"
    assert a.inject_method == "type"
    assert a.vad is True and a.vad_silence == 0.8


def test_flow_bare_clean_means_dictation():
    assert _parse_args(["--clean"]).clean == "dictation"


# --- active-window title command selection --------------------------------------


def test_window_title_cmd_per_platform(monkeypatch):
    from vnote.client import window

    monkeypatch.setattr(window, "_powershell", lambda: "/usr/bin/powershell.exe")
    cmd = window._title_cmd("wsl")
    assert "powershell" in cmd[0] and "GetForegroundWindow" in cmd[-1]

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}" if name == "xdotool" else None)
    assert window._title_cmd("x11") == ["xdotool", "getactivewindow", "getwindowname"]

    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert window._title_cmd("x11") is None
    assert window._title_cmd("wayland") is None
