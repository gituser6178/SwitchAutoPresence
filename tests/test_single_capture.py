"""v0.3 regression tests for one capture owner, mode transitions and audio safety.

No actual AVerMedia, soundcard, or Discord account is accessed.
"""
from __future__ import annotations

from threading import Event
from time import monotonic, sleep

import numpy as np
import pytest

from switchautopresence.audio_monitor import AudioMonitor
from switchautopresence.cli import make_parser
from switchautopresence.device_stream import DeviceStream, VideoFrame, VideoOptions
from switchautopresence.recognition import FrameKind, Recognition
from switchautopresence.runtime import Runtime
from switchautopresence.state import Mode


@pytest.mark.parametrize("kwargs", [
    {"device": -1}, {"device": 1, "width": 1},
    {"device": 1, "height": 5000}, {"device": 1, "fps": 0},
    {"device": 1, "backend": "invalid"},
    {"device": 1, "fourcc": "bad-long-code"},
])
def test_reject_invalid_capture_configs(kwargs):
    with pytest.raises(ValueError):
        VideoOptions(**kwargs)


class FakeCamera:
    def __init__(self, opened=True):
        self.opened = opened
        self.released = Event()
        self.settings = []
        self.calls = 0

    def isOpened(self):
        return self.opened

    def set(self, key, value):
        self.settings.append((key, value))
        return True

    def read(self):
        self.calls += 1
        sleep(.006)
        return True, np.full((720, 1280, 3), self.calls % 230 + 10, dtype=np.uint8)

    def release(self):
        self.released.set()


def test_device_stream_owns_single_handle_and_exposes_latest_frame():
    cameras = []
    def factory(index, backend):
        assert index == 1
        cam = FakeCamera()
        cameras.append(cam)
        return cam
    video = DeviceStream(VideoOptions(1), capture_factory=factory)
    video.start()
    deadline = monotonic() + 2.0
    while video.latest() is None and monotonic() < deadline:
        sleep(.01)
    frame = video.latest()
    assert frame is not None
    assert frame.bgr.shape == (720, 1280, 3)
    assert video.width == 1280
    assert video.height == 720
    assert len(cameras) == 1
    assert video.latest() is not None  # preview and OCR are consumers, not openers
    video.stop()
    assert cameras[0].released.wait(.5)
    assert video.closed


def test_device_stream_reports_busy_device_without_secondary_open():
    cam = FakeCamera(opened=False)
    source = DeviceStream(VideoOptions(1), capture_factory=lambda *_: cam)
    source.start()
    deadline = monotonic() + 2
    while not source.closed and monotonic() < deadline:
        sleep(.01)
    assert source.closed
    assert source.latest() is None
    assert "Discord" in (source.error or "")
    assert cam.released.is_set()


class StubReader:
    created = []

    def __init__(self, options):
        self.options = options
        self.opened = True
        self.closed = False
        self.error = None
        self.width = 640
        self.height = 480
        self.observed_fps = 60
        self.using_defaults = False
        self.stopped = False
        self.frame = VideoFrame(
            1, monotonic(), np.full((480, 640, 3), 180, dtype=np.uint8)
        )
        StubReader.created.append(self)

    def start(self):
        pass

    def latest(self):
        return self.frame

    def stop(self):
        self.stopped = True
        self.opened = False
        self.closed = True


class FakePublisher:
    error = None
    def sync(self, activity):
        return True
    def close(self):
        pass


class StubRecognizer:
    def analyze(self, frame):
        assert frame.shape == (480, 640, 3)
        return Recognition(kind=FrameKind.HOME, title="Pokémon Violet")


def make_runtime(tmp_path, device=None):
    return Runtime(
        device=device, reader_factory=StubReader, publisher=FakePublisher(),
        settings_file=tmp_path / "settings.json",
        artwork_file=tmp_path / "artwork.json",
    )


