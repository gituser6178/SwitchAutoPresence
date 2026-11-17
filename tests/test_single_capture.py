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


def test_manual_supports_audio_monitoring_without_video(tmp_path):
    app = make_runtime(tmp_path, device=1)
    app.select_manual("Pokémon Violet")
    class FakeAudio:
        def __init__(self, input_device):
            self.input_device = input_device
            self.running = False
        def start(self): self.running = True
        def stop(self): self.running = False
        def set_muted(self, value): pass
        def levels(self): return {}
    app.enable_audio(14, monitor_factory=FakeAudio)
    assert app.status()["audio_enabled"]
    app.disable_audio()


def test_new_cli_commands():
    parser = make_parser()
    assert parser.parse_args(["app", "--device", "1"]).device == 1
    assert parser.parse_args(["scan-device", "--device", "1"]).device == 1
    assert parser.parse_args(["audio-devices"]).command == "audio-devices"
    assert parser.parse_args(["probe-window"]).command == "probe-window"


# --- Audio signal diagnosis (no hardware access in unit tests) ---

def test_audio_meter_tracks_signal_without_storing_samples():
    from switchautopresence.audio_monitor import AudioMeter
    meter = AudioMeter()
    meter.observe(np.zeros((32, 2), dtype=np.float32))
    assert not meter.report()["has_signal"]
    meter.observe(np.full((480, 2), .25, dtype=np.float32))
    report = meter.report()
    assert report["blocks"] == 2
    assert report["samples"] == 1024
    assert report["has_signal"]
    assert abs(report["latest_peak_dbfs"] + 12.0) < .2


class FakeProbeStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.closed = False
    def start(self):
        self.started = True
        # Fake audio callback; never opens a physical audio device.
        self.kwargs["callback"](
            np.full((480, self.kwargs["channels"]), .16, dtype=np.float32),
            480, None, None,
        )
    def stop(self):
        self.stopped = True
    def close(self):
        self.closed = True


class FakeProbeBackend:
    def __init__(self):
        self.stream = None
    def query_devices(self, index, kind):
        assert index == 9 and kind == "input"
        return {"name": "Test HDMI Audio", "max_input_channels": 2}
    def InputStream(self, **kwargs):
        self.stream = FakeProbeStream(**kwargs)
        return self.stream


def test_audio_test_reports_hdmi_energy_and_closes_portaudio():
    from switchautopresence.audio_monitor import probe_audio_input
    backend = FakeProbeBackend()
    result = probe_audio_input(9, seconds=1, backend=backend, wait=lambda _: None)
    assert result["status"] == "signal"
    assert result["device_name"] == "Test HDMI Audio"
    assert result["samples"] == 960
    assert result["rms_dbfs"] < 0
    assert backend.stream.stopped and backend.stream.closed


class SilentProbeBackend(FakeProbeBackend):
    def InputStream(self, **kwargs):
        self.stream = FakeProbeStream(**kwargs)
        self.stream.kwargs["callback"] = lambda indata, frames, timestamp, status: None
        return self.stream


@pytest.mark.parametrize("input_device,seconds", [(-1, 8), (2, 0), (2, 31)])
def test_audio_test_rejects_invalid_parameters(input_device, seconds):
    from switchautopresence.audio_monitor import probe_audio_input
    with pytest.raises(ValueError):
        probe_audio_input(input_device, seconds=seconds)


def test_audio_device_metadata_includes_host_api_and_output():
    from switchautopresence.audio_monitor import describe_audio_devices
    class Backend:
        class default:
            device = (5, 7)
        def query_devices(self):
            return [
                {"name": "AVerMedia HDMI", "hostapi": 0, "max_input_channels": 2,
                 "max_output_channels": 0, "default_samplerate": 48000},
                {"name": "Headphones", "hostapi": 0, "max_input_channels": 0,
                 "max_output_channels": 2, "default_samplerate": 48000},
            ]
        def query_hostapis(self):
            return [{"name": "Windows WASAPI"}]
    devices = describe_audio_devices(Backend())
    assert devices[0].hostapi == "Windows WASAPI"
    assert devices[1].output_channels == 2
    assert devices[0].index == 0


