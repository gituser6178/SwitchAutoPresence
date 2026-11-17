# SwitchAutoPresence 🎮

An **unofficial Windows utility** for sharing Nintendo Switch and Switch 2 games on Discord with **automatic game recognition** or **persistent manual game selection**.

> **v0.3 pre-alpha / Windows hardware validation pending.** The application owns a single capture-card video stream, displays an optional streamable preview window, inspects the same frames for HOME-menu titles, and updates Discord Rich Presence. It is not a production-quality streamer, and audio sharing is **experimental**.

## How it works

~~~text
Nintendo Switch 2
        |
        v
AVerMedia GC553Pro (one video reader / one handle)
        |
        v
SwitchAutoPresence
        |--> Live preview window --> Discord "Share an application"
        |--> Low-frequency HOME OCR --> confirmed game --> Discord Rich Presence
        |
        +--> Manual mode (releases card; direct Discord capture may resume)
~~~

**You do NOT need VideoGameCapture, OBS, or another viewer.** Only one application should open the AVerMedia video feed at a time.

### Automatic mode

1. Stop Discord **directly capturing the AVerMedia** (it would compete for the card).
2. Start SwitchAutoPresence with the correct video device index, e.g. **1** on the original test PC.
3. Click **Open stream window**. This is a standalone video-only window.
4. In Discord's **Share Your Screen → Applications**, share **SwitchAutoPresence Stream**, not the AVerMedia video device.
5. The same in-memory video frames are periodically analyzed for the Switch HOME menu; game selection on HOME is only a **candidate**, not confirmed gameplay.
6. HOME shows **Nintendo Switch — Browsing HOME** with generic artwork; likely gameplay shows the previously selected title after several consistent non-HOME frames.

The initial HOME detector uses image-layout heuristics and offline RapidOCR. **It's experimental.** Gameplay launch can be misclassified if the HOME screen is obscured or you open another app. A fresh launch transition is required; starting in the middle of a game displays a generic Switch activity until a title can be confirmed.

### Manual mode

Choose/type a game and click **Set manual game**. Your selection has priority and stays locked until you choose **Start automatic capture** or **Clear activity**.

Manual mode **releases the capture card**, allowing you to stream directly from your AVerMedia in Discord. It works even without an attached console. You can enter a permitted HTTPS game artwork URL or Discord image asset key for each game. The selection and artwork mapping are stored locally in Windows AppData.

### Audio: experimental, OFF by default

OpenCV captures **video only**. For sound, v0.3 includes optional in-process monitoring of the **AVerMedia HDMI audio input** to your default Windows audio output. If Discord captures the shared application's output audio, your audience may hear it as well. **This is NOT yet verified on the GC553Pro with Discord.**

- Run `audio-devices` to find the exact AVerMedia HDMI audio input index.
- Enter that index in the UI and choose **Start audio monitor** (only in Automatic mode).
- Do **not** select your microphone: doing so can create feedback.
- Check Discord's **Share audio** option when sharing the stream window. Listen through headphones if needed.
- Stop audio monitoring immediately if you hear feedback, echoes, or doubled game audio.

Do not consider the streaming pipeline fully validated until video **and** audio are tested.

## Installation (Windows 10/11)

You need Python 3.10+ and an existing SwitchAutoPresence clone. If you already cloned the earlier build:

~~~powershell
git fetch origin
git switch feat/phase2-auto-manual-presence
git pull --ff-only origin feat/phase2-auto-manual-presence
.\.venv\Scripts\python.exe -m pip install --upgrade -e ".[all]"
.\.venv\Scripts\python.exe -m switchautopresence --help
~~~

**OpenCV installation note:** The OpenCV project says `opencv-python` and `opencv-python-headless` should NOT coexist. Some dependency combinations may install both. If `cv2` import breaks or both variants appear, after installing requirements run:

