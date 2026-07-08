# Phase 5 — Polish & packaging

> Last phase of `ROADMAP.md`. No new pipeline capability — make what exists
> pleasant to live with: a tray icon instead of a console window, one-command
> installs, auto-start on both sides of the WSL seam, and a version bump.

## Objective

1. **System tray** (`vnote-flow --tray`): a state-colored icon (green ready,
   red recording, amber processing) with a menu — toggle LLM cleanup, toggle
   VAD, quit. Lets the client run windowless (`pythonw`) instead of holding a
   PowerShell window open.
2. **Install & auto-start scripts**:
   - `scripts/install-windows-client.ps1` — installs the `[flow]` extra on
     Windows Python and (with `-Startup`) drops a `pythonw` shortcut into the
     user's Startup folder, fixing the "not on PATH" papercut for good.
   - `scripts/vnote-daemon.service` — systemd user unit for the daemon on
     native Linux.
   - README recipe for auto-starting the WSL daemon at Windows logon.
3. **Version 0.2.0** — everything since 0.1.0 (daemon, flow client, VAD,
   streaming, vocabulary, tone) is a real minor release.

## Design constraints

- **Core dependencies stay untouched.** The tray needs `pystray` + `pillow`;
  both join the existing `[flow]` extra. `--tray` is opt-in (`VNOTE_TRAY=1`)
  and degrades to today's console behavior with a warning if the tray can't
  start (missing packages, no tray host, Wayland).
- **Tray callbacks mutate shared flags only** (`args.clean`, `args.vad`) and
  push a quit event onto the existing event queue — no second control path.
- **Honest testing limits:** tray behavior on a real Windows tray host can't
  be exercised from this WSL box. Unit tests cover construction, menu wiring
  and state images (skipped where no backend exists); the click-through test
  is manual, on Windows.

## Scope

**In:** `client/tray.py`, `--tray`/`VNOTE_TRAY`, the two scripts, README
"always-on" section, version 0.2.0, tests.

**Out:** a config-editing UI (the config file + `--setup` cover it), MSI/exe
installers, PyPI publication, macOS tray specifics, auto-spawning the daemon
from the client.

## Acceptance criteria

- [ ] `vnote-flow --tray` on Windows shows the icon, colors track state,
      toggles work, Quit exits cleanly (manual, user-verified).
- [ ] Without pystray installed, `--tray` warns and continues console-only.
- [ ] `install-windows-client.ps1 -Startup` creates a working
      `pythonw -m vnote.client.app` shortcut in shell:startup.
- [ ] `systemctl --user enable --now vnote-daemon` serves on a native-Linux
      box (unit file lints; live check is environment-dependent).
- [ ] `vnote --version` reports 0.2.0; ruff + pytest green; core deps
      unchanged.
