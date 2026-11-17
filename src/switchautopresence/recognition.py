"""Offline OCR of Switch HOME titles with conservative layout checks.

This is an initial heuristic, not a trained HOME classifier. Viewer window
borders/aspect ratios differ, so users can calibrate the normalized title ROI.
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
    """Check neutral margins above the tile row and around bottom controls."""
    h, w = frame.shape[:2]
    if h < 240 or w < 320:
        return False
    top = frame[int(.12 * h):int(.19 * h), int(.30 * w):int(.95 * w)]
    bottom = frame[int(.83 * h):int(.94 * h), int(.32 * w):int(.92 * w)]
    return mostly_neutral(top) > .82 and mostly_neutral(bottom) > .58


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

    def analyze(self, frame: np.ndarray) -> Recognition:
        if frame is None or frame.size == 0 or frame.ndim != 3 or frame.shape[2] < 3:
            return Recognition(FrameKind.DARK)
        if float(np.mean(frame[::32, ::32, :3])) < 4.0:
            return Recognition(FrameKind.DARK)
        if not looks_like_home(frame):
            return Recognition(FrameKind.OTHER)
        crop = crop_region(frame, self.roi)
        if crop.size == 0:
            return Recognition(FrameKind.HOME)
        if crop.shape[0] < 110:
            scale = 110.0 / crop.shape[0]
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        result = self._engine()(crop[:, :, :3])
        texts = tuple(getattr(result, "txts", None) or ())
        scores = tuple(getattr(result, "scores", None) or ())
        if not texts:
            return Recognition(FrameKind.HOME)
        joined = " ".join(str(x) for x in texts)
        valid_scores = [float(x) for x in scores if x is not None]
        confidence = min(valid_scores) if valid_scores else 0.0
        match = self.catalog.match(joined) if confidence >= .55 else None
        # HOME selection is only a candidate; it is never a playing claim.
        return Recognition(FrameKind.HOME, match, confidence, joined[:256])
