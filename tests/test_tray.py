"""Tests for the tray icon's construction and toggle wiring.

Needs pystray + Pillow (the [flow] extra) and a usable backend; skipped
cleanly everywhere else — the click-through test is manual, on Windows.
"""

import argparse
import queue

import pytest

pytest.importorskip("pystray")
pytest.importorskip("PIL")


def _tray():
    from vnote.client.tray import Tray

    args = argparse.Namespace(clean=None, vad=False, history=True)
    events: queue.Queue = queue.Queue()
    try:
        return Tray(args, events), args, events
    except Exception as exc:  # noqa: BLE001 - no display / no tray host on this box
        pytest.skip(f"no tray backend here: {exc}")


def test_tray_builds_and_recolors():
    tray, _args, _events = _tray()
    assert set(tray._images) == {"ready", "recording", "processing"}
    tray.state("recording")
    assert tray._icon.title == "vnote-flow (recording)"
    tray.stop()  # never started; must not raise


def test_tray_menu_toggles_shared_flags_and_quits():
    tray, args, events = _tray()
    items = list(tray._icon.menu.items)
    by_text = {str(i.text): i for i in items}

    by_text["LLM cleanup"](tray._icon)  # pystray invokes items with the icon
    assert args.clean == "dictation"
    by_text["LLM cleanup"](tray._icon)
    assert args.clean is None

    by_text["Auto-stop (VAD)"](tray._icon)
    assert args.vad is True

    by_text["Save history"](tray._icon)
    assert args.history is False
    by_text["Save history"](tray._icon)
    assert args.history is True

    by_text["Quit"](tray._icon)
    assert events.get_nowait() == ("exit", 0)
    tray.stop()
