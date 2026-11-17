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

If pip has installed both `opencv-python` and `opencv-python-headless`, uninstall both from the project's .venv and reinstall **only** the pinned headless build:

~~~powershell
.\.venv\Scripts\python.exe -m pip uninstall -y opencv-python opencv-python-headless
.\.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps "opencv-python-headless>=4.8,<5"
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
5. Click **Open stream window**. This second window is a **rendering view**, not a second camera handle.
6. In Discord desktop, use Share Screen -> **Applications** -> **SwitchAutoPresence Stream**. Do not choose the AVerMedia capture device in Discord.
7. Confirm the stream stays alive when the app is behind another window. Note that minimized-window sharing and rendering are not guaranteed by every Discord client.

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
3. With Automatic enabled, type its input index in the GUI and click **Start audio monitor**.
4. If the audio is heard through your Windows output device, enable Discord's application **Share audio** option.
5. Ask a Discord listener whether sound and video are in sync. Disable monitoring if feedback or double audio occurs.

If the audio endpoint isn't exposed or Discord doesn't receive the app's sound, **report that limitation**. We should fix audio routing before promoting the app as a complete streaming replacement.

## Report

Provide text for: capture index, successful stream-window preview, actual resolution and FPS, Discord window-share behavior, HOME OCR text, manual-mode behavior, and whether audio worked. Avoid uploading sensitive personal footage.
