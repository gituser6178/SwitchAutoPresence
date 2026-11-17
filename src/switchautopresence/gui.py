"""Minimal Windows UI with automatic mode and persistent manual override."""

from __future__ import annotations


def run_gui(runtime):
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("SwitchAutoPresence — Preview")
    root.geometry("560x370")
    root.minsize(480, 350)
    root.option_add("*Font", "Segoe UI 10")
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="SwitchAutoPresence", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Automatic recognition or a persistent manual game selection").pack(anchor="w", pady=(0, 18))

    ttk.Label(frame, text="Game (type your own or select a known title):").pack(anchor="w")
    title_var = tk.StringVar()
    games = ttk.Combobox(frame, textvariable=title_var, values=sorted(runtime.catalog.titles), width=65)
    games.pack(fill="x", pady=(4, 8))
    ttk.Label(frame, text="Game artwork (optional HTTPS image URL or Discord asset key):").pack(anchor="w")
    image_var = tk.StringVar()
    ttk.Entry(frame, textvariable=image_var).pack(fill="x", pady=(4, 12))

    def load_game_art(_event=None):
        image_var.set(runtime.artwork.games.get(title_var.get().strip().casefold()) or "")

    games.bind("<<ComboboxSelected>>", load_game_art)
    snap = runtime.session.snapshot()
    if snap.manual_title:
        title_var.set(snap.manual_title)
        load_game_art()

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")

    def apply_manual():
        try:
            runtime.select_manual(title_var.get(), image_var.get().strip())
        except ValueError as exc:
            messagebox.showerror("Invalid game", str(exc))

    ttk.Button(buttons, text="Set manual game", command=apply_manual).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="Automatic", command=runtime.select_auto).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="Clear activity", command=runtime.clear).pack(side="left")

    ttk.Separator(frame).pack(fill="x", pady=18)
    status_var = tk.StringVar()
    hint_var = tk.StringVar()
    ttk.Label(frame, textvariable=status_var, font=("Segoe UI", 11, "bold")).pack(anchor="w")
    ttk.Label(frame, textvariable=hint_var, wraplength=490).pack(anchor="w", pady=(6, 0))

    def refresh():
        status = runtime.status()
        status_var.set(f"{status['mode'].upper()} · {status['screen'].replace('_', ' ').title()} · {status['details']}")
        if status["error"]:
            hint_var.set(status["error"])
        elif status["mode"] == "manual":
            hint_var.set("Manual game stays selected until you choose Automatic or Clear.")
        elif status["mode"] == "auto":
            hint_var.set("Watching the VideoGameCapture window. A highlighted HOME tile is not assumed to be running.")
        else:
            hint_var.set("Activity cleared. Choose a manual game or resume Automatic mode.")
        root.after(700, refresh)

    def close():
        runtime.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    runtime.start()
    refresh()
    root.mainloop()
