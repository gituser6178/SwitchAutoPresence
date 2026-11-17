"""Bounded in-memory audio bridge for separate Windows input/output host APIs.

PortAudio cannot open one duplex Stream spanning WASAPI input and MME output.
Use separate streams for the AVerMedia HDMI endpoint and Windows' default
speaker/DAC, with a small FIFO and continuous sample-rate conversion.

No audio is written to disk or sent to a network service by this bridge.
"""

from __future__ import annotations

from math import floor
from threading import Lock

import numpy as np


class AudioBridge:
    """A bounded, resampling SPSC audio FIFO.

    Input callback supplies stereo float32 at input_rate (e.g., 48000).
    Output callback requests float32 at output_rate (e.g., 44100).
    A fractional source-frame position preserves continuity across input
    callback boundaries. Buffered audio remains below ~500 ms even if
    the playback endpoint slows or stops.
    """

    def __init__(
        self, *, input_rate: int, output_rate: int, channels: int = 2,
        latency_ms: int = 70, max_latency_ms: int = 400,
    ) -> None:
        if not 8000 <= input_rate <= 192000 or not 8000 <= output_rate <= 192000:
            raise ValueError("Audio sample rates must be 8000–192000 Hz")
        if channels not in (1, 2):
            raise ValueError("Audio bridge supports mono or stereo only")
        if not 20 <= latency_ms < max_latency_ms <= 1000:
            raise ValueError("Audio latency must be between 20 and 1000 ms")
        self.input_rate = int(input_rate)
        self.output_rate = int(output_rate)
        self.channels = channels
        self._ratio = self.input_rate / self.output_rate
        self._source_samples_seen = 0
        self._next_source_position = 0.0
        self._last_source_sample: np.ndarray | None = None

        self.capacity = max(1024, round(output_rate * max_latency_ms / 1000))
        self.target_frames = min(self.capacity // 2, max(128, round(output_rate * latency_ms / 1000)))
        self._buffer = np.zeros((self.capacity, channels), dtype=np.float32)
        self._write_pos = 0
        self._read_pos = 0
        self._size = 0
        self._primed = False
        self.underruns = 0
        self.dropped_frames = 0
        self._lock = Lock()

    def _resample(self, frames: np.ndarray) -> np.ndarray:
        data = np.asarray(frames, dtype=np.float32)
        if data.ndim != 2 or data.shape[1] != self.channels:
            raise ValueError("Unexpected audio input channel count")
        if len(data) == 0:
            return np.empty((0, self.channels), dtype=np.float32)

        start = self._source_samples_seen
        end = start + len(data) - 1
        if self._last_source_sample is None:
            available_start = start
            available = data
        else:
            available_start = start - 1
            available = np.concatenate((self._last_source_sample[None, :], data), axis=0)
        # Keep fractional positions across calls. This avoids a discontinuity
        # at every InputStream callback boundary (48k -> 44.1k, for example).
        position = max(self._next_source_position, float(available_start))
        if position > end + 1e-9:
            output = np.empty((0, self.channels), dtype=np.float32)
        else:
            count = floor((end - position) / self._ratio + 1e-9) + 1
            positions = position + np.arange(count, dtype=np.float64) * self._ratio
            offsets = positions - available_start
            i0 = np.minimum(offsets.astype(np.int64), len(available) - 1)
            i1 = np.minimum(i0 + 1, len(available) - 1)
            frac = (offsets - i0).astype(np.float32)[:, None]
            output = (available[i0] * (1.0 - frac) + available[i1] * frac).astype(np.float32)
            self._next_source_position = position + count * self._ratio

        self._last_source_sample = data[-1].copy()
        self._source_samples_seen += len(data)
        return output

    def push(self, frames: np.ndarray) -> None:
        converted = self._resample(frames)
        count = len(converted)
        if count == 0:
            return
        trimmed = max(0, count - self.capacity)
        if trimmed:
            converted = converted[-self.capacity:]
            count = len(converted)
        with self._lock:
            self.dropped_frames += trimmed
            excess = max(0, self._size + count - self.capacity)
            if excess:
                self._read_pos = (self._read_pos + excess) % self.capacity
                self._size -= excess
                self.dropped_frames += excess
            first = min(count, self.capacity - self._write_pos)
            self._buffer[self._write_pos:self._write_pos + first] = converted[:first]
            if count > first:
                self._buffer[:count - first] = converted[first:]
            self._write_pos = (self._write_pos + count) % self.capacity
            self._size += count

    def pull(self, frames: int) -> np.ndarray:
        if frames < 0:
            raise ValueError("Requested frame count must be non-negative")
        output = np.zeros((frames, self.channels), dtype=np.float32)
        if not frames:
            return output
        with self._lock:
            if not self._primed:
                if self._size < self.target_frames:
                    return output
                self._primed = True
            count = min(frames, self._size)
            first = min(count, self.capacity - self._read_pos)
            output[:first] = self._buffer[self._read_pos:self._read_pos + first]
            if count > first:
                output[first:count] = self._buffer[:count - first]
            self._read_pos = (self._read_pos + count) % self.capacity
            self._size -= count
            if count < frames:
                self.underruns += 1
                self._primed = False
        return output

    def stats(self) -> dict:
        with self._lock:
            return {
                "buffer_ms": round(1000 * self._size / self.output_rate, 1),
                "underruns": self.underruns,
                "dropped_frames": self.dropped_frames,
                "primed": self._primed,
            }
