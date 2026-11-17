"""Opt-in mapping of game names to Discord asset keys / approved HTTPS images."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class ImageAssets:
    large_image: str | None = None
    small_image: str | None = None
    large_text: str | None = None
    small_text: str | None = None


def _validate_asset(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 512:
        raise ValueError("Asset must be a short Discord asset key or HTTPS image URL")
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("External artwork must be an HTTPS URL without credentials")
    elif any(c in value for c in ("/", "\\", " ")):
        raise ValueError("Asset key may not contain spaces or path separators")
    return value


class ArtworkCatalog:
    def __init__(self, generic: str | None = None, small: str | None = None, games=None):
        self.generic = _validate_asset(generic)
        self.small = _validate_asset(small)
        self.games = {}
        for game, asset in (games or {}).items():
            if not isinstance(game, str) or (asset is not None and not isinstance(asset, str)):
                raise ValueError("Game art mapping must map game titles to strings or null")
            if asset:
                self.games[game.casefold()] = _validate_asset(asset)

    @classmethod
    def from_file(cls, path: str | Path | None):
        if not path:
            return cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("games", {}), dict):
            raise ValueError("Artwork JSON must contain a games mapping")
        return cls(data.get("generic"), data.get("small"), data.get("games", {}))

    def resolve(self, game: str | None) -> ImageAssets:
        image = self.games.get(game.casefold()) if game else None
        image = image or self.generic
        return ImageAssets(
            large_image=image,
            small_image=self.small,
            large_text=game or "Nintendo Switch",
            small_text="Nintendo Switch",
        )

    def set_game(self, game: str, image: str | None) -> None:
        """Set or clear a per-game image URL / Discord asset key."""
        game = game.strip()
        if not game or len(game) > 128:
            raise ValueError("Game title cannot be empty or longer than 128 characters")
        validated = _validate_asset(image)
        if validated:
            self.games[game.casefold()] = validated
        else:
            self.games.pop(game.casefold(), None)
