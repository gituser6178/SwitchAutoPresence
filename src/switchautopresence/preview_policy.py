"""Frame rendering policy for Discord stream vs control-panel preview.

Only one display target should be actively rendered at a time. The stream
surface remains eligible while another application covers it; do not infer
occlusion from foreground/focus status. Minimized/withdrawn windows cannot
be relied upon for Discord window capture.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RenderTargets:
    stream_open: bool
    stream_window_normal: bool = False

    @property
    def control_preview(self) -> bool:
        return not self.stream_open

    @property
    def stream_window(self) -> bool:
        return self.stream_open and self.stream_window_normal


class FrameScheduler:
    """Schedule render starts on a steady clock, not 16ms after drawing ends.

    Tk callbacks themselves take time to resize/convert/copy HD frames.
    Waiting 16ms *after* each callback led to ~38fps despite 60fps input.
    This scheduler budgets that work inside each 16.67ms frame period.
    """

    def __init__(self, fps: int = 60):
        if fps < 1 or fps > 240:
            raise ValueError("Target display FPS must be between 1 and 240")
        self.fps = fps
        self._deadline = None

    def next_delay_ms(self, started_at: float, finished_at: float) -> int:
        if finished_at < started_at:
            raise ValueError("finish time must not precede start time")
        period = 1.0 / self.fps
        if self._deadline is None:
            self._deadline = started_at
        # Advance the ideal frame deadline, catching up if rendering ran long.
        self._deadline = max(self._deadline + period, finished_at)
        return max(1, int((self._deadline - finished_at) * 1000))

    def reset(self) -> None:
        self._deadline = None
