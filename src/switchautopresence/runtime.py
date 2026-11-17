"""Runtime: viewer-window frames -> offline OCR -> state -> Discord.

No direct capture-card handle is opened by automatic recognition.
"""

from __future__ import annotations

import logging
from threading import Event, RLock, Thread
from time import monotonic

from .artwork import ArtworkCatalog
from .catalog import GameCatalog
from .discord_presence import DiscordPublisher
from .recognition import FrameKind, HomeRecognizer
from .settings import load_mode, save_mode, load_artwork, save_artwork
from .state import Mode, Session
from .window_capture import WindowCapture

LOG = logging.getLogger(__name__)


class Runtime:
    def __init__(
        self, *, app_id: str | None = None, window: str = "VideoGameCapture", hwnd: int | None = None,
        roi=(.08, .19, .84, .19), catalog=None, artwork=None,
        reader_factory=WindowCapture, ocr_engine=None, settings_file=None, artwork_file=None,
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
        self.window = window
        self.hwnd = hwnd
        self.settings_file = settings_file
        self.clock = clock
        self._reader = None
        self._stop = Event()
        self._worker = None
        self._lock = RLock()
        self._dark_count = 0
        self._last_frame_at = None
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
            self._worker.join(timeout=4)
        self._stop_capture()
        self.publisher.close()

    def select_manual(self, title: str, image: str | None = None) -> None:
        # Validate image before changing activity state.
        if image is not None:
            from .artwork import _validate_asset
            _validate_asset(image)
        self.session.set_manual(title)
        if image is not None:
            self.artwork.set_game(title, image)
            try:
                save_artwork(self.artwork.games, self.artwork_file)
            except OSError as exc:
                self.error = f"Could not save game artwork: {exc}"
        self._persist()

    def select_auto(self) -> None:
        self.session.resume_auto()
        self._dark_count = 0
        self._persist()

    def clear(self) -> None:
        self.session.clear()
        self._persist()

    def _persist(self):
        snap = self.session.snapshot()
        try:
            save_mode(snap.mode, snap.manual_title, self.settings_file)
        except OSError as exc:
            self.error = f"Could not save preferences: {exc}"

    def _stop_capture(self):
        if self._reader is not None:
            try:
                self._reader.stop()
            except Exception as exc:
                LOG.debug("Could not stop window capture: %s", exc)
            self._reader = None

    def _start_capture(self):
        try:
            reader = self.reader_factory(self.window, interval_seconds=2.0, hwnd=self.hwnd)
            reader.start()
            self._reader = reader
            self._last_frame_at = None
            self.error = None
        except Exception as exc:
            self._reader = None
            self.error = str(exc)

    def _observe(self, frame):
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

    def _loop(self):
        next_capture_retry = 0.0
        while not self._stop.is_set():
            mode = self.session.snapshot().mode
            if mode != Mode.AUTO:
                self._stop_capture()
            elif self._reader is None and self.clock() >= next_capture_retry:
                self._start_capture()
                next_capture_retry = self.clock() + 15
            if mode == Mode.AUTO and self._reader is not None:
                if self._reader.closed:
                    self.session.no_signal()
                    self.error = self._reader.error or "Viewer was closed"
                    self._stop_capture()
                    next_capture_retry = self.clock() + 5
                else:
                    item = self._reader.poll(timeout=0)
                    if item:
                        self._last_frame_at = item[0]
                        try:
                            self._observe(item[1])
                            self.error = None
                        except Exception as exc:
                            self.error = f"Recognition error: {exc}"
                            LOG.debug(self.error)
            try:
                self.publisher.sync(self.session.snapshot().activity)
            except Exception as exc:
                self.error = f"Discord error: {exc}"
            self._stop.wait(.25)

    def status(self) -> dict:
        snap = self.session.snapshot()
        return {
            "mode": snap.mode.value,
            "screen": snap.screen.value,
            "candidate": snap.candidate,
            "confirmed": snap.confirmed,
            "manual": snap.manual_title,
            "details": snap.activity.details if snap.activity else "No activity",
            "artwork": self.artwork.resolve(snap.activity.game if snap.activity else None).large_image,
            "frame_age": round(self.clock() - self._last_frame_at, 1) if self._last_frame_at else None,
            "error": self.error or self.publisher.error,
        }
