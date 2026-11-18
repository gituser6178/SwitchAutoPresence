"""Own exactly one capture-card video handle and publish the latest frame.

A *single* reader thread owns OpenCV's VideoCapture from open to release.
Only HOME recognition reads in-memory frames. No preview, streaming or audio.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

import cv2
import numpy as np


BACKENDS = {"dshow": cv2.CAP_DSHOW, "msmf": cv2.CAP_MSMF}


@dataclass(frozen=True)
class VideoFrame:
    sequence: int
    timestamp: float
    bgr: np.ndarray


@dataclass(frozen=True)
class VideoOptions:
    device: int
    backend: str = "dshow"
    width: int = 1920
    height: int = 1080
    fps: int = 60
    fourcc: str = "MJPG"

    def __post_init__(self) -> None:
        if self.device < 0:
            raise ValueError("Video device index must be non-negative")
        if self.backend not in BACKENDS:
            raise ValueError("Video backend must be 'dshow' or 'msmf'")
        if not (320 <= self.width <= 3840 and 240 <= self.height <= 2160):
            raise ValueError("Capture resolution must be 320x240 through 3840x2160")
        if not (1 <= self.fps <= 240):
            raise ValueError("Capture frame rate must be between 1 and 240")
        if self.fourcc and (len(self.fourcc) != 4 or not self.fourcc.isascii()):
            raise ValueError("Video FOURCC must be four ASCII characters")


class DeviceStream:
    """One background hardware reader; no recording, sharing, or remote I/O.

    Discord may own the device exclusively. Manual selection does not open it.
    """

    def __init__(
        self,
        options: VideoOptions,
        *,
        capture_factory: Callable | None = None,
        clock: Callable[[], float] = time.monotonic,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        self.options = options
        self._factory = capture_factory or cv2.VideoCapture
        self._clock = clock
        self._pause = pause
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest: VideoFrame | None = None
        self._sequence = 0
        self._opened = False
        self._closed = False
        self.width: int | None = None
        self.height: int | None = None
        self.observed_fps: float | None = None
        self.error: str | None = None
        self.using_defaults = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="switch-video-capture", daemon=True)
        self._thread.start()

    def latest(self) -> VideoFrame | None:
        """Return an immutable frame reference, not an image copy.

        Consumers MUST NOT mutate .bgr. Each subsequent capture frame has its
        own ndarray and does not modify previously returned arrays.
        """
        with self._lock:
            return self._latest

    @property
    def opened(self) -> bool:
        with self._lock:
            return self._opened

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def _open(self, configured: bool):
        cap = self._factory(self.options.device, BACKENDS[self.options.backend])
        if not cap.isOpened():
            cap.release()
            return None
        if configured:
            try:
                if self.options.fourcc:
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.options.fourcc))
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.options.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.options.height)
                cap.set(cv2.CAP_PROP_FPS, self.options.fps)
            except Exception:
                # Some drivers refuse individual capture-property changes.
                pass
        return cap

    def _consume(self, cap, configured: bool) -> tuple[bool, bool]:
        """Return (received_any_frames, ended_intentionally)."""
        started = self._clock()
        first_frame_at = None
        received = 0
        failures_started = None
        while not self._stop.is_set():
            ok, frame = cap.read()
            now = self._clock()
            if not ok or frame is None or not getattr(frame, "size", 0):
                if failures_started is None:
                    failures_started = now
                if now - failures_started > 3.0:
                    return received > 0, False
                self._pause(0.03)
                continue

            if frame.ndim != 3 or frame.shape[2] < 3:
                self.error = "Capture device returned an unsupported pixel format"
                return received > 0, False

            failures_started = None
            if first_frame_at is None:
                first_frame_at = now
            received += 1
            height, width = frame.shape[:2]
            with self._lock:
                self._sequence += 1
                self._latest = VideoFrame(self._sequence, now, frame)
                self._opened = True
                self.width = int(width)
                self.height = int(height)
                if received > 5 and now > first_frame_at:
                    self.observed_fps = round((received - 1) / (now - first_frame_at), 1)
            # The camera read blocks on hardware pacing; no busy-spin delay.

        return received > 0, True

    def _run(self) -> None:
        try:
            for configured in (True, False):
                if self._stop.is_set():
                    break
                cap = self._open(configured)
                if cap is None:
                    self.error = (
                        f"Unable to open capture device {self.options.device}. "
                        "Discord may be using it. Choose Manual game mode; "
                        "Auto requires shared video access."
                    )
                    break
                try:
                    self.using_defaults = not configured
                    if not configured:
                        self.error = "Requested format gave no frames; retrying with device defaults"
                    else:
                        self.error = None
                    received, intentional = self._consume(cap, configured)
                finally:
                    cap.release()
                if intentional:
                    break
                if received:
                    self.error = "Video stream stopped delivering frames; check USB/HDMI signal"
                    break
                if configured:
                    continue  # Try the driver's default negotiated format once.
                self.error = "Device opened but returned no video frames"
                break
        except Exception as exc:
            self.error = f"Capture error: {exc}"
        finally:
            with self._lock:
                self._opened = False
                self._closed = True

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        if thread is not None and thread.is_alive():
            self.error = "Video driver did not stop within 3 seconds; close the application before reopening"
        else:
            self._thread = None
