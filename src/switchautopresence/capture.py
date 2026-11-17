"""Read-only video capture diagnostics for the first development milestone.

No images are displayed, encoded, written to disk, or transmitted. This module
only reports aggregate frame counts, dimensions, and approximate brightness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from time import monotonic, sleep
from typing import Callable

import cv2
import numpy as np

BACKENDS = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}


@dataclass(frozen=True)
class ProbeResult:
    device_index: int
    backend: str
    status: str
    duration_seconds: float
    frames_received: int
    failed_reads: int
    width: int | None = None
    height: int | None = None
    average_fps: float = 0.0
    average_brightness: float | None = None
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def list_directshow_devices() -> list[str]:
    """List camera names without opening their video streams.

    DirectShow device ordering usually matches OpenCV CAP_DSHOW indexing, but
    drivers can enumerate them differently; selection may require trial.
    """
    try:
        from pygrabber.dshow_graph import FilterGraph
    except ImportError as exc:
        raise RuntimeError(
            'Device listing needs pygrabber. Install with: py -m pip install -e ".[windows]"'
        ) from exc
    return list(FilterGraph().get_input_devices())


def _brightness(frame: np.ndarray) -> float:
    """Estimate brightness on a reduced sample, not stored frames."""
    return float(np.mean(frame[::32, ::32]))


def probe_device(
    device_index: int,
    *,
    backend: str = "dshow",
    duration_seconds: float = 8.0,
    capture_factory: Callable | None = None,
    clock: Callable[[], float] = monotonic,
    pause: Callable[[float], None] = sleep,
) -> ProbeResult:
    """Attempt to read a specified device for a short, bounded interval.

    Only call when the user explicitly selects an index. Opening some devices
    may fail while another application has exclusive capture access.
    """
    if device_index < 0:
        raise ValueError("device_index must be non-negative")
    if backend not in BACKENDS:
        raise ValueError("backend must be 'dshow' or 'msmf'")
    if not 1 <= duration_seconds <= 60:
        raise ValueError("duration_seconds must be between 1 and 60")

    factory = capture_factory or cv2.VideoCapture
    cap = factory(device_index, BACKENDS[backend])
    started = clock()
    frames = 0
    misses = 0
    width = height = None
    brightness_total = 0.0
    brightness_samples = 0
    try:
        if not cap.isOpened():
            return ProbeResult(
                device_index, backend, "unavailable", 0.0, 0, 0,
                message="Could not open device. It may be busy, unplugged, or indexed differently.",
            )

        # Do not call cap.set(): changing resolution/FPS may disrupt streaming.
        while clock() - started < duration_seconds:
            ok, frame = cap.read()
            if not ok or frame is None or getattr(frame, "size", 0) == 0:
                misses += 1
                pause(0.05)
                if misses >= 40 and frames == 0:
                    break
                continue

            frames += 1
            height, width = int(frame.shape[0]), int(frame.shape[1])
            if frames == 1 or frames % 15 == 0:
                brightness_total += _brightness(frame)
                brightness_samples += 1

        elapsed = max(0.0, clock() - started)
        mean_brightness = brightness_total / brightness_samples if brightness_samples else None
        if frames == 0:
            status, message = "no_frames", "Device opened but no frames arrived. Check HDMI signal and competing capture apps."
        elif mean_brightness is not None and mean_brightness < 3.0:
            status, message = "dark_frames", "Frames arrived but are almost entirely black. Check the console signal."
        else:
            status, message = "ok", "Frames received. This is not yet a game-recognition or simultaneous-access guarantee."

        return ProbeResult(
            device_index=device_index, backend=backend, status=status,
            duration_seconds=round(elapsed, 2), frames_received=frames,
            failed_reads=misses, width=width, height=height,
            average_fps=round(frames / elapsed, 2) if elapsed else 0.0,
            average_brightness=round(mean_brightness, 2) if mean_brightness is not None else None,
            message=message,
        )
    finally:
        cap.release()
