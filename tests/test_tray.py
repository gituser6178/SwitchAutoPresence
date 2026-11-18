"""Tray tests without a physical Windows taskbar."""

from queue import SimpleQueue
from threading import Event
from pathlib import Path

from switchautopresence.tray import TrayController


class FakeItem:
    def __init__(self, text, callback, default=False):
        self.text, self.callback, self.default = text, callback, default


class FakeMenu:
    def __init__(self, *items):
        self.items = items


class FakeIcon:
    last = None

    def __init__(self, name, image, title, menu):
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
    Menu, MenuItem, Icon = FakeMenu, FakeItem, FakeIcon


def test_tray_open_and_exit_only():
    events = SimpleQueue()
    tray = TrayController(events, api=FakeTrayAPI, icon_image="fake")
    tray.start()
    icon = FakeIcon.last
    assert icon.started.wait(1)
    assert len(icon.menu.items) == 2
    assert icon.menu.items[0].default
    for item in icon.menu.items:
        item.callback(icon, item)
    assert [events.get_nowait() for _ in range(2)] == ["show", "exit"]
    tray.stop()
    assert icon.stopped.is_set()
    assert not tray.running


def test_tray_start_twice_and_stop_twice():
    tray = TrayController(SimpleQueue(), api=FakeTrayAPI, icon_image="fake")
    tray.start()
    icon = FakeIcon.last
    tray.start()
    assert FakeIcon.last is icon
    tray.stop()
    tray.stop()


def test_gui_has_presence_controls_only():
    file = Path(__file__).resolve().parents[1] / "src" / "switchautopresence" / "gui.py"
    source = file.read_text(encoding="utf-8")
    compile(source, str(file), "exec")
    assert "Minimize to tray" in source
    assert "Try automatic detection" in source
    assert "Set Discord game" in source
    assert "ImageTk" not in source
    assert "cv2" not in source
    assert "audio_monitor" not in source
    assert "stream_window" not in source
