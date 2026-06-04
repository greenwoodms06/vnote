"""One-time interactive setup: pick a cleanup backend (and Ollama model).

Runs only on an interactive terminal, only when nothing has been chosen yet, and
never when the choice is already forced by ``$VNOTE_BACKEND`` or ``--backend``.
The result is written to the config file (see ``config.config_file()``); delete
that file to run setup again.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from . import config

# (ollama tag, approx VRAM GB, one-line description)
_OLLAMA_TIERS = [
    ("qwen2.5:14b-instruct", 10, "best quality — needs a good GPU (~10 GB VRAM)"),
    ("qwen2.5:7b-instruct", 6, "solid quality — modest GPU (~6 GB VRAM)"),
    ("llama3.2:3b-instruct", 3, "fastest, lightest — small GPU or CPU (~3 GB)"),
]


def should_run(backend_flag: str | None) -> bool:
    """True only if we should prompt: interactive TTY, no prior choice, not forced."""
    if backend_flag is not None:
        return False
    if os.environ.get("VNOTE_BACKEND"):
        return False
    if config.config_file().exists():
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


def _detect_vram_gb() -> float | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    sizes = []
    for tok in out.split():
        try:
            sizes.append(float(tok))
        except ValueError:
            pass
    return max(sizes) / 1024 if sizes else None  # MiB -> GiB


def _suggest_tier(vram_gb: float | None) -> int:
    if vram_gb is None:
        return 1  # unknown GPU: suggest the middle 7b tier
    for i, (_, need, _) in enumerate(_OLLAMA_TIERS):
        if vram_gb >= need:
            return i
    return len(_OLLAMA_TIERS) - 1


def _ask(prompt: str, options: list[str], default: int) -> int:
    """Print a numbered menu; return the chosen 0-based index (Enter = default)."""
    print(prompt)
    for i, opt in enumerate(options):
        marker = " (default)" if i == default else ""
        print(f"  {i + 1}. {opt}{marker}")
    while True:
        try:
            raw = input(f"Choose [1-{len(options)}] (Enter = {default + 1}): ").strip()
        except EOFError:
            return default
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print("  (please enter a number from the list)")


def run(backend_flag: str | None, *, force: bool = False) -> None:
    """If setup is warranted, prompt and persist the choice. Safe to call always.

    ``force=True`` (used by ``vnote --setup``) re-runs setup even when a config
    already exists, but still requires an interactive terminal.
    """
    if force:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            print("Setup needs an interactive terminal.", file=sys.stderr)
            return
    elif not should_run(backend_flag):
        return

    print("\nFirst run — let's pick how vnote cleans up your transcripts.\n")
    backend_idx = _ask(
        "Cleanup backend:",
        [
            "Local (Ollama) — private, offline, runs on your machine (needs a model download)",
            "Cloud (Claude) — higher-quality cleanup via the Anthropic API (needs ANTHROPIC_API_KEY)",
        ],
        default=0,
    )

    cfg: dict = {}
    if backend_idx == 0:
        cfg["backend"] = "ollama"
        vram = _detect_vram_gb()
        if vram is not None:
            print(f"\nDetected ~{vram:.0f} GB GPU memory.")
        suggested = _suggest_tier(vram)
        tier_idx = _ask(
            "\nWhich local model? (you can change it later)",
            [f"{tag}  —  {desc}" for tag, _, desc in _OLLAMA_TIERS],
            default=suggested,
        )
        tag = _OLLAMA_TIERS[tier_idx][0]
        cfg["ollama_model"] = tag
        print(f"\n✓ Using Ollama with {tag}.")
        print(f"  Pull it once if you haven't:  ollama pull {tag}")
    else:
        cfg["backend"] = "claude"
        print(f"\n✓ Using the Claude backend ({config.CLAUDE_MODEL}).")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("  Note: set ANTHROPIC_API_KEY before your first run (see .env.example).")
        print("  Install the extra if you haven't:  uv pip install -e '.[claude]'")

    config.save_config(cfg)
    print(f"\nSaved to {config.config_file()} — edit it, or set VNOTE_* env vars, to change.")
    print("Delete that file to run this setup again.\n")
