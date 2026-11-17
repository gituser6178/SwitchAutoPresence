"""Windows tray behaviour without a real taskbar or graphical display."""

from queue import SimpleQueue
from threading import Event
from pathlib import Path

from switchautopresence.tray import TrayController


class FakeItem:
    def __init__(self, text, callback, default=False):
        self.text = text
        self.callback = callback
        self.default = default


class FakeMenu:
    def __init__(self, *items):
        self.items = items


class FakeIcon:
    last = None

    def __init__(self, name, image, title, menu):
        self.name = name
        self.image = image
        self.title = title
        self.menu = menu
        self.started = Event()
        self.stopped = Event()
        FakeIcon.last = self

    def run(self):
        self.started.set()
        self.stopped.wait(timeout=2)

    def stop(self):
        self.stopped.set()


class FakeTrayAPI:
    Menu = FakeMenu
    MenuItem = FakeItem
    Icon = FakeIcon


def test_tray_actions_are_queued_for_tk_main_thread():
    events = SimpleQueue()
    tray = TrayController(events, api=FakeTrayAPI, icon_image="mock-icon")
    tray.start()
    assert tray.running
    icon = FakeIcon.last
    assert icon.started.wait(1)
    assert icon.name == "SwitchAutoPresence"
    assert icon.menu.items[0].default
    for item in icon.menu.items:
        item.callback(icon, item)
    assert [events.get_nowait() for _ in range(3)] == ["show", "mute", "exit"]
    tray.stop()
    assert icon.stopped.is_set()
    assert not tray.running


def test_tray_start_is_idempotent_and_stop_is_safe():
    events = SimpleQueue()
    tray = TrayController(events, api=FakeTrayAPI, icon_image="mock-icon")
    tray.start()
    original = FakeIcon.last
    tray.start()
    assert FakeIcon.last is original
    tray.stop()
    tray.stop()


def test_gui_has_tray_and_foreground_stream_picker():
    file = Path(__file__).resolve().parents[1] / "src" / "switchautopresence" / "gui.py"
    code = file.read_text(encoding="utf-8")
    compile(code, str(file), "exec")
    assert "Minimize to tray" in code
    assert "tray_controller[0].start()" in code
    assert 'elif action == "exit"' in code
    assert "win.lift()" in code
    assert "root.after_idle(send_stream_to_background)" not in code
    assert "Discord direct" in code
