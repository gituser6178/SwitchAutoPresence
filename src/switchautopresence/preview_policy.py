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
