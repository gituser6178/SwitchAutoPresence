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


def test_gui_source_compiles_without_starting_a_windows_display():
    # CI runs on a headless machine and must not open a Tk window.
    from pathlib import Path
    source_path = Path(__file__).resolve().parents[1] / "src" / "switchautopresence" / "gui.py"
    source = source_path.read_text(encoding="utf-8")
    compile(source, str(source_path), "exec")
    assert "pause_inline_preview()" in source
    assert "win.lower()" in source
    assert "frame_scheduler.next_delay_ms(started_at, monotonic())" in source
    assert "root.after(delay, draw)" in source



def test_frame_scheduler_accounts_for_draw_time():
    from switchautopresence.preview_policy import FrameScheduler
    schedule = FrameScheduler(60)
    # A 10ms frame gets only ~6ms more idle, not an extra 16ms.
    assert schedule.next_delay_ms(1.000, 1.010) in (6, 7)
    assert schedule.next_delay_ms(1.016, 1.026) in (6, 7)


def test_frame_scheduler_runs_as_fast_as_possible_when_over_budget():
    from switchautopresence.preview_policy import FrameScheduler
    schedule = FrameScheduler(60)
    assert schedule.next_delay_ms(1.0, 1.030) == 1
    assert schedule.next_delay_ms(1.031, 1.060) == 1
    schedule.reset()
    assert schedule.next_delay_ms(2.0, 2.010) in (6, 7)


def test_frame_scheduler_limits_and_nonmonotonic_clocks():
    from switchautopresence.preview_policy import FrameScheduler
    import pytest
    with pytest.raises(ValueError):
        FrameScheduler(0)
    with pytest.raises(ValueError):
        FrameScheduler(241)
    with pytest.raises(ValueError):
        FrameScheduler().next_delay_ms(3.0, 2.0)