~~~powershell
.\.venv\Scripts\python.exe -m pip uninstall -y opencv-python opencv-python-headless
.\.venv\Scripts\python.exe -m pip install --no-deps --force-reinstall "opencv-python-headless>=4.8,<5"
.\.venv\Scripts\python.exe -c "import cv2; print(cv2.__version__)"
~~~

This repair operates **only inside the project virtual environment**. The project uses Pillow/Tkinter for previews, so headless OpenCV is sufficient.

## First video test

Find the AVerMedia index:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence devices
~~~

Close Discord's direct capture of that device, then start the application:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence app --device 1 --width 1920 --height 1080 --fps 60
~~~

The `--device 1` value was correct in one initial GC553Pro test; yours may differ. If no video appears, try **1280×720 @ 60** from the UI or the alternate `--backend msmf` option. Actual negotiated frame size and FPS are displayed by the UI. The app will retry the driver's default format once if the requested format produces no frames.

Use **Open stream window** in the UI and share that window on Discord. **Do not close the app while it is being streamed**.

To test HOME recognition without a Discord Application ID, close the app and run:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence scan-device --device 1 --seconds 12
~~~

Navigate to Switch HOME and highlight a recognizable game while this command runs. Report the output; no screenshots or recorded video are saved.

## Discord Rich Presence

1. In the [Discord Developer Portal](https://discord.com/developers/applications), create a Rich Presence application, ideally named **Nintendo Switch**.
2. Copy its **Application ID** (public, not an account token).
3. Run the app with `--app-id YOUR_APPLICATION_ID` and keep Discord desktop open.

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence app --device 1 --app-id YOUR_APPLICATION_ID
~~~

Discord should display **Nintendo Switch** with game details and session time. For game art, add a permitted HTTPS image URL or upload assets in your Developer Application; otherwise Discord may show the app's default icon. No game covers are copied into this repository.

Without `--app-id` the app runs in **dry-run mode**: gameplay preview and manual/automatic controls still work, but Discord Rich Presence does not change.

## Commands

| Command | Use |
| --- | --- |
| `devices` | List DirectShow video devices |
| `app --device 1` | Launch controller and single-owner preview |
| `scan-device --device 1` | Offline OCR while owning the capture card |
| `audio-devices` | Find the HDMI audio capture endpoint |
| `probe --device 1` | Original Phase 1 diagnostic (only when device is free) |
| `windows`, `probe-window`, `scan-window` | Optional legacy external-viewer tests; not required |

See [Phase 3 testing guide](docs/PHASE3_SINGLE_CAPTURE_TESTING.md) for a complete checklist.

## Known limitations

- The Tkinter video-only window renders at up to **30 FPS** (rendering target, not a guaranteed frame rate); this is a functional preview, **not yet a high-performance 60 FPS streaming renderer**. HDMI passthrough on the AVerMedia is not affected.
- Full-speed capture decode and per-frame Tkinter image drawing may use CPU. OCR is sampled infrequently rather than processed on every frame.
- The GC553Pro hardware probe succeeded alone (426 frames / 8 sec, no read errors), and failed while another app used its video feed. The integrated preview has **not yet been hardware-tested**.
- The capture device must be free when Automatic mode starts. Manual mode relinquishes it.
- Voice/audio monitoring and Discord application audio capture must be tested; the implementation is not a guarantee of working sound.
- The HOME title recognizer is heuristic. Unknown games use generic artwork. It does not recognize arbitrary gameplay scenes.
- This is a Windows developer prototype, not a packaged installer or system-tray release.

## Privacy and license

The app runs locally by default. No video or audio is saved or uploaded by this code. The only intended network-facing presence action is Discord's IPC client, which publishes game title/details/artwork you configure. Do not include personal screenshots, secrets, tokens, or unlicensed game covers in PRs.

Code is **MIT-licensed**. Nintendo, Discord, and AVerMedia are unaffiliated with and do not endorse this project. Game trademarks and third-party artwork belong to their respective owners.
