"""Pure state machine. Selected HOME tile is never automatically a playing game."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock
from time import time


class Mode(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"
    CLEARED = "cleared"


class Screen(str, Enum):
    WAITING = "waiting"
    HOME = "home"
    LAUNCHING = "launching"
    PLAYING = "playing"
    UNKNOWN = "unknown"
    NO_SIGNAL = "no_signal"


@dataclass(frozen=True)
class Activity:
    details: str
    state: str = "Nintendo Switch 2"
    game: str | None = None
    started_at: int | None = None


@dataclass(frozen=True)
class Snapshot:
    mode: Mode
    screen: Screen
    candidate: str | None
    confirmed: str | None
    manual_title: str | None
    activity: Activity | None


class Session:
    """State transitions independent of video, OCR, UI and Discord.

    home() is called only for a recognized HOME UI, non_home() only for
    a substantive non-HOME video frame, and no_signal() only for explicit
    signal failure. A lack of newly-rendered frames alone is not signal loss.
    """

    def __init__(self, *, launch_samples: int = 3, ocr_miss_tolerance: int = 3, clock=time):
        if launch_samples < 2:
            raise ValueError("launch_samples must be >= 2")
        if not 0 <= ocr_miss_tolerance <= 20:
            raise ValueError("ocr_miss_tolerance must be between 0 and 20")
        self._lock = RLock()
        self.mode = Mode.AUTO
        self.screen = Screen.WAITING
        self.candidate: str | None = None
        self.confirmed: str | None = None
        self.manual_title: str | None = None
        self.started_at: int | None = None
        self._non_home_count = 0
        self._launch_samples = launch_samples
        self._ocr_miss_tolerance = ocr_miss_tolerance
        self._ocr_misses = 0
        self._clock = clock

    def home(self, selected_title: str | None) -> None:
        with self._lock:
            self.screen = Screen.HOME
            if selected_title:
                self.candidate = selected_title
                self._ocr_misses = 0
            elif self.candidate is not None:
                # Tolerate a few blank OCR reads without keeping stale titles indefinitely.
                self._ocr_misses += 1
                if self._ocr_misses > self._ocr_miss_tolerance:
                    self.candidate = None
            # A highlighted HOME tile may be suspended; do not claim playing.
            self.confirmed = None
            self.started_at = None
            self._non_home_count = 0

    def non_home(self) -> None:
        with self._lock:
            if self.screen == Screen.HOME:
                self.screen = Screen.LAUNCHING
                self._non_home_count = 1
            elif self.screen == Screen.LAUNCHING:
                self._non_home_count += 1
                if self._non_home_count >= self._launch_samples:
                    if self.candidate:
                        self.confirmed = self.candidate
                        self.started_at = int(self._clock())
                        self.screen = Screen.PLAYING
                    else:
                        self.screen = Screen.UNKNOWN
            elif self.screen in (Screen.WAITING, Screen.NO_SIGNAL):
                # Never guess a game when the app starts in the middle of it.
                self.screen = Screen.UNKNOWN

    def no_signal(self) -> None:
        with self._lock:
            self.screen = Screen.NO_SIGNAL
            self._non_home_count = 0
            self.candidate = None
            self._ocr_misses = 0
            self.confirmed = None
            self.started_at = None

    def set_manual(self, title: str) -> None:
        title = " ".join(title.strip().split())
        if not title:
            raise ValueError("Manual game title cannot be empty")
        if len(title) > 128:
            raise ValueError("Manual game title must not exceed 128 characters")
        with self._lock:
            if self.mode != Mode.MANUAL or self.manual_title != title:
                self.started_at = int(self._clock())
            self.manual_title = title
            self.mode = Mode.MANUAL

    def resume_auto(self) -> None:
        with self._lock:
            self.mode = Mode.AUTO
            self.manual_title = None
            # Explicitly require a fresh HOME observation after override.
            self.screen = Screen.WAITING
            self.candidate = None
            self._ocr_misses = 0
            self.confirmed = None
            self.started_at = None
            self._non_home_count = 0

    def clear(self) -> None:
        with self._lock:
            self.mode = Mode.CLEARED
            self.manual_title = None

    def snapshot(self) -> Snapshot:
        with self._lock:
            activity = None
            if self.mode == Mode.MANUAL and self.manual_title:
                activity = Activity(
                    details=f"Playing {self.manual_title}"[:128],
                    game=self.manual_title,
                    started_at=self.started_at,
                )
            elif self.mode == Mode.AUTO:
                if self.screen in (Screen.HOME, Screen.LAUNCHING):
                    activity = Activity(details="Browsing HOME" if self.screen == Screen.HOME else "Launching game")
                elif self.screen == Screen.PLAYING and self.confirmed:
                    activity = Activity(
                        details=f"Playing {self.confirmed}"[:128],
                        game=self.confirmed,
                        started_at=self.started_at,
                    )
                elif self.screen == Screen.UNKNOWN:
                    activity = Activity(details="Playing on Nintendo Switch")
            return Snapshot(self.mode, self.screen, self.candidate, self.confirmed, self.manual_title, activity)
