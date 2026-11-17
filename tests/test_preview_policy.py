"""No graphical display needed: verify stream/preview resource policy."""

from switchautopresence.preview_policy import RenderTargets


def test_control_preview_renders_before_stream_open():
    targets = RenderTargets(stream_open=False)
    assert targets.control_preview
    assert not targets.stream_window


def test_stream_window_renders_while_covered_by_other_apps():
    # Window remains normally mapped even if not foreground or visible on screen.
    targets = RenderTargets(stream_open=True, stream_window_normal=True)
    assert not targets.control_preview
    assert targets.stream_window


def test_minimized_stream_does_not_render_duplicate_control_preview():
    targets = RenderTargets(stream_open=True, stream_window_normal=False)
    assert not targets.control_preview
    assert not targets.stream_window


def test_closing_stream_restores_control_preview():
    targets = RenderTargets(stream_open=False, stream_window_normal=False)
    assert targets.control_preview
    assert not targets.stream_window
