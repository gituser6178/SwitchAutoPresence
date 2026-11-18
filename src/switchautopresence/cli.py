"""HOME recognition diagnostics and Discord activity. No media output."""

from __future__ import annotations

import argparse
import json
import os
import sys
from time import monotonic, sleep

from .capture import list_directshow_devices, probe_device
from .recognition import parse_roi


def _video_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--device", type=int, required=True, help="Video device index")
    parser.add_argument("--backend", choices=("dshow", "msmf"), default="dshow")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=60)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="switchautopresence",
                                     description="Nintendo Switch HOME recognition and Discord Rich Presence")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("devices", help="List video capture devices")
    probe = sub.add_parser("probe", help="Diagnose capture-card video access")
    probe.add_argument("--device", type=int, required=True)
    probe.add_argument("--backend", choices=("dshow", "msmf"), default="dshow")
    probe.add_argument("--seconds", type=float, default=8.0)
    probe.add_argument("--json", action="store_true")
    scan = sub.add_parser("scan-device", help="Run local HOME OCR diagnostic")
    _video_arguments(scan)
    scan.add_argument("--seconds", type=float, default=12.0)
    scan.add_argument("--roi", default="0.08,0.19,0.84,0.19")
    scan.add_argument("--titles", default=None)
    app = sub.add_parser("app", help="Start game-presence controller")
    app.add_argument("--device", type=int, default=None)
    app.add_argument("--backend", choices=("dshow", "msmf"), default="dshow")
    app.add_argument("--width", type=int, default=1920)
    app.add_argument("--height", type=int, default=1080)
    app.add_argument("--fps", type=int, default=60)
    app.add_argument("--app-id", default=os.environ.get("SWITCHAUTOPRESENCE_DISCORD_APP_ID"))
    app.add_argument("--roi", default="0.08,0.19,0.84,0.19")
    app.add_argument("--titles", default=None)
    app.add_argument("--artwork", default=None)
    # Backwards compatibility for the old user shortcut; no video is captured.
    app.add_argument("--discord-direct", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("SwitchAutoPresence desktop app requires Windows.", file=sys.stderr)
        return 2
    if args.command == "devices":
        try:
            devices = list_directshow_devices()
            for idx, name in enumerate(devices):
                print(f"[{idx}] {name}")
            return 0 if devices else 1
        except Exception as exc:
            print(f"Device discovery failed: {exc}", file=sys.stderr)
            return 2
    if args.command == "probe":
        if args.device < 0 or not 1 <= args.seconds <= 60:
            parser.error("--device >= 0 and --seconds 1..60 required")
        try:
            result = probe_device(args.device, backend=args.backend, duration_seconds=args.seconds)
            if args.json:
                print(json.dumps(result.to_dict(), indent=2))
            else:
                print(f"{result.status}: {result.message}")
            return 0 if result.status == "ok" else 1
        except Exception as exc:
            print(f"Probe failed: {exc}", file=sys.stderr)
            return 2
    if args.command == "scan-device":
        if args.device < 0 or not 1 <= args.seconds <= 60:
            parser.error("--device >= 0 and --seconds 1..60 required")
        from .catalog import GameCatalog
        from .device_stream import DeviceStream, VideoOptions
        from .recognition import HomeRecognizer
        source = None
        try:
            recognizer = HomeRecognizer(GameCatalog.from_file(args.titles), roi=parse_roi(args.roi))
            source = DeviceStream(VideoOptions(args.device, args.backend, args.width, args.height, args.fps))
            source.start()
            count, sequence, next_scan = 0, 0, 0.0
            deadline = monotonic() + args.seconds
            while monotonic() < deadline and not source.closed:
                packet = source.latest()
                now = monotonic()
                if packet is not None and packet.sequence != sequence and now >= next_scan:
                    sequence = packet.sequence
                    next_scan = now + 2
                    result = recognizer.analyze(packet.bgr)
                    print(f"{result.kind.value} title={result.title or '-'} "
                          f"confidence={result.confidence:.2f} method={result.method} "
                          f"OCR={result.raw_text[:140]}")
                    count += 1
                sleep(.1)
            if not count:
                print(source.error or "No frames (Discord may own video)")
            return 0 if count else 1
        except Exception as exc:
            print(f"HOME scan failed: {exc}", file=sys.stderr)
            return 2
        finally:
            if source is not None:
                source.stop()
    if args.command == "app":
        try:
            from .artwork import ArtworkCatalog
            from .catalog import GameCatalog
            from .gui import run_gui
            from .runtime import Runtime
            runtime = Runtime(
                app_id=args.app_id, device=args.device, backend=args.backend,
                width=args.width, height=args.height, fps=args.fps,
                roi=parse_roi(args.roi), catalog=GameCatalog.from_file(args.titles),
                artwork=ArtworkCatalog.from_file(args.artwork),
            )
            if args.discord_direct:
                runtime.clear()
            run_gui(runtime)
            return 0
        except Exception as exc:
            print(f"App failed: {exc}", file=sys.stderr)
            return 2
    parser.error("Unknown command")
    return 2
