"""Optional system-tray icon for vnote-flow (pystray + Pillow, from the [flow] extra).

Lets the client run windowless (pythonw on Windows): the icon color is the
status line — green ready, red recording, amber processing — and the menu
covers the toggles you'd otherwise restart with different flags for.
"""

from __future__ import annotations

import argparse
import queue

_COLORS = {
    "ready": (90, 200, 120),
    "recording": (230, 70, 70),
    "processing": (240, 180, 60),
}


def _dot(color: tuple[int, int, int]):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((8, 8, 56, 56), fill=(*color, 255))
    return img


class Tray:
    """Build with the shared args namespace + event queue; then start()."""

    def __init__(self, args: argparse.Namespace, events: queue.Queue) -> None:
        import pystray

        self._images = {name: _dot(color) for name, color in _COLORS.items()}

        def toggle_clean(icon, item) -> None:
            args.clean = None if args.clean else "dictation"

        def toggle_vad(icon, item) -> None:
            args.vad = not args.vad

        def toggle_history(icon, item) -> None:
            args.history = not args.history

        menu = pystray.Menu(
            pystray.MenuItem("vnote-flow", None, enabled=False),
            pystray.MenuItem("LLM cleanup", toggle_clean, checked=lambda item: bool(args.clean)),
            pystray.MenuItem("Auto-stop (VAD)", toggle_vad, checked=lambda item: bool(args.vad)),
            pystray.MenuItem("Save history", toggle_history, checked=lambda item: bool(args.history)),
            pystray.MenuItem("Save last take as note",
                             lambda icon, item: events.put(("promote", 0))),
            pystray.MenuItem("Quit", lambda icon, item: events.put(("exit", 0))),
        )
        # ASCII-only title: pystray's X11 backend writes it latin-1.
        self._icon = pystray.Icon("vnote-flow", self._images["ready"], "vnote-flow (ready)", menu)

    def start(self) -> None:
        self._icon.run_detached()

    def state(self, name: str) -> None:
        """Recolor the icon: 'ready' | 'recording' | 'processing'."""
        self._icon.icon = self._images[name]
        self._icon.title = f"vnote-flow ({name})"

    def stop(self) -> None:
        try:
            self._icon.stop()
        except Exception:  # noqa: BLE001 - never let tray teardown mask the real exit
            pass
