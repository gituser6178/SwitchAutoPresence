"""Offline detection of selected games on the Switch HOME screen.

The Switch 2 HOME title is thin, bright cyan text against a neutral background.
The first implementation sometimes missed it and misclassified gray loading
frames as HOME. This recognizer isolates the cyan line, attempts recognition-
only OCR, and only accepts HOME evidence when text or a cyan title is present.

A selected tile is a candidate, never proof a game is running.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import cv2
import numpy as np

from .catalog import GameCatalog


class FrameKind(str, Enum):
    HOME = "home"
    OTHER = "other"
    DARK = "dark"


@dataclass(frozen=True)
class Recognition:
    kind: FrameKind
    title: str | None = None
    confidence: float = 0.0
    raw_text: str = ""
    method: str = ""


def parse_roi(value: str) -> tuple[float, float, float, float]:
    try:
        values = tuple(float(v.strip()) for v in value.split(","))
    except ValueError as exc:
        raise ValueError("ROI must be normalized x,y,width,height") from exc
    if len(values) != 4 or not all(0 <= x <= 1 for x in values):
        raise ValueError("ROI needs four numbers between 0 and 1")
    x, y, w, h = values
    if min(w, h) <= 0 or x + w > 1 or y + h > 1:
        raise ValueError("ROI must be fully inside the image with nonzero size")
    return values


def crop_region(frame: np.ndarray, roi: tuple[float, float, float, float]) -> np.ndarray:
    h, w = frame.shape[:2]
    x, y, rw, rh = roi
    x0, y0 = int(round(x * w)), int(round(y * h))
    x1, y1 = int(round((x + rw) * w)), int(round((y + rh) * h))
    return frame[y0:y1, x0:x1]


def mostly_neutral(frame: np.ndarray) -> float:
    if frame.size == 0:
        return 0.0
    small = frame[::max(1, frame.shape[0] // 60), ::max(1, frame.shape[1] // 100), :3]
    spread = small.max(axis=2).astype(np.int16) - small.min(axis=2).astype(np.int16)
    return float((spread < 27).mean())


def looks_like_home(frame: np.ndarray) -> bool:
    """Broad background check; NOT sufficient on its own to declare HOME."""
    h, w = frame.shape[:2]
    if h < 240 or w < 320:
        return False
    top = frame[int(.12 * h):int(.19 * h), int(.30 * w):int(.95 * w)]
    bottom = frame[int(.83 * h):int(.94 * h), int(.32 * w):int(.92 * w)]
    return mostly_neutral(top) > .82 and mostly_neutral(bottom) > .58


def cyan_line_crop(region: np.ndarray) -> np.ndarray | None:
    """Extract a likely cyan game-title line from a title band.

    Light-blue text may not be detected as text by default OCR. The cyan
    isolation reduces the neutral background and prevents game tile artwork
    from interfering. No raw frames are saved.
    """
    if region is None or region.size == 0 or region.ndim != 3 or region.shape[2] < 3:
        return None
    bgr = np.ascontiguousarray(region[:, :, :3])
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (79, 40, 110), (112, 255, 255))
    # Guard against artwork that has a single, large cyan patch, instead of
    # widely separated character strokes on one narrow line.
    rows, cols = np.where(mask > 0)
    if len(rows) < 35:
        return None
    y0, y1 = int(rows.min()), int(rows.max())
    x0, x1 = int(cols.min()), int(cols.max())
    if x1 - x0 < bgr.shape[1] * .18 or y1 - y0 > bgr.shape[0] * .62:
        return None
    margin_x = max(4, bgr.shape[1] // 110)
    margin_y = max(3, bgr.shape[0] // 25)
    x0, x1 = max(0, x0 - margin_x), min(bgr.shape[1], x1 + margin_x + 1)
    y0, y1 = max(0, y0 - margin_y), min(bgr.shape[0], y1 + margin_y + 1)
    line = bgr[y0:y1, x0:x1]
    if line.size == 0:
        return None
    # Recognition-only OCR generally performs better when single-line text is
    # at least ~48 pixels high. Preserve proportions.
    scale = max(1.0, 56.0 / line.shape[0])
    return cv2.resize(line, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


class HomeRecognizer:
    def __init__(self, catalog: GameCatalog, *, roi=(.08, .19, .84, .19), engine=None):
        self.catalog = catalog
        self.roi = roi
        self.engine = engine

    def _engine(self):
        if self.engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError as exc:
                raise RuntimeError('Offline OCR requires: python -m pip install -e ".[auto]"') from exc
            self.engine = RapidOCR()
        return self.engine

    def _read(self, img: np.ndarray, *, line: bool) -> tuple[str, float, str | None]:
        engine = self._engine()
        try:
            if line:
                try:
                    result = engine(img, use_det=False, use_cls=False, use_rec=True)
                except TypeError:
                    # Small in-memory test doubles may not expose RapidOCR's
                    # optional stage-switching arguments.
                    result = engine(img)
            else:
                result = engine(img)
        except Exception:
            # OCR runtime failures are surfaced separately by the caller; a
            # transient no-text image is not an application failure.
            raise
        txts = tuple(getattr(result, "txts", None) or ())
        scores = tuple(getattr(result, "scores", None) or ())
        text = " ".join(str(x).strip() for x in txts if str(x).strip())
        good_scores = [float(x) for x in scores if x is not None]
        confidence = min(good_scores) if good_scores else 0.0
        match = None
        if confidence >= .50:
            # A detection pass can include the nearby console icon or split a
            # title across several text boxes. Prefer the whole text, then a line.
            match = self.catalog.match(text)
            if match is None:
                for fragment in txts:
                    match = self.catalog.match(str(fragment))
                    if match:
                        break
        return text[:256], confidence, match

    def analyze(self, frame: np.ndarray) -> Recognition:
        if frame is None or frame.size == 0 or frame.ndim != 3 or frame.shape[2] < 3:
            return Recognition(FrameKind.DARK, method="invalid_video")
        if float(np.mean(frame[::32, ::32, :3])) < 4.0:
            return Recognition(FrameKind.DARK, method="black_signal")
        if not looks_like_home(frame):
            return Recognition(FrameKind.OTHER, method="non_neutral_background")

        region = crop_region(frame, self.roi)
        if region.size == 0:
            return Recognition(FrameKind.OTHER, method="empty_title_region")
        # The Switch 2 HOME title is near y≈0.23, and game artwork starts
        # near y≈0.27. Inspect only the upper strip for cyan title pixels;
        # the larger ROI remains available for conventional OCR fallback.
        title_strip_roi = (self.roi[0], self.roi[1], self.roi[2], min(self.roi[3], .08))
        candidate_line = cyan_line_crop(crop_region(frame, title_strip_roi))
        fallback = None
        if candidate_line is not None:
            text, confidence, match = self._read(candidate_line, line=True)
            if match:
                return Recognition(FrameKind.HOME, match, confidence, text, "cyan_line")
            if text:
                fallback = (text, confidence)
        # Default text detection can still recognize non-cyan themes.
        resized = region
        if region.shape[0] < 110:
            scale = 110.0 / region.shape[0]
            resized = cv2.resize(region, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        text, confidence, match = self._read(resized, line=False)
        if match:
            return Recognition(FrameKind.HOME, match, confidence, text, "normal_ocr")
        if text:
            return Recognition(FrameKind.HOME, None, confidence, text, "unmatched_text")
        if fallback:
            return Recognition(FrameKind.HOME, None, fallback[1], fallback[0], "unmatched_cyan_line")
        if candidate_line is not None:
            return Recognition(FrameKind.HOME, None, 0.0, "", "cyan_title_unreadable")
        # Neutral backgrounds alone misidentified game loading screens as HOME.
        return Recognition(FrameKind.OTHER, None, 0.0, "", "neutral_without_title")