def test_audio_monitor_exposes_realtime_rms_level():
    backend = FakeAudioBackend()
    monitor = AudioMonitor(5, backend=backend)
    monitor.start()
    data = np.full((128, 2), .1, dtype=np.float32)
    backend.stream.options["callback"](data, np.zeros_like(data), 128, None, None)
    assert monitor.levels()["latest_peak_dbfs"] < 0
    assert monitor.levels()["blocks"] == 1
    monitor.stop()


def test_cli_accepts_audio_test():
    args = make_parser().parse_args(["audio-test", "--input", "3", "--seconds", "6"])
    assert args.input == 3
    assert args.seconds == 6


def test_audio_test_distinguishes_sparse_peaks_from_silence():
    from switchautopresence.audio_monitor import probe_audio_input
    class SparseProbeBackend(FakeProbeBackend):
        def InputStream(self, **kwargs):
            class SparseStream(FakeProbeStream):
                def start(self):
                    self.started = True
                    samples = np.zeros((480, self.kwargs["channels"]), dtype=np.float32)
                    samples[0, 0] = .03
                    self.kwargs["callback"](samples, 480, None, None)
            self.stream = SparseStream(**kwargs)
            return self.stream
    result = probe_audio_input(9, seconds=1, backend=SparseProbeBackend(), wait=lambda _: None)
    assert result["status"] == "weak_signal"
    assert result["has_peaks"] and not result["has_signal"]
    assert result["peak_dbfs"] > -35


def test_audio_test_classifies_true_silence():
    from switchautopresence.audio_monitor import probe_audio_input
    class ZeroProbeBackend(FakeProbeBackend):
        def InputStream(self, **kwargs):
            class ZeroStream(FakeProbeStream):
                def start(self):
                    self.started = True
                    self.kwargs["callback"](
                        np.zeros((480, self.kwargs["channels"]), dtype=np.float32),
                        480, None, None,
                    )
            self.stream = ZeroStream(**kwargs)
            return self.stream
    result = probe_audio_input(9, seconds=1, backend=ZeroProbeBackend(), wait=lambda _: None)
    assert result["status"] == "silent"
    assert not result["has_peaks"]


def test_direct_video_gives_card_to_discord_without_killing_local_audio(tmp_path):
    StubReader.created.clear()
    app = make_runtime(tmp_path, device=1)
    class FakeAudio:
        def __init__(self, input_device):
            self.input_device = input_device
            self.running = False
        def start(self): self.running = True
        def stop(self): self.running = False
        def set_muted(self, value): pass
        def levels(self): return {}
    app.enable_audio(14, monitor_factory=FakeAudio)
    app.start()
    deadline = monotonic() + 2
    while not StubReader.created and monotonic() < deadline:
        sleep(.02)
    assert StubReader.created
    app.select_direct()
    deadline = monotonic() + 2
    while not StubReader.created[0].stopped and monotonic() < deadline:
        sleep(.02)
    assert StubReader.created[0].stopped
    assert app.status()["discord_owns_video"]
    assert app.preview_frame() is None
    assert app.status()["audio_enabled"]
    assert app.session.snapshot().activity.details == "Streaming Nintendo Switch"
    app.select_manual("The Legend of Zelda: Ocarina of Time")
    assert app.status()["audio_enabled"]
    app.stop()


def test_discord_direct_mode_does_not_open_video_on_restart(tmp_path):
    StubReader.created.clear()
    app = make_runtime(tmp_path, device=1)
    app.select_direct()
    app.start()
    sleep(.3)
    assert StubReader.created == []
    app.stop()
    again = make_runtime(tmp_path, device=1)
    assert again.status()["mode"] == Mode.DIRECT.value
