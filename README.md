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

After installing, run `vnote --doctor` to check your environment.

For **local** cleanup you also need [Ollama](https://ollama.com). vnote walks you
through picking a model on first run (see below), or pull one yourself:

```bash
ollama pull qwen2.5:14b-instruct   # default; ~10 GB VRAM. Lighter: qwen2.5:7b-instruct / llama3.2:3b-instruct
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
```

You can dictate formatting instructions as you talk ("make that a bulleted list",
"scratch that", "put a heading here") — the cleanup step follows them.

`--redo` is handy for trying a different cleanup intensity without re-transcribing
(transcription is the slow part) — e.g. `vnote --redo voice-notes/2026-… --summary`.

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
| `ANTHROPIC_API_KEY` | — (required for `--backend claude`) |

## Development

```bash
uv pip install -e '.[dev]'   # pytest + ruff
pytest -q                    # unit tests (pure logic; no GPU/mic/network)
ruff check vnote tests
```

The unit tests cover the testable core (transcript parsing, slugging, config
resolution, first-run gating). The hardware paths — mic capture, GPU transcription,
the Ollama/Claude calls — can't run in CI; smoke-test them manually with the bundled
public-domain clip:

```bash
vnote .testdata/jfk.flac
```

## License

[MIT](LICENSE) © Scott Greenwood
