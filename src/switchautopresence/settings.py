"""Local non-sensitive preferences; avoids storing credentials or captures."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .state import Mode


def settings_path() -> Path:
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / ".config")
    return Path(base) / "SwitchAutoPresence" / "settings.json"


def load_mode(path: Path | None = None) -> tuple[Mode, str | None]:
    path = path or settings_path()
    if not path.exists():
        return Mode.AUTO, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("mode") == "direct":
            # Migrate legacy streaming mode without grabbing video on startup.
            return Mode.CLEARED, None
        mode = Mode(data["mode"])
        title = data.get("manual_title")
        if mode == Mode.MANUAL and (not isinstance(title, str) or not title.strip()):
            return Mode.AUTO, None
        return mode, title if mode == Mode.MANUAL else None
    except (OSError, ValueError, TypeError, KeyError):
        return Mode.AUTO, None


def save_mode(mode: Mode, manual_title: str | None, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"mode": mode.value, "manual_title": manual_title if mode == Mode.MANUAL else None}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def artwork_path() -> Path:
    return settings_path().with_name("artwork.json")


def load_artwork(path: Path | None = None) -> dict[str, str]:
    path = path or artwork_path()
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(result, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in result.items()):
            raise ValueError("Invalid saved game artwork")
        return result
    except (FileNotFoundError, OSError, ValueError):
        return {}


def save_artwork(games: dict[str, str], path: Path | None = None) -> None:
    path = path or artwork_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(games, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
