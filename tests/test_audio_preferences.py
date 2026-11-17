"""Regression tests for HDMI input auto-discovery and persisted audio choices."""

import json
from pathlib import Path

from switchautopresence.audio_monitor import AudioDevice
from switchautopresence.audio_preferences import (
    AudioSelection, load_audio_selection, preferred_audio_input,
    preferred_audio_output, save_audio_selection, selection_from_devices,
)


def device(index: int, name: str, hostapi: str, *, input_channels: int = 0,
           output_channels: int = 0, rate: int = 48000) -> AudioDevice:
    return AudioDevice(
        index=index, name=name, hostapi=hostapi,
        input_channels=input_channels, output_channels=output_channels,
        default_samplerate=rate,
    )


def setup_devices():
    return [
        device(1, "Analogue 1 + 2 (Focusrite USB)", "MME", input_channels=2, rate=44100),
        device(2, "Not To Use (Live Gamer ULTRA S GC553Pro)", "MME", input_channels=2, rate=44100),
        device(3, "HDMI (Live Gamer ULTRA S GC553Pro)", "MME", input_channels=2, rate=44100),
        device(5, "Speakers (TOPPING USB DAC)", "MME", output_channels=2, rate=44100),
        device(9, "HDMI (Live Gamer ULTRA S GC553Pro)", "Windows DirectSound", input_channels=2, rate=44100),
        device(13, "Not To Use (Live Gamer ULTRA S GC553Pro)", "Windows WASAPI", input_channels=2),
        device(14, "HDMI (Live Gamer ULTRA S GC553Pro)", "Windows WASAPI", input_channels=2),
        device(15, "Analogue 1 + 2 (Focusrite USB Audio)", "Windows WASAPI", input_channels=2),
        device(28, "HDMI (Live Gamer ULTRA S GC553Pro)", "Windows WDM-KS", input_channels=2),
    ]


def test_autodetect_prefers_hdmi_wasapi_and_never_not_to_use():
    assert preferred_audio_input(setup_devices()) == 14


def test_no_avermedia_never_selects_microphone_or_focusrite():
    devices = [
        device(4, "Microphone (webcam)", "Windows WASAPI", input_channels=1),
        device(5, "Analogue 1 + 2 (Focusrite)", "MME", input_channels=2),
        device(7, "HDMI (NVIDIA Graphics)", "Windows WASAPI", input_channels=2),
    ]
    assert preferred_audio_input(devices) is None


def test_saved_hdmi_choice_survives_windows_index_changes():
    existing = setup_devices()
    selection = selection_from_devices(existing, input_device=14)
    changed = [
        device(22, "HDMI (Live Gamer ULTRA S GC553Pro)", "Windows WASAPI", input_channels=2),
        device(14, "Microphone (webcam)", "Windows WASAPI", input_channels=1),
    ]
    assert preferred_audio_input(changed, selection) == 22


def test_saved_choice_avoids_unrelated_endpoint_on_reindex():
    saved = AudioSelection(14, "HDMI (Live Gamer ULTRA S GC553Pro)", "Windows WASAPI")
    devices = [device(14, "Microphone (webcam)", "Windows WASAPI", input_channels=1)]
    assert preferred_audio_input(devices, saved) is None


def test_saved_preference_round_trip_without_credentials(tmp_path: Path):
    path = tmp_path / "audio.json"
    prefs = selection_from_devices(setup_devices(), input_device=14)
    save_audio_selection(prefs, path)
    result = load_audio_selection(path)
    assert result == prefs
    assert result.output_device is None
    assert json.loads(path.read_text())["input_hostapi"] == "Windows WASAPI"


def test_saved_default_output_remains_blank():
    pref = AudioSelection(14, "HDMI", "Windows WASAPI")
    assert preferred_audio_output(setup_devices(), pref) is None


def test_explicit_output_rematches_by_name():
    devices = setup_devices()
    pref = selection_from_devices(devices, input_device=14, output_device=5)
    assert preferred_audio_output(devices, pref) == 5
    reindexed = [
        device(9, "HDMI (Live Gamer ULTRA S GC553Pro)", "Windows WASAPI", input_channels=2),
        device(6, "Speakers (TOPPING USB DAC)", "MME", output_channels=2, rate=44100),
        device(5, "Speakers (TV)", "MME", output_channels=2, rate=44100),
    ]
    assert preferred_audio_output(reindexed, pref) == 6


def test_corrupted_audio_preferences_fail_to_safe_defaults(tmp_path: Path):
    path = tmp_path / "audio.json"
    path.write_text("{bad json", encoding="utf-8")
    assert load_audio_selection(path) == AudioSelection()
    path.write_text('{"input_device": "14", "input_name": "microphone"}', encoding="utf-8")
    assert load_audio_selection(path).input_device is None


def test_ui_destroys_main_preview_while_stream_active():
    src = Path(__file__).resolve().parents[1] / "src" / "switchautopresence" / "gui.py"
    content = src.read_text(encoding="utf-8")
    compile(content, str(src), "exec")
    assert "preview.destroy()" in content
    assert "preview = None" in content
    assert "pause_inline_preview()" in content
    assert "resume_inline_preview()" in content
    assert "save_audio_selection(preference)" in content
