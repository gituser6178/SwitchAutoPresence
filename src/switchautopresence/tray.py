"""Windows system tray integration, safely isolated from Tkinter's UI thread.

The tray icon uses pystray in a background thread; its callbacks only place
messages in a thread-safe queue. Tkinter processes those messages on its
own main thread to show controls, mute audio or exit.
"""

from __future__ import annotations

from threading import Thread


def create_icon_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((5, 7, 59, 49), radius=10, fill=(29, 91, 186, 255))
    draw.rounded_rectangle((12, 13, 52, 42), radius=5, fill=(12, 19, 35, 255))
    draw.rectangle((25, 52, 39, 57), fill=(29, 91, 186, 255))
    draw.rounded_rectangle((16, 22, 48, 33), radius=5, fill=(100, 208, 249, 255))
    return image


class TrayController:
    def __init__(self, events, *, api=None, icon_image=None):
        self._events = events
        self._api = api
        self._icon_image = icon_image
        self._icon = None
        self._thread = None

    @property
    def running(self) -> bool:
        return self._icon is not None

    def start(self) -> None:
        if self.running:
            return
        try:
            api = self._api
            if api is None:
                import pystray as api
        except ImportError as exc:
            raise RuntimeError(
                'System tray support requires: python -m pip install -e ".[all]"'
            ) from exc

        image = self._icon_image if self._icon_image is not None else create_icon_image()
        menu = api.Menu(
            api.MenuItem("Open SwitchAutoPresence", lambda icon, item: self._events.put("show"), default=True),
            api.MenuItem("Mute / Unmute HDMI audio", lambda icon, item: self._events.put("mute")),
            api.MenuItem("Exit SwitchAutoPresence", lambda icon, item: self._events.put("exit")),
        )
        icon = api.Icon(
            "SwitchAutoPresence",
            image,
            "SwitchAutoPresence — HDMI audio and Discord presence",
            menu,
        )
        self._icon = icon
        self._thread = Thread(target=icon.run, name="switch-tray", daemon=True)
        try:
            self._thread.start()
        except Exception:
            self._icon = None
            self._thread = None
            raise

    def stop(self) -> None:
        icon, self._icon = self._icon, None
        if icon is not None:
            icon.stop()