def test_runtime_uses_same_frame_for_ocr_and_stream_preview(tmp_path):
    StubReader.created.clear()
    app = make_runtime(tmp_path, device=1)
    app.recognizer = StubRecognizer()
    app.start()
    deadline = monotonic() + 2
    while app.session.snapshot().candidate is None and monotonic() < deadline:
        sleep(.025)
    assert app.session.snapshot().candidate == "Pokémon Violet"
    assert app.session.snapshot().activity.details == "Browsing HOME"
    frame = app.preview_frame()
    assert frame is not None
    assert frame.bgr is StubReader.created[0].frame.bgr
    assert len(StubReader.created) == 1
    app.stop()
    assert StubReader.created[0].stopped


def test_manual_mode_releases_hardware_and_stays_locked(tmp_path):
    StubReader.created.clear()
    app = make_runtime(tmp_path, device=1)
    app.start()
    deadline = monotonic() + 2
    while not StubReader.created and monotonic() < deadline:
        sleep(.025)
    assert len(StubReader.created) == 1
    app.select_manual("Mario Kart World")
    deadline = monotonic() + 2
    while not StubReader.created[0].stopped and monotonic() < deadline:
        sleep(.025)
    assert StubReader.created[0].stopped
    assert app.preview_frame() is None
    assert app.session.snapshot().activity.game == "Mario Kart World"
    app.stop()


def test_manual_mode_never_opens_video_on_app_start(tmp_path):
    StubReader.created.clear()
    app = make_runtime(tmp_path, device=1)
    app.select_manual("The Legend of Zelda: Ocarina of Time")
    app.start()
    sleep(.35)
    assert StubReader.created == []
    assert app.status()["mode"] == Mode.MANUAL.value
    app.stop()


def test_clear_also_releases_capture(tmp_path):
    StubReader.created.clear()
    app = make_runtime(tmp_path, device=1)
    app.start()
    deadline = monotonic() + 2
    while not StubReader.created and monotonic() < deadline:
        sleep(.025)
    app.clear()
    deadline = monotonic() + 2
    while not StubReader.created[0].stopped and monotonic() < deadline:
        sleep(.025)
    assert StubReader.created[0].stopped
    assert app.status()["details"] == "No activity"
    app.stop()


class FakeAudioStream:
    def __init__(self, **kwargs):
        self.options = kwargs
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


class FakeAudioBackend:
    class default:
        device = (0, 7)

    def __init__(self):
        self.stream = None

    def query_devices(self, idx, kind):
        if kind == "input":
            assert idx == 5
            return {"max_input_channels": 2}
        assert idx == 7
        return {"max_output_channels": 2}

    def Stream(self, **kwargs):
        self.stream = FakeAudioStream(**kwargs)
        return self.stream


def test_audio_monitor_is_opt_in_and_local_passthrough():
    backend = FakeAudioBackend()
    monitor = AudioMonitor(5, backend=backend)
    assert not monitor.running
    monitor.start()
    assert monitor.running
    assert backend.stream.started
    assert backend.stream.options["device"] == (5, 7)
    assert backend.stream.options["samplerate"] == 48000
    a = np.array([[0.12, 0.24], [0.4, 0.52]], dtype=np.float32)
    output = np.zeros_like(a)
    backend.stream.options["callback"](a, output, 2, None, None)
    assert np.allclose(a, output)
    monitor.stop()
    assert not monitor.running
    assert backend.stream.stopped and backend.stream.closed


def test_audio_monitor_rejects_negative_endpoint():
    with pytest.raises(ValueError):
        AudioMonitor(-1)


def test_manual_rejects_audio_monitoring(tmp_path):
    app = make_runtime(tmp_path, device=1)
    app.select_manual("Pokémon Violet")
    with pytest.raises(ValueError):
        app.enable_audio(5)


def test_new_cli_commands():
    parser = make_parser()
    assert parser.parse_args(["app", "--device", "1"]).device == 1
    assert parser.parse_args(["scan-device", "--device", "1"]).device == 1
    assert parser.parse_args(["audio-devices"]).command == "audio-devices"
    assert parser.parse_args(["probe-window"]).command == "probe-window"
