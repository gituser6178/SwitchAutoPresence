"""Safe local audio-device preferences and AVerMedia HDMI auto-selection.

PortAudio indices can change after Windows reboots, USB reconnects or driver
updates. Persist names and host APIs; never blindly trust an old numeric index
that now resolves to a microphone or an unrelated recording endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from .audio_monitor import AudioDevice
from .settings import settings_path


@dataclass(frozen=True)
class AudioSelection:
    input_device: int | None = None
    input_name: str = ""
    input_hostapi: str = ""
    output_device: int | None = None
    output_name: str = ""
    output_hostapi: str = ""


def audio_settings_path() -> Path:
    return settings_path().with_name("audio.json")


def load_audio_selection(path: Path | None = None) -> AudioSelection:
    path = path or audio_settings_path()
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            return AudioSelection()
        input_index = obj.get("input_device")
        output_index = obj.get("output_device")
        if not (isinstance(input_index, int) and input_index >= 0):
            input_index = None
        if not (isinstance(output_index, int) and output_index >= 0):
            output_index = None
        return AudioSelection(
            input_device=input_index,
            input_name=str(obj.get("input_name") or "")[:256],
            input_hostapi=str(obj.get("input_hostapi") or "")[:128],
            output_device=output_index,
            output_name=str(obj.get("output_name") or "")[:256],
            output_hostapi=str(obj.get("output_hostapi") or "")[:128],
        )
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return AudioSelection()


def save_audio_selection(selection: AudioSelection, path: Path | None = None) -> None:
    path = path or audio_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {
        "input_device": selection.input_device,
        "input_name": selection.input_name,
        "input_hostapi": selection.input_hostapi,
        "output_device": selection.output_device,
        "output_name": selection.output_name,
        "output_hostapi": selection.output_hostapi,
    }
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _is_avermedia_hdmi(device: AudioDevice) -> bool:
    name = device.name.casefold()
    return (
        device.input_channels > 0
        and "not to use" not in name
        and "hdmi" in name
        and any(token in name for token in ("avermedia", "live gamer", "gc553"))
    )


def _resolve_saved(
    devices: list[AudioDevice], saved_index: int | None,
    saved_name: str, saved_hostapi: str, *, is_input: bool,
) -> int | None:
    if not saved_name:
        return None
    valid = [
        d for d in devices
        if (d.input_channels > 0 if is_input else d.output_channels > 0)
        and d.name.casefold() == saved_name.casefold()
        and d.hostapi.casefold() == saved_hostapi.casefold()
    ]
    if not valid:
        return None
    if saved_index is not None:
        for device in valid:
            if device.index == saved_index:
                return device.index
    # USB device indices may have been reordered. Reidentify by name/API.
    return valid[0].index


def preferred_audio_input(
    devices: Iterable[AudioDevice], saved: AudioSelection | None = None,
) -> int | None:
    items = list(devices)
    if saved is not None:
        resolved = _resolve_saved(
            items, saved.input_device, saved.input_name,
            saved.input_hostapi, is_input=True,
        )
        if resolved is not None:
            # Never auto-select an endpoint explicitly labeled "Not To Use".
            item = next(d for d in items if d.index == resolved)
            # Automatic startup must never silently open a microphone.
            if _is_avermedia_hdmi(item):
                return resolved

    choices = [d for d in items if _is_avermedia_hdmi(d)]
    if not choices:
        return None

    def priority(device: AudioDevice):
        return (
            device.hostapi.casefold() == "windows wasapi",
            device.default_samplerate == 48000,
            device.input_channels >= 2,
            -device.index,
        )

    return max(choices, key=priority).index


def preferred_audio_output(
    devices: Iterable[AudioDevice], saved: AudioSelection | None = None,
) -> int | None:
    if saved is None or saved.output_device is None:
        return None  # Blank means default Windows playback output.
    return _resolve_saved(
        list(devices), saved.output_device, saved.output_name,
        saved.output_hostapi, is_input=False,
    )


def selection_from_devices(
    devices: Iterable[AudioDevice], input_device: int,
    output_device: int | None = None,
) -> AudioSelection:
    if input_device < 0 or (output_device is not None and output_device < 0):
        raise ValueError("Audio device indices must be non-negative")
    mapping = {d.index: d for d in devices}
    input_info = mapping.get(input_device)
    if input_info is None or input_info.input_channels < 1:
        raise ValueError("Selected audio input is not available")
    output_info = mapping.get(output_device) if output_device is not None else None
    if output_device is not None and (output_info is None or output_info.output_channels < 1):
        raise ValueError("Selected audio output is not available")
    return AudioSelection(
        input_device=input_device,
        input_name=input_info.name,
        input_hostapi=input_info.hostapi,
        output_device=output_device,
        output_name=output_info.name if output_info is not None else "",
        output_hostapi=output_info.hostapi if output_info is not None else "",
    )
