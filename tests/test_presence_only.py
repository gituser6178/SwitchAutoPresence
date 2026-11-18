"""Migration and removal of media streaming behavior."""

import json

from switchautopresence.settings import load_mode
from switchautopresence.state import Mode


def test_legacy_discord_direct_mode_does_not_grab_video(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"mode": "direct", "manual_title": None}), encoding="utf-8")
    assert load_mode(path) == (Mode.CLEARED, None)


def test_manual_title_survives_old_settings(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"mode": "manual", "manual_title": "Pokémon Violet"}), encoding="utf-8")
    assert load_mode(path) == (Mode.MANUAL, "Pokémon Violet")


def test_runtime_has_no_media_rendering_or_audio_methods():
    from switchautopresence.runtime import Runtime
    for method in ("preview_frame", "select_direct", "enable_audio", "disable_audio", "set_audio_muted"):
        assert not hasattr(Runtime, method)
