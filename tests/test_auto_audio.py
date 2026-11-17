"""Automatic HDMI audio device choice, persistence, mute and UI policy tests."""

from pathlib import Path

import numpy as np

from switchautopresence.audio_monitor import AudioDevice, AudioMonitor
from switchautopresence.audio_preferences import (
    AudioSelection,
    load_audio_selection,
    preferred_audio_input,
    preferred_audio_output,
    save_audio_selection,
    selection_from_devices,
)


def fake_devices():
    return [
        AudioDevice(1, "Analogue 1 + 2 (Focusrite USB Audio)", "Windows WASAPI", 2, 0, 48000),
        AudioDevice(9, "HDMI (Live Gamer ULTRA S GC553Pro)", "Windows DirectSound", 2, 0, 44100),
        AudioDevice(13, "Not To Use (Live Gamer ULTRA S GC553Pro)", "Windows WASAPI", 2, 0, 48000),
        AudioDevice(14, "HDMI (Live Gamer ULTRA S GC553Pro)", "Windows WASAPI", 2, 0, 48000),
        AudioDevice(5, "Speakers (TOPPING USB DAC)", "MME", 0, 2, 48000, default_output=True),
    ]


def test_best_default_is_avermedia_hdmi_wasapi_not_microphone():
    assert preferred_audio_input(fake_devices()) == 14


def test_saved_hdmi_input_is_restored_by_name_and_api(tmp_path):
    original = selection_from_devices(fake_devices(), 14)
    path = tmp_path / "audio.json"
    save_audio_selection(original, path)
    loaded = load_audio_selection(path)
    assert loaded.input_name == original.input_name
    assert preferred_audio_input(fake_devices(), loaded) == 14

    reordered = [
        AudioDevice(37, original.input_name, "Windows WASAPI", 2, 0, 48000),
        fake_devices()[0],
    ]
    assert preferred_audio_input(reordered, loaded) == 37


def test_saved_microphone_cannot_be_auto_opened():
    saved = AudioSelection(
        input_device=1,
        input_name="Analogue 1 + 2 (Focusrite USB Audio)",
        input_hostapi="Windows WASAPI",
    )
    assert preferred_audio_input(fake_devices(), saved) == 14


def test_saved_output_defaults_to_windows_until_manually_overridden(tmp_path):
    original = selection_from_devices(fake_devices(), 14, None)
    assert preferred_audio_output(fake_devices(), original) is None
    selected = selection_from_devices(fake_devices(), 14, 5)
    path = tmp_path / "audio.json"
    save_audio_selection(selected, path)
    assert preferred_audio_output(fake_devices(), load_audio_selection(path)) == 5


def test_invalid_or_missing_saved_settings_fall_back_safely(tmp_path):
    p = tmp_path / "audio.json"
    assert preferred_audio_input(fake_devices(), load_audio_selection(p)) == 14
    p.write_text("not-json", encoding="utf-8")
    assert load_audio_selection(p) == AudioSelection()


class DummyStream:
    def __init__(self, **kwargs):
        self.cb = kwargs["callback"]
    def start(self): pass
    def stop(self): pass
    def close(self): pass


class DummyDuplexBackend:
    class default:
        device = (0, 7)
    def __init__(self):
        self.stream = None
    def query_devices(self, index, kind):
        if kind == "input":
            return {"max_input_channels": 2, "default_samplerate": 48000.0, "hostapi": 1}
        return {"max_output_channels": 2, "default_samplerate": 48000.0, "hostapi": 1}
    def Stream(self, **kwargs):
        self.stream = DummyStream(**kwargs)
        return self.stream


def test_mute_stops_playback_not_capture_or_meter():
    backend = DummyDuplexBackend()
    monitor = AudioMonitor(14, backend=backend)
    monitor.start()
    data = np.full((128, 2), .2, dtype=np.float32)
    audible = np.empty_like(data)
    backend.stream.cb(data, audible, len(data), None, None)
    assert np.allclose(audible, .2)

    monitor.set_muted(True)
    silent = np.ones_like(data)
    backend.stream.cb(data, silent, len(data), None, None)
    assert monitor.running
    assert monitor.muted
    assert np.all(silent == 0)
    assert monitor.levels()["has_signal"]
    assert monitor.levels()["muted"] is True

    monitor.set_muted(False)
    unmuted = np.zeros_like(data)
    backend.stream.cb(data, unmuted, len(data), None, None)
    assert np.allclose(unmuted, data)
    monitor.stop()


def test_gui_auto_audio_policy_and_duplicate_preview_syntax():
    source = (Path(__file__).resolve().parents[1] / "src" / "switchautopresence" / "gui.py").read_text(encoding="utf-8")
    compile(source, "gui.py", "exec")
    assert 'root.after(400, route_audio)' in source
    assert 'text="Mute"' in source
    assert 'text="Unmute"' in source
    assert 'text="Rescan"' in source
    assert 'preview.destroy()' in source
    assert 'Start audio monitor' not in source
