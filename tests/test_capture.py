import numpy as np
import pytest

from switchautopresence.capture import probe_device


class FakeCapture:
    def __init__(self, frames, opened=True):
        self.frames = iter(frames)
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        return next(self.frames, (False, None))

    def release(self):
        self.released = True


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def tick(self):
        self.now += 0.25
        return self.now


def test_probe_reads_frames_and_releases_capture():
    cap = FakeCapture([(True, np.full((64, 96, 3), 130, dtype=np.uint8))] * 6)
    clock = FakeClock()
    result = probe_device(2, duration_seconds=1, capture_factory=lambda *_: cap, clock=clock.tick)
    assert result.status == "ok"
    assert result.frames_received > 0
    assert (result.width, result.height) == (96, 64)
    assert cap.released


def test_probe_handles_busy_device():
    cap = FakeCapture([], opened=False)
    result = probe_device(0, duration_seconds=1, capture_factory=lambda *_: cap)
    assert result.status == "unavailable"
    assert cap.released


def test_probe_detects_dark_frames():
    cap = FakeCapture([(True, np.zeros((64, 64, 3), dtype=np.uint8))] * 6)
    clock = FakeClock()
    result = probe_device(0, duration_seconds=1, capture_factory=lambda *_: cap, clock=clock.tick)
    assert result.status == "dark_frames"
    assert result.frames_received > 0


def test_probe_no_frames():
    cap = FakeCapture([(False, None)] * 40)
    clock = FakeClock()
    result = probe_device(0, duration_seconds=1, capture_factory=lambda *_: cap, clock=clock.tick, pause=lambda _: None)
    assert result.status == "no_frames"
    assert cap.released


@pytest.mark.parametrize("device,backend,seconds", [(-1,"dshow",5),(0,"unknown",5),(0,"dshow",0),(0,"dshow",61)])
def test_validation(device, backend, seconds):
    with pytest.raises(ValueError):
        probe_device(device, backend=backend, duration_seconds=seconds)
