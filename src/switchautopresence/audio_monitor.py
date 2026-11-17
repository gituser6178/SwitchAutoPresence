"""AVerMedia/Windows capture-card audio monitoring and read-only diagnostics.

VideoCapture returns video only. On Windows, the capture card may expose its
HDMI audio as a separate recording endpoint. These tools use PortAudio via
sounddevice to measure/monitor that endpoint, never save samples to disk, and
never send the audio over a network.

Discord application audio sharing is NOT guaranteed; remote validation is
required before considering this an end-to-end streaming solution.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log10
from threading import Event, Lock

import numpy as np


def _backend(backend=None):
    if backend is not None:
        return backend
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError('Audio requires python -m pip install -e ".[audio]"') from exc
    return sd


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    hostapi: str
    input_channels: int
    output_channels: int
    default_samplerate: int
    default_input: bool = False
    default_output: bool = False


def describe_audio_devices(backend=None) -> list[AudioDevice]:
    sd = _backend(backend)
    devices = sd.query_devices()
    apis = sd.query_hostapis()
    default_input, default_output = sd.default.device
    return [
        AudioDevice(
            index=i, name=str(info["name"]),
            hostapi=str(apis[int(info["hostapi"])]["name"]),
            input_channels=int(info["max_input_channels"]),
            output_channels=int(info["max_output_channels"]),
            default_samplerate=round(float(info["default_samplerate"])),
            default_input=i == default_input,
            default_output=i == default_output,
        )
        for i, info in enumerate(devices)
        if int(info["max_input_channels"]) > 0 or int(info["max_output_channels"]) > 0
    ]


def list_audio_inputs() -> list[tuple[int, str, int]]:
    """Compatibility wrapper for earlier CLI users."""
    return [(d.index, d.name, d.input_channels)
            for d in describe_audio_devices() if d.input_channels > 0]


def _dbfs(level: float) -> float:
    return round(20 * log10(max(1e-6, min(1.0, float(level)))), 1)


class AudioMeter:
    """Block-level RMS and peak levels with no recorded audio buffer."""

    def __init__(self):
        self._lock = Lock()
        self._blocks = 0
        self._samples = 0
        self._sum_squares = 0.0
        self._peak = 0.0
        self._last_rms = 0.0
        self._last_peak = 0.0

    def observe(self, samples: np.ndarray) -> None:
        if samples is None or samples.size == 0:
            return
        arr = np.asarray(samples, dtype=np.float32)
        squared = np.multiply(arr, arr)
        energy = float(np.sum(squared, dtype=np.float64))
        peak = float(np.max(np.abs(arr)))
        count = int(arr.size)
        with self._lock:
            self._sum_squares += energy
            self._samples += count
            self._peak = max(peak, self._peak)
            self._last_rms = (energy / count) ** .5
            self._last_peak = peak
            self._blocks += 1

    def report(self) -> dict:
        with self._lock:
            total = (self._sum_squares / self._samples) ** .5 if self._samples else 0.0
            return {
                "blocks": self._blocks,
                "samples": self._samples,
                "rms_dbfs": _dbfs(total),
                "peak_dbfs": _dbfs(self._peak),
                "latest_rms_dbfs": _dbfs(self._last_rms),
                "latest_peak_dbfs": _dbfs(self._last_peak),
                "has_signal": self._samples > 0 and total >= 0.002,
                "has_peaks": self._samples > 0 and self._peak >= 0.0056,
                # Peaks alone could be noise; do not treat as confirmed game audio.
            }


def probe_audio_input(
    input_device: int, *, seconds: float = 8.0, samplerate: int | None = None,
    backend=None, wait=None,
) -> dict:
    """Measure audio arriving from one input; does NOT play, record or save.

    Choose ONLY the AVerMedia HDMI recording endpoint. Avoid microphones.
    """
    if input_device < 0:
        raise ValueError("Audio device index must be >= 0")
    if not 1 <= seconds <= 30:
        raise ValueError("Audio test duration must be 1–30 seconds")
    sd = _backend(backend)
    info = sd.query_devices(input_device, "input")
    if samplerate is None:
        samplerate = int(round(float(info.get("default_samplerate") or 48000)))
    if not 8000 <= samplerate <= 192000:
        raise ValueError("Audio sample rate must be 8000–192000 Hz")
    channels = min(2, int(info["max_input_channels"]))
    if channels < 1:
        raise ValueError("Selected device has no input channels")
    meter = AudioMeter()
    warnings: list[str] = []

    def callback(indata, frames, timestamp, status):
        if status and len(warnings) < 4:
            warnings.append(str(status))
        meter.observe(indata)

    try:
        stream = sd.InputStream(
            device=input_device,
            samplerate=samplerate,
            channels=channels,
            dtype="float32",
            blocksize=0,
            callback=callback,
        )
        try:
            stream.start()
            (wait or Event().wait)(seconds)
        finally:
            try:
                stream.stop()
            finally:
                stream.close()
    except Exception as exc:
        raise RuntimeError(
            f"Cannot open recording device {input_device} at {samplerate} Hz: {exc}. "
            "Try another AVerMedia audio index / Windows Recording device or set "
            "its format to 48000 Hz."
        ) from exc

    report = meter.report()
    if not report["blocks"]:
        status = "no_frames"
    elif report["has_signal"]:
        status = "signal"
    elif report["has_peaks"]:
        status = "weak_signal"
    else:
        status = "silent"
    report.update(
        input_device=input_device, device_name=str(info["name"]),
        seconds=float(seconds), samplerate=samplerate,
        channels=channels, warnings=warnings,
        status=status,
    )
    return report


class AudioMonitor:
    """Route GC553Pro HDMI audio into Windows playback without Windows Listen.

    Matching input/output host APIs and rates use a simple duplex Stream.
    Mismatched APIs (e.g. WASAPI input 14 + MME output 5) or rates use separate
    InputStream and OutputStream instances plus a bounded resampling FIFO.
    """

    def __init__(self, input_device: int, output_device: int | None = None, *, backend=None):
        if input_device < 0 or (output_device is not None and output_device < 0):
            raise ValueError("Audio device indices must be >= 0")
        self.input_device = input_device
        self.output_device = output_device
        self.backend = backend
        self._stream = None
        self._streams = []
        self._bridge = None
        self.output_endpoint: int | None = None
        self.input_rate: int | None = None
        self.output_rate: int | None = None
        self.route_mode: str | None = None
        self.meter = AudioMeter()
        self.error: str | None = None
        # Mute affects both local playback and any Discord application-audio
        # capture. Keep sampling HDMI and draining the FIFO while muted.
        self._muted = Event()

    @property
    def muted(self) -> bool:
        return self._muted.is_set()

    def set_muted(self, muted: bool) -> None:
        if muted:
            self._muted.set()
        else:
            self._muted.clear()

    @property
    def running(self) -> bool:
        return bool(self._streams)

    def levels(self) -> dict:
        report = self.meter.report()
        report.update(
            muted=self.muted,
            route_mode=self.route_mode,
            output_endpoint=self.output_endpoint,
            input_rate=self.input_rate,
            output_rate=self.output_rate,
        )
        if self._bridge is not None:
            report.update(self._bridge.stats())
        return report

    def start(self) -> None:
        if self.running:
            return
        from .audio_bridge import AudioBridge
        sd = _backend(self.backend)
        input_info = sd.query_devices(self.input_device, "input")
        output_id = self.output_device
        if output_id is None:
            output_id = sd.default.device[1]
        if output_id is None or int(output_id) < 0:
            raise RuntimeError("No Windows default audio output. Select a playback endpoint.")
        output_id = int(output_id)
        output_info = sd.query_devices(output_id, "output")
        channels = min(
            2, int(input_info["max_input_channels"]), int(output_info["max_output_channels"]),
        )
        if channels < 1:
            raise ValueError("Selected audio endpoints must both have an active channel")
        input_rate = int(round(float(input_info.get("default_samplerate") or 48000)))
        output_rate = int(round(float(output_info.get("default_samplerate") or 48000)))
        input_hostapi = input_info.get("hostapi", -1)
        output_hostapi = output_info.get("hostapi", -1)

        self.input_rate = input_rate
        self.output_rate = output_rate
        self.output_endpoint = output_id
        started = []
        opened = []
        self._bridge = None

        try:
            if input_hostapi == output_hostapi and input_rate == output_rate:
                self.route_mode = "duplex"
                def duplex_callback(indata, outdata, frames, timestamp, status):
                    if status:
                        self.error = f"Audio callback warning: {status}"
                    self.meter.observe(indata)
                    if self._muted.is_set():
                        outdata.fill(0)
                    else:
                        outdata[:] = indata

                stream = sd.Stream(
                    samplerate=input_rate,
                    blocksize=0,
                    device=(self.input_device, output_id),
                    channels=channels,
                    dtype="float32",
                    latency="low",
                    callback=duplex_callback,
                )
                opened.append(stream)
                stream.start()
                started.append(stream)
            else:
                # PortAudio requires one host API for each stream. These two
                # independently clocked streams can use different APIs/rates.
                self.route_mode = "separate"
                bridge = AudioBridge(
                    input_rate=input_rate, output_rate=output_rate, channels=channels,
                )
                self._bridge = bridge

                def input_callback(indata, frames, timestamp, status):
                    if status:
                        self.error = f"Audio input warning: {status}"
                    self.meter.observe(indata)
                    bridge.push(indata)

                def output_callback(outdata, frames, timestamp, status):
                    if status:
                        self.error = f"Audio output warning: {status}"
                    data = bridge.pull(frames)
                    if self._muted.is_set():
                        outdata.fill(0)
                    else:
                        outdata[:] = data

                inp = sd.InputStream(
                    samplerate=input_rate,
                    device=self.input_device,
                    channels=channels,
                    dtype="float32",
                    blocksize=0,
                    latency="low",
                    callback=input_callback,
                )
                opened.append(inp)
                out = sd.OutputStream(
                    samplerate=output_rate,
                    device=output_id,
                    channels=channels,
                    dtype="float32",
                    blocksize=0,
                    latency="low",
                    callback=output_callback,
                )
                opened.append(out)
                inp.start()
                started.append(inp)
                out.start()
                started.append(out)
        except Exception as exc:
            for stream in reversed(started):
                try:
                    stream.stop()
                except Exception:
                    pass
            for stream in reversed(opened):
                try:
                    stream.close()
                except Exception:
                    pass
            self._stream = None
            self._streams = []
            self._bridge = None
            self.route_mode = None
            raise RuntimeError(
                f"HDMI audio routing failed: input {self.input_device} "
                f"({input_rate} Hz, host API {input_hostapi}), output {output_id} "
                f"({output_rate} Hz, host API {output_hostapi}). Details: {exc}"
            ) from exc

        self._streams = opened
        self._stream = opened[-1]
        self.error = None

    def stop(self) -> None:
        streams, self._streams = self._streams, []
        self._stream = None
        self._bridge = None
        first_error = None
        for stream in reversed(streams):
            try:
                stream.stop()
            except Exception as exc:
                first_error = first_error or exc
            try:
                stream.close()
            except Exception as exc:
                first_error = first_error or exc
        self.route_mode = None
        if first_error is not None:
            raise RuntimeError(f"Unable to release audio endpoint: {first_error}") from first_error
