"""Small Windows control panel and a separate Discord-streamable preview window.

Both windows render a frame from the ONE DeviceStream reader. No Tk events
run off the main thread. The stream window contains only gameplay, never
private controls or Discord identifiers.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk
import cv2


def run_gui(runtime):
    root = tk.Tk()
    root.title("SwitchAutoPresence — v0.3 preview")
    root.geometry("850x760")
    root.minsize(740, 630)

    body = ttk.Frame(root, padding=14)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="SwitchAutoPresence", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(
        body, text="One capture card reader  •  automatic game detection  •  manual override"
    ).pack(anchor="w", pady=(0, 8))

    preview = tk.Label(body, bg="#090d16", fg="#d1d5db", text="Video preview: waiting for capture",
                       font=("Segoe UI", 12))
    preview.pack(fill="both", expand=True)
    preview.configure(height=14)

    controls = ttk.Frame(body)
    controls.pack(fill="x", pady=(12, 7))
    device_var = tk.StringVar(value=str(runtime.status()["device"] if runtime.status()["device"] is not None else "1"))
    ttk.Label(controls, text="Video device index").pack(side="left", padx=(0, 5))
    ttk.Entry(controls, textvariable=device_var, width=5).pack(side="left")
    ttk.Label(controls, text="Format").pack(side="left", padx=(12, 5))
    resolution = tk.StringVar(value="1920x1080 @ 60")
    ttk.Combobox(
        controls, textvariable=resolution, width=18, state="readonly",
        values=["1920x1080 @ 60", "1280x720 @ 60", "640x480 @ 30"],
    ).pack(side="left")
    backend_var = tk.StringVar(value="dshow")
    ttk.Combobox(controls, textvariable=backend_var, width=8, state="readonly",
                 values=["dshow", "msmf"]).pack(side="left", padx=(8, 0))

    stream_window = [None]
    stream_label = [None]
    last_preview_sequence = [-1]
    last_stream_sequence = [-1]

    def enable_auto():
        try:
            index = int(device_var.get().strip())
            if index < 0:
                raise ValueError("Device index must be zero or higher")
            dims, fps_value = resolution.get().split(" @ ")
            w, h = (int(v) for v in dims.split("x"))
            runtime.configure_video(index, backend=backend_var.get(), width=w, height=h, fps=int(fps_value))
            runtime.select_auto()
        except ValueError as exc:
            messagebox.showerror("Video settings", str(exc))

    manual_box = ttk.Frame(body)
    manual_box.pack(fill="x", pady=(4, 7))
    ttk.Label(manual_box, text="Manual game").grid(row=0, column=0, sticky="w")
    ttk.Label(manual_box, text="Art URL / asset key (optional)").grid(row=0, column=1, sticky="w", padx=(12, 0))
    game_var = tk.StringVar()
    game_combo = ttk.Combobox(manual_box, textvariable=game_var, values=sorted(runtime.catalog.titles))
    game_combo.grid(row=1, column=0, sticky="ew")
    image_var = tk.StringVar()
    ttk.Entry(manual_box, textvariable=image_var).grid(row=1, column=1, sticky="ew", padx=(12, 0))
    manual_box.columnconfigure(0, weight=1)
    manual_box.columnconfigure(1, weight=1)

    def art_for_game(_event=None):
        image_var.set(runtime.artwork.games.get(game_var.get().strip().casefold()) or "")

    game_combo.bind("<<ComboboxSelected>>", art_for_game)
    if runtime.session.snapshot().manual_title:
        game_var.set(runtime.session.snapshot().manual_title)
        art_for_game()

    def set_manual():
        try:
            runtime.select_manual(game_var.get(), image_var.get().strip())
        except ValueError as exc:
            messagebox.showerror("Manual game", str(exc))

    actions = ttk.Frame(body)
    actions.pack(fill="x", pady=(4, 8))
    ttk.Button(actions, text="Start automatic capture", command=enable_auto).pack(side="left", padx=(0, 8))
    ttk.Button(actions, text="Set manual game", command=set_manual).pack(side="left", padx=(0, 8))
    ttk.Button(actions, text="Clear activity", command=runtime.clear).pack(side="left")

    def close_stream_window():
        if stream_window[0] is not None:
            w = stream_window[0]
            stream_window[0] = None
            stream_label[0] = None
            try:
                w.destroy()
            except tk.TclError:
                pass

    def open_stream_window():
        if stream_window[0] is not None:
            stream_window[0].lift()
            return
        win = tk.Toplevel(root)
        win.title("SwitchAutoPresence Stream — share this window in Discord")
        win.geometry("1280x720")
        win.minsize(640, 360)
        label = tk.Label(win, bg="#05070b", fg="white", text="Waiting for Switch video...")
        label.pack(fill="both", expand=True)
        stream_window[0], stream_label[0] = win, label
        last_stream_sequence[0] = -1
        win.protocol("WM_DELETE_WINDOW", close_stream_window)

    ttk.Button(actions, text="Open stream window", command=open_stream_window).pack(side="right")

    audio_box = ttk.Frame(body)
    audio_box.pack(fill="x", pady=(4, 2))
    audio_var = tk.StringVar()
    ttk.Label(audio_box, text="AVerMedia HDMI audio input index (optional)").pack(side="left", padx=(0, 8))
    ttk.Entry(audio_box, textvariable=audio_var, width=6).pack(side="left")
    audio_button = ttk.Button(audio_box)
    audio_button.pack(side="left", padx=(8, 0))

    def toggle_audio():
        if runtime.status()["audio_enabled"]:
            runtime.disable_audio()
            return
        try:
            runtime.enable_audio(int(audio_var.get().strip()))
        except ValueError:
            messagebox.showerror("Audio input", "Enter the HDMI audio input index from the audio-devices command.")
        except RuntimeError as exc:
            messagebox.showerror("Audio monitor", str(exc))

    audio_button.configure(text="Start audio monitor", command=toggle_audio)
    ttk.Label(
        body,
        text="Only monitor AVerMedia HDMI audio. Avoid selecting a microphone (feedback risk). "
             "Discord application-audio sharing requires a separate Windows test.",
        wraplength=800, font=("Segoe UI", 9),
    ).pack(anchor="w", pady=(1, 8))

    ttk.Separator(body).pack(fill="x", pady=5)
    status_var = tk.StringVar()
    hint_var = tk.StringVar()
    ttk.Label(body, textvariable=status_var, font=("Segoe UI", 10, "bold")).pack(anchor="w")
    ttk.Label(body, textvariable=hint_var, wraplength=810).pack(anchor="w", pady=(3, 0))

    def show_frame(target, packet, w, h):
        try:
            image = packet.bgr
            target_w, target_h = max(2, w), max(2, h)
            scale = min(target_w / image.shape[1], target_h / image.shape[0])
            width, height = max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale))
            resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            photo = ImageTk.PhotoImage(Image.fromarray(rgb))
            target.configure(image=photo, text="")
            target.image = photo
        except (tk.TclError, ValueError):
            pass

    def draw():
        if not root.winfo_exists():
            return
        packet = runtime.preview_frame()
        if packet is not None:
            if packet.sequence != last_preview_sequence[0]:
                last_preview_sequence[0] = packet.sequence
                show_frame(preview, packet, preview.winfo_width(), preview.winfo_height())
            if stream_label[0] is not None and packet.sequence != last_stream_sequence[0]:
                last_stream_sequence[0] = packet.sequence
                show_frame(stream_label[0], packet,
                           stream_label[0].winfo_width(), stream_label[0].winfo_height())
        else:
            last_preview_sequence[0] = -1
            if preview.cget("image"):
                preview.configure(image="", text="Video preview unavailable — use Automatic and choose a device")
                preview.image = None
            if stream_label[0] is not None:
                last_stream_sequence[0] = -1
                if stream_label[0].cget("image"):
                    stream_label[0].configure(image="", text="No video — capture is not active")
                    stream_label[0].image = None
        root.after(65, draw)  # ~15 FPS display; OCR runs separately, ~every 2 sec.

    def update_status():
        if not root.winfo_exists():
            return
        s = runtime.status()
        video = s["capture_resolution"] or "no frames"
        status_var.set(
            f"{s['mode'].upper()} | {s['screen'].replace('_',' ').title()} | {s['details']} "
            f"| Video {video}"
        )
        audio_button.configure(text="Stop audio monitor" if s["audio_enabled"] else "Start audio monitor")
        if s["error"]:
            hint_var.set(s["error"])
        elif s["mode"] == "manual":
            hint_var.set("Manual mode releases video capture: stream directly from AVerMedia in Discord if desired.")
        elif s["mode"] == "auto":
            hint_var.set(
                "Share 'SwitchAutoPresence Stream' window in Discord instead of opening the "
                "AVerMedia directly. HOME-selected title is not considered playing until launch."
            )
        else:
            hint_var.set("Rich Presence cleared. Select Automatic or Manual to resume.")
        root.after(750, update_status)

    def close():
        close_stream_window()
        runtime.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    runtime.start()
    draw()
    update_status()
    root.mainloop()
