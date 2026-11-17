"""Optional in-process monitoring of capture-card HDMI audio.

Unlike OpenCV VideoCapture, audio uses a separate Windows input endpoint.
The user selects it explicitly. Monitoring plays that input to the default
Windows output; it may then be eligible for Discord application-audio sharing.
This must be verified on the user's Windows/Discord configuration.
No audio is saved or uploaded by this process.
"""

from __future__ import annotations


def list_audio_inputs() -> list[tuple[int, str, int]]:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError('Audio requires python -m pip install -e ".[audio]"') from exc
    return [
        (index, str(info["name"]), int(info["max_input_channels"]))
        for index, info in enumerate(sd.query_devices())
        if info["max_input_channels"] > 0
    ]


class AudioMonitor:
    def __init__(self, input_device: int, output_device: int | None = None, *, backend=None):
        if input_device < 0:
            raise ValueError("Audio input device index must be >= 0")
        self.input_device = input_device
        self.output_device = output_device
        self.backend = backend
        self._stream = None
        self.error: str | None = None

    @property
    def running(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if self._stream is not None:
            return
        if self.backend is None:
            try:
                import sounddevice as sd
            except ImportError as exc:
                raise RuntimeError('Audio requires python -m pip install -e ".[audio]"') from exc
            self.backend = sd

        sd = self.backend
        input_info = sd.query_devices(self.input_device, "input")
        output_id = self.output_device
        if output_id is None:
            output_id = sd.default.device[1]
        output_info = sd.query_devices(output_id, "output")
        channels = min(2, int(input_info["max_input_channels"]), int(output_info["max_output_channels"]))
        if channels < 1:
            raise ValueError("Selected endpoints do not support the same channel count")

        def callback(indata, outdata, _frames, _time, status):
            # Copy capture audio into the application's output stream;
            # no disk write and no network transmit.
            if status:
                self.error = f"Audio callback warning: {status}"
            outdata[:] = indata

        stream = sd.Stream(
            samplerate=48000,
            blocksize=0,
            device=(self.input_device, output_id),
            channels=channels,
            dtype="float32",
            latency="low",
            callback=callback,
        )
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        self._stream = stream
        self.error = None

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
