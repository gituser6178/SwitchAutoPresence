"""Tiny game-presence controller without video preview or audio processing."""

from __future__ import annotations

from queue import Empty, SimpleQueue
from time import time
import tkinter as tk
from tkinter import messagebox, ttk

from .tray import TrayController


def run_gui(runtime) -> None:
    root = tk.Tk()
    root.title("SwitchAutoPresence — v0.4")
    root.geometry("570x460")
    root.minsize(505, 410)
    events = SimpleQueue()
    tray = TrayController(events)
    body = ttk.Frame(root, padding=16)
    body.pack(fill="both", expand=True)

    def show_window() -> None:
        root.deiconify()
        root.lift()
        root.focus_force()

    def minimize_to_tray() -> None:
        try:
            tray.start()
            root.withdraw()
        except Exception as exc:
            messagebox.showwarning("Tray unavailable", str(exc))
            root.iconify()

    def exit_app() -> None:
        root.destroy()

    heading = ttk.Frame(body)
    heading.pack(fill="x")
    ttk.Label(heading, text="SwitchAutoPresence", font=("Segoe UI", 17, "bold")).pack(side="left")
    ttk.Button(heading, text="Minimize to tray", command=minimize_to_tray).pack(side="right")
    ttk.Label(body, text="Discord handles capture-card video and audio; this app only manages game activity.",
              wraplength=535).pack(anchor="w", pady=(9, 14))

    status_frame = ttk.LabelFrame(body, text="Discord activity", padding=12)
    status_frame.pack(fill="x")
    activity_var = tk.StringVar(value="Waiting for game")
    timer_var = tk.StringVar(value="Elapsed: —")
    note_var = tk.StringVar(value="Ready")
    ttk.Label(status_frame, textvariable=activity_var, font=("Segoe UI", 11, "bold"),
              wraplength=485).pack(anchor="w")
    ttk.Label(status_frame, textvariable=timer_var).pack(anchor="w", pady=3)
    ttk.Label(status_frame, textvariable=note_var, wraplength=485).pack(anchor="w")

    manual = ttk.LabelFrame(body, text="Manual game — recommended while Discord streams", padding=12)
    manual.pack(fill="x", pady=(10, 0))
    game_var = tk.StringVar()
    game_entry = ttk.Combobox(manual, textvariable=game_var, values=list(runtime.catalog.titles))
    game_entry.pack(fill="x")
    ttk.Label(manual, text="Optional game artwork: HTTPS URL or Discord asset key").pack(
        anchor="w", pady=(7, 0))
    art_var = tk.StringVar()
    ttk.Entry(manual, textvariable=art_var).pack(fill="x", pady=(2, 5))

    def on_game_selected(_event=None) -> None:
        art_var.set(runtime.artwork.games.get(game_var.get().strip().casefold(), ""))

    game_entry.bind("<<ComboboxSelected>>", on_game_selected)

    def use_manual() -> None:
        try:
            runtime.select_manual(game_var.get(), art_var.get().strip() or None)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Game or artwork error", str(exc))

    ttk.Button(manual, text="Set Discord game", command=use_manual).pack(anchor="e")

    auto = ttk.LabelFrame(body, text="Optional HOME detection", padding=12)
    auto.pack(fill="x", pady=(10, 0))
    options = ttk.Frame(auto)
    options.pack(fill="x")
    selected_device = runtime.status()["device"]
    device_var = tk.StringVar(value=str(selected_device if selected_device is not None else 1))
    backend_var = tk.StringVar(value="dshow")
    ttk.Label(options, text="Video device").pack(side="left")
    ttk.Entry(options, textvariable=device_var, width=5).pack(side="left", padx=(5, 12))
    ttk.Combobox(options, textvariable=backend_var, values=["dshow", "msmf"],
                 state="readonly", width=7).pack(side="left")
    ttk.Label(options, text="  Requires shared capture access").pack(side="left")

    def use_auto() -> None:
        try:
            runtime.configure_video(int(device_var.get()), backend=backend_var.get())
            runtime.select_auto()
        except ValueError as exc:
            messagebox.showerror("Invalid video device", str(exc))

    actions = ttk.Frame(auto)
    actions.pack(fill="x", pady=(8, 0))
    ttk.Button(actions, text="Try automatic detection", command=use_auto).pack(side="left")
    ttk.Button(actions, text="Clear Discord status", command=runtime.clear).pack(side="right")

    def refresh() -> None:
        try:
            status = runtime.status()
            activity_var.set(status["details"])
            started = status["started_at"]
            if started is None:
                timer_var.set("Elapsed: —")
            else:
                seconds = max(0, int(time() - started))
                hours, remaining = divmod(seconds, 3600)
                minutes, seconds = divmod(remaining, 60)
                timer_var.set(f"Elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}")
            note = status.get("error") or ""
            if status["mode"] == "auto":
                if status["capture_blocked"]:
                    note = "Capture unavailable: use Manual while Discord streams. " + note
                elif status["capture_open"]:
                    note = "HOME recognition active. " + note
                else:
                    note = "Waiting for capture device. " + note
            elif status["mode"] == "manual":
                note = "Manual presence; capture card released. " + note
            else:
                note = "Presence cleared; no video capture. " + note
            note_var.set(note.strip())
            root.after(900, refresh)
        except tk.TclError:
            pass

    def poll_tray() -> None:
        try:
            while True:
                action = events.get_nowait()
                if action == "show":
                    show_window()
                elif action == "exit":
                    exit_app()
                    return
        except Empty:
            pass
        try:
            root.after(150, poll_tray)
        except tk.TclError:
            pass

    root.protocol("WM_DELETE_WINDOW", minimize_to_tray)
    runtime.start()
    refresh()
    poll_tray()
    try:
        root.mainloop()
    finally:
        tray.stop()
        runtime.stop()
