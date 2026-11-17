"""Discord local IPC Rich Presence; no user auth token or remote uploads."""

from __future__ import annotations

import logging
from time import monotonic

from .artwork import ArtworkCatalog
from .state import Activity

LOG = logging.getLogger(__name__)


class DiscordPublisher:
    """Dedupe updates, reconnect on loss and preserve session timestamps."""

    def __init__(self, app_id: str | None, artwork: ArtworkCatalog, *, rpc_factory=None, clock=monotonic):
        self.app_id = app_id
        self.artwork = artwork
        self.rpc_factory = rpc_factory
        self._clock = clock
        self._rpc = None
        self._last_payload = object()
        self._last_sent = 0.0
        self._retry_after = 0.0
        self.error: str | None = None

    def _factory(self):
        if self.rpc_factory:
            return self.rpc_factory(self.app_id)
        try:
            from pypresence import Presence
        except ImportError as exc:
            raise RuntimeError('Install the Discord extra: pip install -e ".[discord]"') from exc
        return Presence(self.app_id)

    def _connect(self) -> bool:
        if not self.app_id:
            return False
        if self._rpc is not None:
            return True
        now = self._clock()
        if now < self._retry_after:
            return False
        try:
            rpc = self._factory()
            rpc.connect()
            self._rpc = rpc
            self._last_payload = object()
            self.error = None
            return True
        except Exception as exc:
            self.error = f"Discord not connected: {exc}"
            self._retry_after = now + 10.0
            LOG.debug(self.error)
            return False

    def sync(self, activity: Activity | None) -> bool:
        if not self.app_id:
            self.error = "Dry run (no Discord application ID configured)"
            return False
        if not self._connect():
            return False
        payload = self._payload(activity)
        if payload == self._last_payload and self._clock() - self._last_sent < 45:
            return True
        try:
            if payload is None:
                self._rpc.clear()
            else:
                self._rpc.update(**payload)
            self._last_payload = payload
            self._last_sent = self._clock()
            self.error = None
            return True
        except Exception as exc:
            self.error = f"Discord update failed: {exc}"
            LOG.warning(self.error)
            self.close()
            self._retry_after = self._clock() + 10
            return False

    def _payload(self, activity: Activity | None) -> dict | None:
        if activity is None:
            return None
        images = self.artwork.resolve(activity.game)
        payload = {
            "name": "Nintendo Switch",
            "details": activity.details[:128],
            "state": activity.state[:128],
        }
        if activity.started_at is not None:
            payload["start"] = int(activity.started_at)  # pypresence accepts Unix epoch seconds
        if images.large_image:
            payload["large_image"] = images.large_image
            payload["large_text"] = images.large_text[:128]
        if images.small_image:
            payload["small_image"] = images.small_image
            payload["small_text"] = images.small_text[:128]
        return payload

    def preview(self, activity: Activity | None) -> dict | None:
        return self._payload(activity)

    def close(self) -> None:
        if self._rpc is not None:
            try:
                self._rpc.close()
            except Exception:
                pass
        self._rpc = None
