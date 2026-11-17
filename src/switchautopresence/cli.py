"""Phase 1 command line interface. No recording and no Discord login."""

from __future__ import annotations

import argparse
import json
import sys

from .capture import list_directshow_devices, probe_device


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="switchautopresence",
        description="Read-only Nintendo Switch capture-device diagnostics (early development)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("devices", help="List DirectShow video device names without opening a stream")
    probe = sub.add_parser("probe", help="Read a selected device briefly without saving images")
    probe.add_argument("--device", type=int, required=True, help="Zero-based capture device index")
    probe.add_argument("--backend", choices=("dshow", "msmf"), default="dshow")
    probe.add_argument("--seconds", type=float, default=8.0, help="Probe duration (1-60 seconds)")
    probe.add_argument("--json", action="store_true", help="Machine-readable results")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("This Phase 1 capture tool runs on Windows 10/11 only.", file=sys.stderr)
        return 2

    if args.command == "devices":
        try:
            names = list_directshow_devices()
        except Exception as exc:
            print(f"Could not enumerate DirectShow devices: {exc}", file=sys.stderr)
            return 2
        if not names:
            print("No DirectShow video devices found. Check USB connection and Windows permissions.")
            return 1
        for i, name in enumerate(names):
            print(f"[{i}] {name}")
        print("Indices are a starting point; DirectShow/OpenCV ordering may differ by driver.")
        return 0

    if args.command == "probe":
        if args.device < 0 or not 1 <= args.seconds <= 60:
            parser.error("--device must be >= 0 and --seconds must be between 1 and 60")
        try:
            result = probe_device(args.device, backend=args.backend, duration_seconds=args.seconds)
        except Exception as exc:
            print(f"Capture probe failed: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(f"Status: {result.status}")
            print(f"Device {result.device_index} | {result.backend} | {result.duration_seconds}s")
            print(f"Frames: {result.frames_received} | Read errors: {result.failed_reads}")
            print(f"Resolution: {result.width or '?'}x{result.height or '?'} | Observed FPS: {result.average_fps}")
            print(result.message)
        return 0 if result.status == "ok" else 1

    parser.error("Unknown command")
    return 2
