"""CLI: original capture probe, viewer diagnostics and desktop control panel."""

from __future__ import annotations

import argparse
import json
import os
import sys
from time import monotonic

from .capture import list_directshow_devices, probe_device
from .recognition import parse_roi


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="switchautopresence", description="Nintendo Switch capture diagnostics and Discord presence preview"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("devices", help="List DirectShow cameras without opening video streams")
    probe = sub.add_parser("probe", help="Phase 1: read selected capture device directly")
    probe.add_argument("--device", type=int, required=True)
    probe.add_argument("--backend", choices=("dshow", "msmf"), default="dshow")
    probe.add_argument("--seconds", type=float, default=8.0)
    probe.add_argument("--json", action="store_true")

    sub.add_parser("windows", help="List visible application titles and HWND values")
    wp = sub.add_parser("probe-window", help="Test viewer window without opening hardware")
    wp.add_argument("--window", default="VideoGameCapture", help="Part of viewer window title")
    wp.add_argument("--hwnd", type=int, default=None, help="Exact decimal window handle")
    wp.add_argument("--seconds", type=float, default=8.0)

    scan = sub.add_parser("scan-window", help="Offline OCR diagnostic for HOME titles")
    scan.add_argument("--window", default="VideoGameCapture")
    scan.add_argument("--hwnd", type=int, default=None)
    scan.add_argument("--seconds", type=float, default=12.0)
    scan.add_argument("--roi", default="0.08,0.19,0.84,0.19")
    scan.add_argument("--titles", default=None)

    app = sub.add_parser("app", help="Launch automatic/manual game selection window")
    app.add_argument("--window", default="VideoGameCapture", help="Part of viewer window title")
    app.add_argument("--hwnd", type=int, default=None, help="Exact decimal window handle")
    app.add_argument("--app-id", default=os.environ.get("SWITCHAUTOPRESENCE_DISCORD_APP_ID"),
                     help="Discord Developer Application ID")
    app.add_argument("--roi", default="0.08,0.19,0.84,0.19", help="Normalized HOME title region x,y,w,h")
    app.add_argument("--titles", default=None, help="Optional JSON list of additional game titles")
    app.add_argument("--artwork", default=None, help="Optional JSON game title -> image URL / asset key mappings")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("SwitchAutoPresence's capture and GUI run on Windows 10/11 only.", file=sys.stderr)
        return 2

    if args.command == "devices":
        try:
            names = list_directshow_devices()
        except Exception as exc:
            print(f"Could not enumerate DirectShow devices: {exc}", file=sys.stderr)
            return 2
        if not names:
            print("No DirectShow devices found. Check USB and Windows permissions.")
            return 1
        for i, name in enumerate(names):
            print(f"[{i}] {name}")
        print("Indices are a starting point; OpenCV ordering may differ by driver.")
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

    if args.command == "windows":
        try:
            from .window_capture import list_windows
            for hwnd, title in list_windows():
                print(f"{hwnd}: {title}")
        except Exception as exc:
            print(f"Could not enumerate windows: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "probe-window":
        if not 1 <= args.seconds <= 60:
            parser.error("--seconds must be between 1 and 60")
        from .window_capture import WindowCapture
        source = WindowCapture(args.window, hwnd=args.hwnd, interval_seconds=1.0)
        count, shape = 0, None
        try:
            source.start()
            deadline = monotonic() + args.seconds
            while monotonic() < deadline and not source.closed:
                item = source.poll(timeout=.25)
                if item is not None:
                    _, frame = item
                    count += 1
                    shape = frame.shape
            if count:
                print(f"Status: ok | Window: {args.window} | Samples: {count} | Frame: {shape[1]}x{shape[0]}")
                print("Viewer-window capture, not AVerMedia hardware capture. No images saved.")
                return 0
            print(f"Status: no_frames | {source.error or 'No video received; verify window title / minimized state.'}")
            return 1
        except Exception as exc:
            print(f"Window probe failed: {exc}", file=sys.stderr)
            return 2
        finally:
            source.stop()

    if args.command == "scan-window":
        if not 1 <= args.seconds <= 60:
            parser.error("--seconds must be between 1 and 60")
        try:
            from .catalog import GameCatalog
            from .recognition import HomeRecognizer
            from .window_capture import WindowCapture
            source = WindowCapture(args.window, hwnd=args.hwnd, interval_seconds=2.0)
            recognizer = HomeRecognizer(GameCatalog.from_file(args.titles), roi=parse_roi(args.roi))
            try:
                source.start()
                deadline = monotonic() + args.seconds
                count = 0
                while monotonic() < deadline and not source.closed:
                    item = source.poll(timeout=.25)
                    if item is None:
                        continue
                    count += 1
                    result = recognizer.analyze(item[1])
                    print(f"Frame {count}: screen={result.kind.value} | title={result.title or '-'} | confidence={result.confidence:.2f} | OCR={result.raw_text[:150]}")
                if count == 0:
                    print(f"No viewer frames received. {source.error or ''}")
                return 0 if count else 1
            finally:
                source.stop()
        except Exception as exc:
            print(f"Window OCR scan failed: {exc}", file=sys.stderr)
            return 2

    if args.command == "app":
        try:
            from .artwork import ArtworkCatalog
            from .catalog import GameCatalog
            from .runtime import Runtime
            from .gui import run_gui
            runtime = Runtime(
                app_id=args.app_id,
                window=args.window,
                hwnd=args.hwnd,
                roi=parse_roi(args.roi),
                catalog=GameCatalog.from_file(args.titles),
                artwork=ArtworkCatalog.from_file(args.artwork),
            )
            run_gui(runtime)
            return 0
        except Exception as exc:
            print(f"Application could not start: {exc}", file=sys.stderr)
            return 2

    parser.error("Unknown command")
    return 2
