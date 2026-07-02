"""Start/stop mic capture for the flow client: in-memory 16 kHz mono WAV.

record.py records until Enter in a terminal; the flow client starts and stops
from hotkey events, so this exposes an explicit Recorder.start()/stop() pair.
Backends, same preference order as record.py: the parec/pw-record CLI path
(WSL/Linux), else the sounddevice library (native Windows/macOS/ALSA Linux).
"""

from __future__ import annotations

import io
import signal
import subprocess
import sys
import threading
import time
import wave

from ..config import CHANNELS, SAMPLE_RATE
from ..record import _raw_pcm_cmd


def _wav_bytes(pcm: bytes) -> bytes:
    """Wrap raw s16le PCM in a WAV container, in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(2)  # s16le
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


class Recorder:
    """One start()/stop() capture cycle. Make a fresh one per take."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._pcm = io.BytesIO()
        self._chunks: list[bytes] = []
        self._stream = None
        self._started = 0.0

    def start(self) -> None:
        self._started = time.monotonic()
        cmd = _raw_pcm_cmd()
        if cmd is not None:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            # Drain stdout continuously — at 32 KB/s the pipe buffer fills in ~2 s.
            self._reader = threading.Thread(target=self._drain, daemon=True)
            self._reader.start()
            return
        import sounddevice as sd  # already a core dependency; imported lazily to keep startup light

        def callback(indata, frames, time_info, status):  # noqa: ANN001 - sounddevice signature
            if status:
                print(f"  (audio warning: {status})", file=sys.stderr)
            self._chunks.append(bytes(indata))

        self._stream = sd.RawInputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16", callback=callback)
        self._stream.start()

    def _drain(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for chunk in iter(lambda: self._proc.stdout.read(4096), b""):
            self._pcm.write(chunk)

    def pcm_snapshot(self) -> bytes:
        """Raw PCM captured so far — safe to call while recording (used by VAD polling)."""
        if self._proc is not None:
            return self._pcm.getvalue()
        return b"".join(self._chunks)

    def stop(self) -> tuple[bytes, float]:
        """Stop capturing. Returns (wav_bytes, seconds_recorded)."""
        if self._proc is not None:
            if self._proc.poll() is None:
                self._proc.send_signal(signal.SIGINT)
                try:
                    self._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._proc.terminate()
                    self._proc.wait(timeout=3)
            if self._reader is not None:
                self._reader.join(timeout=3)
            pcm = self._pcm.getvalue()
        elif self._stream is not None:
            self._stream.stop()
            self._stream.close()
            pcm = b"".join(self._chunks)
        else:
            pcm = b""
        return _wav_bytes(pcm), len(pcm) / (2 * CHANNELS * SAMPLE_RATE)
