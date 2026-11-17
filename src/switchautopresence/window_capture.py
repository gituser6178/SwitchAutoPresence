"""Windows Graphics Capture of the viewer window, never the hardware device.

No video file/screenshot is written, streamed, or uploaded by this module.
"""

from __future__ import annotations

import sys
from queue import Empty, Full, Queue
from threading import Lock
from time import monotonic

import numpy as np


def list_windows() -> list[tuple[int, str]]:
    """Return visible titled top-level windows, useful for viewer selection."""
    if sys.platform != "win32":
        raise RuntimeError("Window enumeration requires Windows")
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    titles: list[tuple[int, str]] = []
    cb_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

    @cb_type
    def enum_callback(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if buf.value.strip():
                    titles.append((int(hwnd), buf.value))
        return True

    user32.EnumWindows.argtypes = [cb_type, wintypes.LPARAM]
    user32.EnumWindows(enum_callback, 0)
    return titles


class WindowCapture:
    """Bounded one-frame sample queue with defensive copy and explicit stop."""

    def __init__(self, title: str, *, interval_seconds: float = 2.0, hwnd: int | None = None,
                 capture_class=None, clock=monotonic):
        if not title and hwnd is None:
            raise ValueError("Provide a viewer window name or numeric HWND")
        if interval_seconds < .25:
            raise ValueError("Frame sampling interval must be >= 0.25s")
        self.title = title
        self.hwnd = hwnd
        self.interval_seconds = interval_seconds
        self.capture_class = capture_class
        self.clock = clock
        self.frames: Queue[tuple[float, np.ndarray]] = Queue(maxsize=1)
        self._control = None
        self._capture = None
        self.closed = False
        self.error: str | None = None
        self._last_sample = -float("inf")
        self._lock = Lock()

    def start(self):
        if self._control is not None:
            return
        try:
            klass = self.capture_class
            if klass is None:
                from windows_capture import WindowsCapture as klass
            settings = dict(cursor_capture=False, draw_border=False,
                            minimum_update_interval=int(self.interval_seconds * 1000))
            if self.hwnd is not None:
                settings["window_hwnd"] = self.hwnd
            else:
                settings["window_name"] = self.title
            capture = klass(**settings)

            @capture.event
            def on_frame_arrived(frame, _control):
                try:
                    now = self.clock()
                    with self._lock:
                        if now - self._last_sample < self.interval_seconds:
                            return
                        self._last_sample = now
                    pixels = frame.frame_buffer
                    if pixels is None or pixels.ndim != 3 or pixels.shape[2] < 3:
                        return
                    # Native frame storage can be reused after callback.
                    bgr = np.ascontiguousarray(pixels[:, :, :3]).copy()
                    try:
                        self.frames.put_nowait((now, bgr))
                    except Full:
                        try:
                            self.frames.get_nowait()
                        except Empty:
                            pass
                        self.frames.put_nowait((now, bgr))
                except Exception as exc:
                    self.error = f"Frame handling error: {exc}"

            @capture.event
            def on_closed():
                self.closed = True
                self.error = "Viewer window closed"

            self.closed = False
            self.error = None
            self._control = capture.start_free_threaded()
            self._capture = capture  # retain Python callback owner during capture
        except Exception as exc:
            self.error = f"Could not capture window '{self.title}': {exc}"
            raise RuntimeError(self.error) from exc

    def poll(self, timeout: float = 0) -> tuple[float, np.ndarray] | None:
        try:
            return self.frames.get(timeout=timeout)
        except Empty:
            return None

    def stop(self) -> None:
        if self._control is not None:
            try:
                self._control.stop()
            except Exception:
                pass
            self._control = None
            self._capture = None
