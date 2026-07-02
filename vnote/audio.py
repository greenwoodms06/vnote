"""Tiny shared audio helpers (stdlib only)."""

from __future__ import annotations

import io
import wave

from .config import CHANNELS, SAMPLE_RATE

BYTES_PER_S = 2 * CHANNELS * SAMPLE_RATE  # s16le


def wav_bytes(pcm_s16le: bytes) -> bytes:
    """Wrap raw s16le PCM in a WAV container, in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)  # s16le
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm_s16le)
    return buf.getvalue()
