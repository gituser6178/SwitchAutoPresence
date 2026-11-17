# v0.3 — Single-owner capture + preview validation (Windows)

The project no longer assumes VideoGameCapture is running. Automatic mode opens the GC553Pro **once**. The app's stream window and game recognition use the same frames.

## Update from v0.2

~~~powershell
cd C:\WINDOWS\system32\SwitchAutoPresence
git fetch origin
git switch feat/phase2-auto-manual-presence
git pull --ff-only origin feat/phase2-auto-manual-presence
.\.venv\Scripts\python.exe -m pip install -e ".[all]"
.\.venv\Scripts\python.exe -m switchautopresence --help
~~~

If pip has installed both `opencv-python` and `opencv-python-headless`, uninstall both from the project's .venv and reinstall **only** the pinned OpenCV 4.x build:

~~~powershell
.\.venv\Scripts\python.exe -m pip uninstall -y opencv-python opencv-python-headless
.\.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps "opencv-python>=4.8,<5"
~~~

## Video test — single owner

1. Power on the Switch and connect your AVerMedia GC553Pro. Stop any Discord stream that **directly** captures the AVerMedia first.
2. Find the video index (previous test PC: index 1):

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence devices
~~~

3. Launch:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence app --device 1
~~~

4. Verify preview shows live Switch video; note the resolution in the status area. If blank/driver negotiation fails, select 1280x720 @ 60 in the UI and press Start automatic capture.
5. Click **Start stream source**. The control panel hides its own video preview and the stream source starts **behind other windows** (no duplicate image work).
6. In Discord desktop, use Share Screen -> **Applications** -> **SwitchAutoPresence Stream**. Do not choose the AVerMedia capture device. If the application window isn't listed, click **Show stream for Discord picker** and retry.
7. After Discord starts sharing, cover the source with another application. The stream should keep advancing as long as the source window remains mapped and **not minimized**. Ask a viewer to verify video and game sound. Do **not** minimize, withdraw or hide the source; that is not a supported Discord window-capture workflow.
8. Close the stream source window to restore the control-panel preview. Check that the video capture and HDMI audio continue as expected.

## Game identification test

1. Highlight **The Legend of Zelda: Ocarina of Time** on the Switch HOME menu, without launching it.
2. App should show `Browsing HOME`, not `Playing Ocarina of Time`.
3. Launch the title and observe whether it changes to `Playing Ocarina of Time` after several OCR sampling intervals.
4. Return HOME: the presence should go back to `Browsing HOME`.
5. If the app fails to recognize HOME, close it and test the standalone diagnostic:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence scan-device --device 1 --seconds 12
~~~

Record the OCR text and state. On-screen titles may be misread; the classifier may need tuning with anonymized, user-provided test frames.

## Manual and fallback

1. Select **Set manual game** with a game title (e.g. Pokémon Violet).
2. The app should release the camera within a moment; this will stop its own stream preview. Now Discord can directly capture AVerMedia as before.
3. Switch back to **Start automatic capture**: stop Discord's direct capture FIRST to free the card again.
4. **Clear activity** should remove Rich Presence and release the card.
5. Manual mode should work even when the console or USB cable is disconnected.

## Optional HDMI audio (unverified)

**Video capture in OpenCV does not include audio.** The standalone stream window will not automatically carry game sound.

1. List input endpoints:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence audio-devices
~~~

2. Choose the **AVerMedia HDMI audio input**, never your normal microphone.
3. With Automatic enabled, HDMI audio connects automatically using the saved or preferred AVerMedia HDMI input. Use the **Recording input** dropdown or **Rescan** only when needed; use **Mute / Unmute** for playback.
4. If the audio is heard through your Windows output device, enable Discord's application **Share audio** option.
5. Ask a Discord listener whether sound and video are in sync. Disable monitoring if feedback or double audio occurs.

If the audio endpoint isn't exposed or Discord doesn't receive the app's sound, **report that limitation**. We should fix audio routing before promoting the app as a complete streaming replacement.

## Report

Provide text for: capture index, successful stream-window preview, actual resolution and FPS, Discord window-share behavior, HOME OCR text, manual-mode behavior, and whether audio worked. Avoid uploading sensitive personal footage.

## 60 FPS and HOME title troubleshooting

The GUI requests a 16 ms redraw target and reports actual **capture FPS** and **stream-window FPS**. If the stream preview is still below 60 FPS, the Tkinter renderer needs further optimization. This is not the same as the capture-card FPS.

When the app shows HOME → Launching → Unknown, check the `HOME title candidate` and `OCR` status in the controller. If the candidate never becomes a real title, close the app and run `scan-device --device 1 --seconds 12` with Zelda highlighted. Share the diagnostic *text* to calibrate it, not gameplay frames. A few intermittent OCR misses no longer immediately erase a recognized candidate.

Audio sharing is not proven until a remote Discord listener confirms sound (with the AVerMedia HDMI audio input selected and the audio monitor enabled). Turn off the monitor if you hear feedback or duplicate sound.

## RapidOCR finds no text

Some Nintendo Switch 2 HOME screens contain thin cyan text that the default OCR detector misses. The recognizer now attempts a cyan-line crop using recognition-only OCR before regular text detection.

The scan-device diagnostic prints a method and OCR text for each frame. cyan_title_unreadable means the title's color was found but its text could not be read. neutral_without_title means a gray-looking video frame lacked HOME evidence and will not change the game state.

Please provide diagnostic text rather than uploading sensitive footage.

## Background capture vs completely invisible output

Discord supports Windows Graphics Capture for per-application sharing. DWM-backed window capture can keep receiving frames when a window is **occluded by other windows**, provided the application continues to draw. We explicitly continue updating the source stream's Tk PhotoImage while the mapped window is covered and **stop all rendering** in the control-panel preview to save CPU.

A genuine hidden/minimized window is **not** the same as a covered window. Discord may not enumerate it or may freeze the stream. The source must remain open and not minimized, even if you put any other window in front of it.

Use **Show stream for Discord picker** if Discord can't locate the source while it's behind other windows. Don't assume that sending it to the taskbar or making it fully transparent will keep capture alive. An entirely invisible source would need a virtual capture backend and separate validation of how Discord receives its video/audio.
