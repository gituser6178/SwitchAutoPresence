"""Conservative HOME-title matching; never guess titles from arbitrary gameplay."""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

DEFAULT_TITLES = (
    "The Legend of Zelda: Ocarina of Time",
    "The Legend of Zelda: Breath of the Wild",
    "The Legend of Zelda: Tears of the Kingdom",
    "The Legend of Zelda: Echoes of Wisdom",
    "Pokémon Violet",
    "Pokémon Scarlet",
    "Pokémon Legends: Z-A",
    "Mario Kart World",
    "Super Mario Odyssey",
    "Super Smash Bros. Ultimate",
    "Animal Crossing: New Horizons",
)


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


class GameCatalog:
    def __init__(self, titles=DEFAULT_TITLES):
        self.titles = tuple(dict.fromkeys(t.strip() for t in titles if t and t.strip()))

    @classmethod
    def from_file(cls, path: str | Path | None):
        if path is None:
            return cls()
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, list) or not all(isinstance(x, str) for x in obj):
            raise ValueError("Catalog must be a JSON array of title strings")
        return cls((*DEFAULT_TITLES, *obj))

    def match(self, observed: str | None, *, threshold: float = 0.80) -> str | None:
        if not observed:
            return None
        text = normalize_title(observed)
        if len(text) < 5:
            return None
        best_name, best_ratio = None, 0.0
        for title in self.titles:
            normalized = normalize_title(title)
            if text == normalized:
                return title
            # Require a near-whole title, never a partial "Zelda" substring.
            similarity = SequenceMatcher(None, text, normalized).ratio()
            if similarity > best_ratio:
                best_ratio, best_name = similarity, title
        return best_name if best_ratio >= threshold else None
