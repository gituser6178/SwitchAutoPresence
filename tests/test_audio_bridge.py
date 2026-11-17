"""Tests for capture-to-default-output audio bridge; no physical audio required."""

import numpy as np
import pytest

from switchautopresence.audio_bridge import AudioBridge
from switchautopresence.audio_monitor import AudioMonitor


def test_resampling_48khz_to_44100_continuous_between_blocks():
    bridge = AudioBridge(input_rate=48000, output_rate=44100, channels=2, latency_ms=20)
    delivered = []
    # Simulate 10ms callback frames at a time; don't lose timing between blocks.
    for i in range(30):
        block = np.full((480, 2), 0.35, dtype=np.float32)
        bridge.push(block)
        delivered.append(bridge.pull(441))
    audio = np.concatenate(delivered)
    assert audio.shape == (30 * 441, 2)
    # Initial buffering delays playback, but steady portions preserve amplitude.
    assert np.median(audio[-4410:, 0]) == pytest.approx(.35, abs=.001)
    assert bridge.stats()["underruns"] == 0


def test_resampler_has_no_large_discontinuity_at_block_edges():
    bridge = AudioBridge(input_rate=48000, output_rate=44100, channels=1, latency_ms=20)
    samples = np.arange(0, 4800, dtype=np.float32).reshape(-1, 1) / 4800.0
    for block in np.array_split(samples, 10):
        bridge.push(block)
    received = bridge.pull(700)
    # Smooth ramp: no discontinuity at 480-sample input callback boundaries.
    assert np.all(np.diff(received[:, 0]) >= -1e-5)
    assert np.max(np.abs(np.diff(received[:, 0]))) < 0.001


def test_buffer_is_bounded_and_counts_drops():
    bridge = AudioBridge(input_rate=48000, output_rate=44100, channels=2, latency_ms=60)
    bridge.push(np.full((48000, 2), .3, dtype=np.float32))
    state = bridge.stats()
    assert state["dropped_frames"] > 0
    assert 0 <= state["buffer_ms"] <= 400


def test_short_read_is_zero_filled_and_counts_underrun():
    bridge = AudioBridge(input_rate=48000, output_rate=48000, channels=2, latency_ms=20)
    bridge.push(np.full((100, 2), .3, dtype=np.float32))
    assert np.count_nonzero(bridge.pull(100)) == 0  # not primed
    bridge.push(np.full((2500, 2), .3, dtype=np.float32))
    output = bridge.pull(4000)
    assert np.max(output) == pytest.approx(.3)
    assert np.all(output[2600:] == 0)
    assert bridge.stats()["underruns"] == 1


class FakeSplitStream:
    def __init__(self, kind, kwargs, *, fail_start=False):
        self.kind = kind
        self.kwargs = kwargs
        self.fail_start = fail_start
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self):
        if self.fail_start:
            raise OSError("failed to start simulated output")
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


class FakeSplitBackend:
    class default:
        device = (0, 5)

    def __init__(self, fail_output_start=False):
        self.input_stream = None
        self.output_stream = None
        self.fail_output_start = fail_output_start

    def query_devices(self, index, kind):
        if kind == "input":
            assert index == 14
            return {
                "name": "HDMI (AVerMedia GC553Pro)",
                "max_input_channels": 2,
                "default_samplerate": 48000.0,
                "hostapi": 2,  # Windows WASAPI
            }
        assert kind == "output"
        assert index == 5
        return {
            "name": "Speakers (TOPPING USB DAC)",
            "max_output_channels": 2,
            "default_samplerate": 44100.0,
            "hostapi": 0,  # MME
        }

    def InputStream(self, **kwargs):
        self.input_stream = FakeSplitStream("input", kwargs)
        return self.input_stream

    def OutputStream(self, **kwargs):
        self.output_stream = FakeSplitStream(
            "output", kwargs, fail_start=self.fail_output_start
        )
        return self.output_stream

    def Stream(self, **kwargs):
        raise AssertionError("Cross-host duplex Stream must never be called")


def test_cross_host_avermedia_to_default_topping_audio():
    backend = FakeSplitBackend()
    monitor = AudioMonitor(14, backend=backend)
    assert not monitor.running
    monitor.start()
    assert monitor.running
    assert monitor.route_mode == "separate"
    assert monitor.output_endpoint == 5
    assert monitor.input_rate == 48000
    assert monitor.output_rate == 44100
    assert backend.input_stream.kwargs["device"] == 14
    assert backend.output_stream.kwargs["device"] == 5

    input_callback = backend.input_stream.kwargs["callback"]
    output_callback = backend.output_stream.kwargs["callback"]
    for _ in range(15):
        input_callback(np.full((480, 2), .2, dtype=np.float32), 480, None, None)
        out = np.empty((441, 2), dtype=np.float32)
        output_callback(out, 441, None, None)
    assert np.max(out) == pytest.approx(.2, abs=.001)
    assert np.min(out) == pytest.approx(.2, abs=.001)
    assert monitor.levels()["has_signal"]
    assert monitor.levels()["route_mode"] == "separate"
    monitor.stop()
    assert not monitor.running
    assert backend.input_stream.closed and backend.output_stream.closed


def test_cross_host_failure_closes_both_streams():
    backend = FakeSplitBackend(fail_output_start=True)
    monitor = AudioMonitor(14, backend=backend)
    with pytest.raises(RuntimeError, match="routing failed"):
        monitor.start()
    assert not monitor.running
    assert backend.input_stream.started
    assert backend.input_stream.stopped
    assert backend.input_stream.closed
    assert backend.output_stream.closed


def test_audio_bridge_refuses_bad_settings():
    with pytest.raises(ValueError):
        AudioBridge(input_rate=0, output_rate=44100)
    with pytest.raises(ValueError):
        AudioBridge(input_rate=48000, output_rate=44100, channels=3)
    with pytest.raises(ValueError):
        AudioBridge(input_rate=48000, output_rate=44100, latency_ms=800, max_latency_ms=700)
