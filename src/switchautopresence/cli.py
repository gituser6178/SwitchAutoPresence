"""Capture-card video preview, offline OCR diagnostics, and Discord activity."""

from __future__ import annotations

import argparse
import json
import os
import sys
from time import monotonic, sleep

from .capture import list_directshow_devices, probe_device
from .recognition import parse_roi


def _video_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--device", type=int, required=True, help="Zero-based video device index")
    parser.add_argument("--backend", choices=("dshow", "msmf"), default="dshow")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=60)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="switchautopresence", description="Nintendo Switch capture, recognition and Discord Rich Presence"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("devices", help="List DirectShow video devices without opening one")
    probe = sub.add_parser("probe", help="Phase 1: test selected capture card video")
    probe.add_argument("--device", type=int, required=True)
    probe.add_argument("--backend", choices=("dshow", "msmf"), default="dshow")
    probe.add_argument("--seconds", type=float, default=8.0)
    probe.add_argument("--json", action="store_true")

    sub.add_parser("audio-devices", help="List Windows audio capture endpoints")
    sub.add_parser("windows", help="[Optional] List app windows for viewer-based diagnostics")
    wp = sub.add_parser("probe-window", help="[Optional] Test an already-open external video viewer window")
    wp.add_argument("--window", default="VideoGameCapture")
    wp.add_argument("--hwnd", type=int, default=None)
    wp.add_argument("--seconds", type=float, default=8.0)

    sw = sub.add_parser("scan-window", help="[Optional] OCR a viewer HOME menu without opening hardware")
    sw.add_argument("--window", default="VideoGameCapture")
    sw.add_argument("--hwnd", type=int, default=None)
    sw.add_argument("--seconds", type=float, default=12.0)
    sw.add_argument("--roi", default="0.08,0.19,0.84,0.19")
    sw.add_argument("--titles", default=None)

    sd = sub.add_parser("scan-device", help="Read and OCR HOME from a single capture-card handle")
    _video_arguments(sd)
    sd.add_argument("--seconds", type=float, default=12.0)
    sd.add_argument("--roi", default="0.08,0.19,0.84,0.19")
    sd.add_argument("--titles", default=None)

    app = sub.add_parser("app", help="Start automatic/manual control panel and optional stream window")
    app.add_argument("--device", type=int, default=None, help="Video index (e.g. 1 for your AVerMedia)")
    app.add_argument("--backend", choices=("dshow", "msmf"), default="dshow")
    app.add_argument("--width", type=int, default=1920)
    app.add_argument("--height", type=int, default=1080)
    app.add_argument("--fps", type=int, default=60)
    app.add_argument("--app-id", default=os.environ.get("SWITCHAUTOPRESENCE_DISCORD_APP_ID"),
                     help="Discord Developer Application ID (public, not a user token)")
    app.add_argument("--roi", default="0.08,0.19,0.84,0.19")
    app.add_argument("--titles", default=None)
    app.add_argument("--artwork", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("Video/audio/GUI tools run on Windows 10/11 only.", file=sys.stderr)
        return 2

    if args.command == "devices":
        try:
            names = list_directshow_devices()
            for index, name in enumerate(names):
                print(f"[{index}] {name}")
            if not names:
                print("No DirectShow video devices found")
                return 1
            return 0
        except Exception as exc:
            print(f"Cannot list video devices: {exc}", file=sys.stderr)
            return 2

    if args.command == "audio-devices":
        try:
            from .audio_monitor import list_audio_inputs
            for index, name, channels in list_audio_inputs():
                print(f"[{index}] {name} ({channels} input channels)")
            print("Choose the AVerMedia HDMI audio input, NOT your microphone.")
            return 0
        except Exception as exc:
            print(f"Cannot list audio inputs: {exc}", file=sys.stderr)
            return 2

    if args.command == "probe":
        if args.device < 0 or not 1 <= args.seconds <= 60:
            parser.error("--device must be >= 0 and --seconds 1..60")
        try:
            result = probe_device(args.device, backend=args.backend, duration_seconds=args.seconds)
            if args.json:
                print(json.dumps(result.to_dict(), indent=2))
            else:
                print(f"Status: {result.status}")
                print(f"Device {result.device_index} | {result.backend} | {result.duration_seconds}s")
                print(f"Frames: {result.frames_received} | Read errors: {result.failed_reads}")
                print(f"Resolution: {result.width or '?'}x{result.height or '?'} | FPS: {result.average_fps}")
                print(result.message)
            return 0 if result.status == "ok" else 1
        except Exception as exc:
            print(f"Capture probe failed: {exc}", file=sys.stderr)
            return 2

    if args.command in ("probe-window", "scan-window", "windows"):
        try:
            from .window_capture import WindowCapture, list_windows
            if args.command == "windows":
                for hwnd, title in list_windows():
                    print(f"{hwnd}: {title}")
                return 0
            if not 1 <= args.seconds <= 60:
                parser.error("--seconds must be 1..60")
            source = WindowCapture(args.window, hwnd=args.hwnd, interval_seconds=2.0)
            if args.command == "scan-window":
                from .recognition import HomeRecognizer
                from .catalog import GameCatalog
                recognizer = HomeRecognizer(GameCatalog.from_file(args.titles), roi=parse_roi(args.roi))
            count = 0
            try:
                source.start()
                deadline = monotonic() + args.seconds
                while monotonic() < deadline and not source.closed:
                    item = source.poll(timeout=.25)
                    if item is None:
                        continue
                    count += 1
                    if args.command == "scan-window":
                        result = recognizer.analyze(item[1])
                        print(f"Frame {count}: {result.kind.value} | title={result.title or '-'} | OCR={result.raw_text[:140]}")
                    else:
                        print(f"Sample {count}: {item[1].shape[1]}x{item[1].shape[0]}")
                if not count:
                    print(f"No frames. {source.error or 'Check external window title and minimize state.'}")
                return 0 if count else 1
            finally:
                source.stop()
        except Exception as exc:
            print(f"External viewer test failed: {exc}", file=sys.stderr)
            return 2

    if args.command == "scan-device":
        if not 1 <= args.seconds <= 60:
            parser.error("--seconds must be 1..60")
        try:
            from .device_stream import DeviceStream, VideoOptions
            from .catalog import GameCatalog
            from .recognition import HomeRecognizer
            recognizer = HomeRecognizer(GameCatalog.from_file(args.titles), roi=parse_roi(args.roi))
            source = DeviceStream(VideoOptions(args.device, args.backend, args.width, args.height, args.fps))
            count, previous_sequence, next_read = 0, 0, 0.0
            source.start()
            try:
                deadline = monotonic() + args.seconds
                while monotonic() < deadline:
                    if source.closed:
                        break
                    packet = source.latest()
                    now = monotonic()
                    if packet and packet.sequence != previous_sequence and now >= next_read:
                        previous_sequence = packet.sequence
                        next_read = now + 2
                        result = recognizer.analyze(packet.bgr)
                        count += 1
                        print(f"Frame {count}: {result.kind.value} | selected={result.title or '-'} | "
                              f"OCR={result.raw_text[:140]}")
                    sleep(.1)
                if not count:
                    print(f"No video samples. {source.error or 'Check capture card input and competing apps.'}")
                return 0 if count else 1
            finally:
                source.stop()
        except Exception as exc:
            print(f"Direct HOME scan failed: {exc}", file=sys.stderr)
            return 2

    if args.command == "app":
        try:
            from .catalog import GameCatalog
            from .artwork import ArtworkCatalog
            from .runtime import Runtime
            from .gui import run_gui
            runtime = Runtime(
                app_id=args.app_id, device=args.device, backend=args.backend,
                width=args.width, height=args.height, fps=args.fps,
                roi=parse_roi(args.roi),
                catalog=GameCatalog.from_file(args.titles),
                artwork=ArtworkCatalog.from_file(args.artwork),
            )
            run_gui(runtime)
            return 0
        except Exception as exc:
            print(f"Could not start SwitchAutoPresence: {exc}", file=sys.stderr)
            return 2

    parser.error("Unknown command")
    return 2
