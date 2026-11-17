"""Run the single-owner capture feed, GUI preview, OCR and Discord presence.

Capture ownership lives inside DeviceStream. The GUI and recognizer only
borrow its latest in-memory frame; neither opens a second AVerMedia handle.
Manual mode releases the card so users may stream it directly from Discord.
"""

from __future__ import annotations

import logging
from threading import Event, RLock, Thread
from time import monotonic

from .artwork import ArtworkCatalog, _validate_asset
from .audio_monitor import AudioMonitor
from .catalog import GameCatalog
from .device_stream import DeviceStream, VideoOptions
from .discord_presence import DiscordPublisher
from .recognition import FrameKind, HomeRecognizer
from .settings import load_mode, save_mode, load_artwork, save_artwork
from .state import Mode, Session

LOG = logging.getLogger(__name__)


class Runtime:
    """Screen-independent state plus one owned video source.

    The main UI remains responsive if a driver takes time to open a device.
    Video is never recorded, uploaded or copied into an extra capture handle.
    """

    def __init__(
        self, *, app_id: str | None = None, device: int | None = None,
        backend: str = "dshow", width: int = 1920, height: int = 1080,
        fps: int = 60, roi=(.08, .19, .84, .19), catalog=None, artwork=None,
        reader_factory=DeviceStream, ocr_engine=None, settings_file=None, artwork_file=None,
        publisher=None, clock=monotonic,
    ):
        self.session = Session()
        self.catalog = catalog or GameCatalog()
        self.artwork = artwork or ArtworkCatalog()
        self.artwork_file = artwork_file
        for title, url in load_artwork(artwork_file).items():
            try:
                self.artwork.set_game(title, url)
            except ValueError:
                continue
        self.publisher = publisher or DiscordPublisher(app_id, self.artwork)
        self.reader_factory = reader_factory
        self.recognizer = HomeRecognizer(self.catalog, roi=roi, engine=ocr_engine)
        self.settings_file = settings_file
        self.clock = clock
        self._config_lock = RLock()
        self._options = VideoOptions(device, backend, width, height, fps) if device is not None else None
        self._active_options = None
        self._reader: DeviceStream | None = None
        self._stop = Event()
        self._worker: Thread | None = None
        self._dark_count = 0
        self._last_frame_at: float | None = None
        self._last_sequence = 0
        self._next_recognition = 0.0
        self._audio: AudioMonitor | None = None
        self.error: str | None = None
        mode, manual = load_mode(settings_file)
        if mode == Mode.MANUAL and manual:
            self.session.set_manual(manual)
        elif mode == Mode.CLEARED:
            self.session.clear()

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = Thread(target=self._loop, daemon=True, name="switch-presence")
        self._worker.start()

    def stop(self) -> None:
        self._stop.set()
        if self._worker:
            self._worker.join(timeout=5)
        self.disable_audio()
        self._stop_capture()
        self.publisher.close()

    def configure_video(
        self, device: int, *, backend: str = "dshow",
        width: int = 1920, height: int = 1080, fps: int = 60,
    ) -> None:
        options = VideoOptions(device, backend, width, height, fps)
        with self._config_lock:
            self._options = options

    def select_manual(self, title: str, image: str | None = None) -> None:
        if image is not None:
            _validate_asset(image)
        self.error = None  # Clear any obsolete capture error on mode switch
        self.session.set_manual(title)
        if image is not None:
            self.artwork.set_game(title, image)
            try:
                save_artwork(self.artwork.games, self.artwork_file)
            except OSError as exc:
                self.error = f"Could not save artwork: {exc}"
        self._persist()

    def select_auto(self) -> None:
        self.error = None
        self.session.resume_auto()
        self._dark_count = 0
        self._persist()

    def clear(self) -> None:
        self.error = None
        self.session.clear()
        self._persist()

    def _persist(self) -> None:
        snap = self.session.snapshot()
        try:
            save_mode(snap.mode, snap.manual_title, self.settings_file)
        except OSError as exc:
            self.error = f"Could not save preferences: {exc}"

    def enable_audio(self, input_device: int, *, monitor_factory=AudioMonitor) -> None:
        if self.session.snapshot().mode != Mode.AUTO:
            raise ValueError("Enable automatic mode before audio monitoring")
        if self._audio:
            self.disable_audio()
        audio = monitor_factory(input_device)
        try:
            audio.start()
        except Exception as exc:
            self.error = f"Audio monitoring could not start: {exc}"
            raise RuntimeError(self.error) from exc
        self._audio = audio

    def disable_audio(self) -> None:
        if self._audio is not None:
            audio, self._audio = self._audio, None
            try:
                audio.stop()
            except Exception as exc:
                self.error = f"Audio stop problem: {exc}"

    def _stop_capture(self) -> None:
        with self._config_lock:
            reader, self._reader = self._reader, None
            self._active_options = None
        if reader is not None:
            try:
                reader.stop()
            except Exception as exc:
                self.error = f"Capture could not stop: {exc}"

    def _start_capture(self, options: VideoOptions) -> None:
        try:
            reader = self.reader_factory(options)
            reader.start()
            with self._config_lock:
                self._reader = reader
                self._active_options = options
            self._last_frame_at = None
            self._last_sequence = 0
            self._next_recognition = 0.0
            self.error = None
        except Exception as exc:
            self.error = f"Capture startup failed: {exc}"

    def _observe(self, frame) -> None:
        result = self.recognizer.analyze(frame)
        if result.kind == FrameKind.HOME:
            self._dark_count = 0
            self.session.home(result.title)
        elif result.kind == FrameKind.DARK:
            self._dark_count += 1
            if self._dark_count >= 4:
                self.session.no_signal()
        else:
            self._dark_count = 0
            self.session.non_home()

    def _loop(self) -> None:
        next_capture_retry = 0.0
        while not self._stop.is_set():
            now = self.clock()
            mode = self.session.snapshot().mode
            with self._config_lock:
                desired = self._options
                reader = self._reader
                active = self._active_options

            if mode != Mode.AUTO or desired is None:
                if reader is not None:
                    self._stop_capture()
                if self._audio is not None:
                    self.disable_audio()
                if mode == Mode.AUTO and desired is None:
                    self.error = "Select a capture device index, or use Manual mode"
            else:
                if reader is not None and active != desired:
                    self._stop_capture()
                    reader = None
                    next_capture_retry = 0.0

                if reader is None and now >= next_capture_retry:
                    self._start_capture(desired)
                    next_capture_retry = now + 8.0
                    with self._config_lock:
                        reader = self._reader

                if reader is not None:
                    if reader.closed:
                        self.session.no_signal()
                        self.error = reader.error or "Video capture stopped"
                        self.disable_audio()
                        self._stop_capture()
                        next_capture_retry = now + 8.0
                    else:
                        packet = reader.latest()
                        if packet is not None and packet.sequence != self._last_sequence:
                            self._last_sequence = packet.sequence
                            self._last_frame_at = packet.timestamp
                            if now >= self._next_recognition:
                                self._next_recognition = now + 2.0
                                try:
                                    self._observe(packet.bgr)
                                    self.error = None
                                except Exception as exc:
                                    self.error = f"Recognition error: {exc}"
                                    LOG.debug(self.error)
            try:
                self.publisher.sync(self.session.snapshot().activity)
            except Exception as exc:
                self.error = f"Discord update error: {exc}"

            self._stop.wait(.25)

    def preview_frame(self):
        """Latest same-owner camera frame, or None when not capturing."""
        if self.session.snapshot().mode != Mode.AUTO:
            return None
        with self._config_lock:
            reader = self._reader
        return reader.latest() if reader is not None and not reader.closed else None

    def status(self) -> dict:
        snap = self.session.snapshot()
        with self._config_lock:
            reader = self._reader
            options = self._options
        return {
            "mode": snap.mode.value,
            "screen": snap.screen.value,
            "candidate": snap.candidate,
            "confirmed": snap.confirmed,
            "manual": snap.manual_title,
            "details": snap.activity.details if snap.activity else "No activity",
            "artwork": self.artwork.resolve(snap.activity.game if snap.activity else None).large_image,
            "device": options.device if options else None,
            "capture_open": bool(reader and reader.opened),
            "capture_resolution": f"{reader.width}x{reader.height}" if reader and reader.width else None,
            "capture_fps": reader.observed_fps if reader else None,
            "using_defaults": bool(reader and reader.using_defaults),
            "frame_age": round(self.clock() - self._last_frame_at, 1) if self._last_frame_at else None,
            "audio_enabled": bool(self._audio and self._audio.running),
            "error": self.error or (reader.error if reader else None) or self.publisher.error,
        }
