"""Silence endpointing on raw PCM, via the Silero VAD bundled with faster-whisper.

Used client-side by the flow client to decide when an utterance is over
(speak → pause → auto-stop) — no Whisper model is loaded. faster-whisper is a
core dependency, but its import drags in ctranslate2/onnxruntime, so it happens
lazily; callers that care should warm it once (any call does) before recording.
"""

from __future__ import annotations

from .config import SAMPLE_RATE

_BYTES_PER_S = 2 * SAMPLE_RATE  # s16le mono


def speech_spans(pcm_s16le: bytes) -> list[tuple[float, float]]:
    """(start_s, end_s) speech segments detected in raw 16 kHz mono s16le PCM."""
    import numpy as np
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    audio = np.frombuffer(pcm_s16le, dtype=np.int16).astype(np.float32) / 32768.0
    if not len(audio):
        return []
    # Close segments after a short pause and skip end-padding, so the trailing
    # gap we measure in should_stop() tracks real silence promptly.
    opts = VadOptions(min_silence_duration_ms=300, speech_pad_ms=0)
    spans = get_speech_timestamps(audio, opts, sampling_rate=SAMPLE_RATE)
    return [(s["start"] / SAMPLE_RATE, s["end"] / SAMPLE_RATE) for s in spans]


def should_stop(pcm_s16le: bytes, silence_s: float = 1.0, min_speech_s: float = 0.3) -> bool:
    """True once the clip holds >= min_speech_s of speech followed by >= silence_s of silence."""
    duration = len(pcm_s16le) / _BYTES_PER_S
    if duration < min_speech_s + silence_s:
        return False
    spans = speech_spans(pcm_s16le)
    if not spans:
        return False  # nothing said yet — keep listening
    spoken = sum(end - start for start, end in spans)
    return spoken >= min_speech_s and (duration - spans[-1][1]) >= silence_s
