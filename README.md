# vnote — local voice notes, from your mic to your clipboard

[![CI](https://github.com/greenwoodms06/vnote/actions/workflows/ci.yml/badge.svg)](https://github.com/greenwoodms06/vnote/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A small command-line tool for **dictated notes**: speak (or hand it an audio file),
transcribe locally on your **GPU** with [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
(`large-v3-turbo`), tidy the transcript with a **local LLM**, and drop the cleaned
Markdown straight onto your **clipboard**. Everything stays on your machine by default.

It's built for the workflow that the polished dictation apps skip: a **CLI on WSL2 /
Linux** that records through WSLg's PulseAudio bridge, runs Whisper on CUDA, and pastes
into whatever you're typing in. If you're on macOS and want point-and-talk dictation,
[yapper](https://github.com/ahmedlhanafy/yapper) or
[local-whisper](https://github.com/luisalima/local-whisper) are more polished choices.

> This is a personal tool I use daily and am sharing as-is — no support promised, but
> issues and PRs are welcome.

## Platform support

| Platform | Mic recording | GPU transcription | Clipboard | Status |
|---|---|---|---|---|
| **WSL2** (Windows) | `parec` via WSLg | CUDA | `clip.exe` | **tested — primary** |
| **Native Linux** | `parec` / `pw-record` / `sounddevice` | CUDA | `wl-copy` / `xclip` / `xsel` | **tested** |
| Windows (native) | `sounddevice` | CUDA | `clip.exe` | untested — should work |
| macOS | `sounddevice` | CPU only (no CUDA) | `pbcopy` | untested — CPU-only |
| any | — (file mode) | CUDA / CPU | best-effort | processing audio files works everywhere |

Processing an existing file (`vnote memo.m4a`) needs no audio setup at all.

## Install

Quickest — installs the `vnote` command in its own isolated environment:

```bash
uv tool install git+https://github.com/greenwoodms06/vnote
```

Or from a clone (recommended if you want to hack on it):

```bash
uv sync                       # creates .venv with deps
uv pip install -e .           # installs the `vnote` command
# optional: cloud cleanup backend
uv pip install -e '.[claude]' # adds the Anthropic SDK for `--backend claude`
```

> **Invoking it from a clone:** the `vnote` command lives inside the project's
> `.venv`, so run it with **`uv run vnote …`** (uv handles the venv for you), or
> activate the venv first (`source .venv/bin/activate`) and then call `vnote`
> directly. The `uv tool install` route above instead puts `vnote` on your PATH
> globally, so no prefix is needed. The examples below use the bare `vnote` form.

After installing, run `vnote --doctor` (or `uv run vnote --doctor`) to check your environment.

For **local** cleanup you also need [Ollama](https://ollama.com). vnote walks you
through picking a model on first run (see below), or pull one yourself:

```bash
ollama pull qwen2.5:14b-instruct   # default; ~10 GB VRAM. Lighter: qwen2.5:7b-instruct / llama3.2:3b
```

The first transcription downloads the Whisper model (~1.6 GB) to `~/.cache/huggingface`.

> **Audio on WSL:** WSL has no native ALSA device, so recording goes through WSLg's
> PulseAudio bridge via `parec`. Install it with `sudo apt install -y pulseaudio-utils`.
> `pw-record`, `ffmpeg`, or the `sounddevice` library are used as fallbacks if present.

## First run

The first time you run `vnote` interactively, it asks two quick questions — which
cleanup backend (local Ollama vs. cloud Claude) and, for Ollama, which model size
(pre-selected from your detected GPU memory). Your choice is saved to
`~/.config/vnote/config.json`. Delete that file to run setup again, or override
anytime with a flag or a `VNOTE_*` environment variable. The prompt is skipped when
input isn't a terminal, so scripts and pipelines are never blocked.

## Use

(From a clone, prefix these with `uv run` — e.g. `uv run vnote` — or activate the
venv first. See [Install](#install).)

```bash
vnote                      # record from the mic; press Enter to stop
vnote memo.m4a             # process an existing audio file
vnote --light              # faithful cleanup (de-fill + grammar only)
vnote --edit               # editorial cleanup — reorganize, headings, lists (default)
vnote --summary            # condensed rewrite
vnote --raw                # transcript only, no LLM
vnote --backend claude     # use the Claude backend (needs the [claude] extra + key)
vnote --no-clipboard       # don't touch the clipboard
vnote --redo DIR           # re-run cleanup on a saved note (skips transcription)
vnote --stdout             # also print the note to stdout (for piping)
vnote -o, --open           # open the new note in $EDITOR afterward
vnote --serve              # keep models warm in a localhost daemon (see below)
vnote --no-daemon          # ignore a running daemon; load models in-process
```

You can dictate formatting instructions as you talk ("make that a bulleted list",
"scratch that", "put a heading here") — the cleanup step follows them.

`--redo` is handy for trying a different cleanup intensity without re-transcribing
(transcription is the slow part) — e.g. `vnote --redo voice-notes/2026-… --summary`.

### Warm daemon (optional, faster)

Normally every run loads the Whisper model into VRAM first — several seconds
before transcription even starts. Leave a daemon running and repeat runs skip
that entirely:

```bash
vnote --serve              # terminal A: loads the model once, then serves on 127.0.0.1:8760
vnote memo.m4a             # terminal B: detects the daemon and starts transcribing immediately
```

The CLI probes for a daemon on each run and silently falls back to in-process
models when none is up, so nothing else changes — same output, same files.
`--no-daemon` forces in-process for a single run, `vnote --doctor` shows whether
a daemon is up, and `VNOTE_DAEMON_HOST` / `VNOTE_DAEMON_PORT` move the address.
It binds to localhost only, with no auth — it's a single-user convenience, not a
network service.

### Flow mode — dictate into any app (experimental)

`vnote-flow` is a thin push-to-talk client for the daemon: press
**ctrl+shift+space** anywhere, speak, press it again — the transcript is pasted
into whatever app has focus (clipboard-paste, with your old clipboard restored).

```bash
vnote --serve                        # somewhere: the warm daemon
vnote-flow                           # hotkey loop (needs the [flow] extra: pynput)
vnote-flow --vad                     # auto-stop after a ~1s pause (no second key press)
vnote-flow --clean                   # fast LLM 'dictation' cleanup before pasting (default: raw)
vnote-flow --stream                  # live partial text on the console while you speak
vnote-flow --once --print            # one hotkey-free cycle to stdout (works anywhere)
vnote-flow --inject type             # per-character typing instead of pasting
```

Spoken commands **"new line"**, **"new paragraph"** and **"scratch that"** are
applied to the transcript by rule, even without `--clean`. With `--clean`, a
light dictation prompt also fixes punctuation/fillers and handles the fuzzier
commands ("period", "quote … unquote") — point `VNOTE_DICTATION_MODEL` at a
small model (e.g. `llama3.2:3b`) to keep it fast.

Run it on the machine that owns the **keyboard and mic**:

| Setup | Daemon | `vnote-flow` |
|---|---|---|
| Native Linux / Windows / macOS | same machine | same machine (`pip install 'vnote[flow]'`) |
| **WSL2** | inside WSL (CUDA) | **Windows Python** — `pip install 'vnote[flow]'`; localhost reaches the WSL daemon out of the box |

> If `vnote-flow` isn't on PATH after a Windows `pip install`, run it as
> `py -m vnote.client.app` instead.

Configure with `VNOTE_HOTKEY` (e.g. `ctrl+alt+d`) and `VNOTE_INJECT`
(`auto`/`paste`/`type`). Caveats: a non-elevated client can't type into
elevated/admin windows (Windows UIPI — fails silently); Wayland needs `wtype`
or `ydotool` for injection. Flow mode is ephemeral by design — it doesn't write
session folders; use `vnote` for notes you want to keep.

### Check & configure

```bash
vnote --doctor             # check recorder, GPU, clipboard, and backend — with fixes
vnote --config             # show resolved settings and the config-file path
vnote --setup              # re-run the interactive first-run setup
```

**No GPU?** Use `--backend claude` (cleanup runs in the cloud); transcription falls
back to CPU automatically — slower, but it works.

## Output

Each run writes `voice-notes/YYYY-MM-DD-HHMM-<slug>/`:

| file | what |
|---|---|
| `audio.wav` | the recording (or a copy of the file you passed) |
| `transcript.txt` | raw Whisper output |
| `note.md` | the cleaned, reorganized note — the thing you keep |
| `meta.json` | model, durations, language, timestamps |

`note.md` is also copied to your clipboard.

## Config (env vars)

Environment variables override the saved first-run choice. A `.env` in the current
directory is auto-loaded (see `.env.example`).

| var | default |
|---|---|
| `VNOTE_DIR` | `./voice-notes` |
| `VNOTE_WHISPER_MODEL` | `large-v3-turbo` |
| `VNOTE_BACKEND` | `ollama` |
| `VNOTE_OLLAMA_MODEL` | `qwen2.5:14b-instruct` |
| `VNOTE_CLAUDE_MODEL` | `claude-sonnet-4-6` |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` |
| `VNOTE_DAEMON_HOST` | `127.0.0.1` |
| `VNOTE_DAEMON_PORT` | `8760` |
| `VNOTE_HOTKEY` | `ctrl+shift+space` (vnote-flow) |
| `VNOTE_INJECT` | `auto` (vnote-flow: `paste`/`type`) |
| `VNOTE_VAD` | off (vnote-flow: `1` = auto-stop on silence) |
| `VNOTE_VAD_SILENCE` | `1.0` (seconds of pause that end an utterance) |
| `VNOTE_STREAM` | off (vnote-flow: `1` = transcribe while speaking) |
| `VNOTE_DICTATION_MODEL` | the `ollama_model` (small/fast model for `--clean` dictation) |
| `ANTHROPIC_API_KEY` | — (required for `--backend claude`) |

## Development

```bash
uv pip install -e '.[dev]'   # pytest + ruff
uv run pytest -q             # unit tests (pure logic; no GPU/mic/network)
uv run ruff check vnote tests
```

The unit tests cover the testable core (transcript parsing, slugging, config
resolution, first-run gating). The hardware paths — mic capture, GPU transcription,
the Ollama/Claude calls — can't run in CI; smoke-test them manually with the bundled
public-domain clip:

```bash
uv run vnote .testdata/jfk.flac
```

## License

[MIT](LICENSE) © Scott Greenwood
