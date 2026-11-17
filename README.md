# SwitchAutoPresence 🎮

An **unofficial Windows utility** for sharing Nintendo Switch and Switch 2 games on Discord with **automatic game recognition** or **persistent manual game selection**.

> **v0.3 pre-alpha / Windows hardware validation pending.** The application owns a single capture-card video stream, displays an optional streamable preview window, inspects the same frames for HOME-menu titles, and updates Discord Rich Presence. It is not a production-quality streamer, and audio sharing is **experimental**.

## Agreed development direction

**Streaming reliability comes first:** measured 60 FPS preview and confirmed HDMI audio in Discord, then working manual Discord Presence with artwork. Automatic recognition remains useful but must not block a release.

For automatic detection, the next design uses a **local image reference library** to recognize the selected game tile **on HOME only** (not arbitrary gameplay), with OCR as a fallback. It remembers the last confirmed active game through loading/cutscene frames. A highlighted HOME tile is *not* treated as playing, and a HOME return cannot reliably distinguish suspension from closing the game.

Users can add locally captured/owned tile references through a proposed **Add Game Image** flow; the public repository will not redistribute copyrighted game covers.

**This is a locked design decision, not yet a completed feature.** The current v0.3 build still uses experimental HOME OCR and a heuristic launch detector. See [Product direction and acceptance tests](docs/PRODUCT_DIRECTION.md).

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
3. Click **Start stream source**. The controller **stops drawing its duplicate preview** and releases its image buffer; the stream window is started **behind other windows**, instead of popping in front of your desktop.
4. In Discord's **Share Your Screen → Applications**, select **SwitchAutoPresence Stream**, not the AVerMedia video device. If it doesn't appear, press **Show stream for Discord picker** to bring it forward temporarily. After selection, cover it with other windows as usual.
5. The same in-memory video frames are periodically analyzed for the Switch HOME menu; game selection on HOME is only a **candidate**, not confirmed gameplay.
6. HOME shows **Nintendo Switch — Browsing HOME** with generic artwork; likely gameplay shows the previously selected title after several consistent non-HOME frames.

The initial HOME detector uses image-layout heuristics and offline RapidOCR. **It's experimental.** Gameplay launch can be misclassified if the HOME screen is obscured or you open another app. A fresh launch transition is required; starting in the middle of a game displays a generic Switch activity until a title can be confirmed.


### Background Discord streaming (control preview disabled)

Once **Start stream source** has been clicked:

- The **main control-panel preview is completely disabled**; no second video resizing, conversion or image allocation occurs until the stream window is closed.
- The independent **SwitchAutoPresence Stream** window remains mapped and keeps accepting the latest capture frames even if other normal windows cover it. It is lowered to the background when created rather than forced to the foreground.
- It **does not need to stay on top** to be streamable through Windows Graphics Capture, where supported. Select the **Application** window inside Discord, not the entire desktop.
- **Do not minimize or hide** the source window. A truly invisible/minimized HWND may disappear from Discord's application picker or stop updating. This release deliberately does **not** use `withdraw`, `iconify`, transparency, or other tricks that would risk freezing the feed.
- Use **Show stream for Discord picker** if it isn't selectable initially. You can then cover it again with other windows; the background rendering continues. Close the stream window to restore the control-panel preview.
- Discord and Windows have multiple window-capture methods; the user must verify actual occluded-window streaming on their own system. A future completely **headless** source would require a separate virtual capture or display backend, not a normally hidden app window.

**Sound:** The existing in-process HDMI audio relay continues independently of either preview; opening or closing the stream window doesn't enable/disable the audio monitor.

### Manual mode

Choose/type a game and click **Set manual game**. Your selection has priority and stays locked until you choose **Start automatic capture** or **Clear activity**.

Manual mode **releases the capture card**, allowing you to stream directly from your AVerMedia in Discord. It works even without an attached console. You can enter a permitted HTTPS game artwork URL or Discord image asset key for each game. The selection and artwork mapping are stored locally in Windows AppData.

### Audio: experimental, OFF by default

OpenCV captures **video only**. For sound, v0.3 includes optional in-process monitoring of the **AVerMedia HDMI audio input** to your default Windows audio output. If Discord captures the shared application's output audio, your audience may hear it as well. **This is NOT yet verified on the GC553Pro with Discord.**

- Run `audio-devices` to find the exact AVerMedia HDMI audio input index.
- In Automatic mode, the app **automatically detects and opens** the AVerMedia HDMI audio input. Use the recording-device dropdown only if you need a different input.
- Do **not** select your microphone: doing so can create feedback.
- Check Discord's **Share audio** option when sharing the stream window. Listen through headphones if needed.
- The **Mute / Unmute** button silences output for both your headphones and any Discord application-audio share without releasing the audio input. If you hear feedback or doubled audio, disable Windows **Listen to this device**.

Do not consider the streaming pipeline fully validated until video **and** audio are tested.


### Audio relay to your default Windows output (no "Listen to this device")

**No Windows Listen checkbox is required.** SwitchAutoPresence can now read HDMI audio from AVerMedia using Windows WASAPI and play it through your default Windows output, including a different host API or sample rate. The input and output are separate PortAudio streams connected by an in-memory, bounded resampling buffer. The input is never sent to cloud services or saved as a recording.

On the initial tester's PC, **HDMI audio input #14 = 48 kHz WASAPI** and the **default TOPPING USB DAC output #5 = 44.1 kHz MME**. This is now handled by the separate-stream route; previously a single duplex stream could not connect those two host APIs.

1. **Disable** Windows Sound → Recording → AVerMedia HDMI → Properties → **Listen to this device** before starting the app. Otherwise you will hear doubled audio.
2. Launch \`.\.venv\Scripts\python.exe -m switchautopresence app --device 1\` and use Automatic mode (the capture card must be free of Discord direct capture).
3. Audio starts **automatically** when the application enters Automatic mode. The best available AVerMedia HDMI input is selected, with playback routed to your default TOPPING DAC. Use the dropdowns to override devices, **Rescan** after hot-plugging, or **Mute / Unmute** playback.
4. The audio meter should report **separate**, **48000→44100 Hz**, and **output #5** while playing the game through your default speakers/headphones.
5. Check audio locally first, then enable **Share audio** when screen-sharing the **SwitchAutoPresence Stream** application in Discord; verify with a remote listener.

**Important:** the actual measured HDMI input #14 previously reported approximately -66.5 dBFS average. This routing fix cannot turn a genuinely quiet or incorrect input into loud game audio. If the meter remains nearly silent, stop the monitor, run the \`audio-test\` command against the alternate **HDMI input #9 (DirectSound)** and compare levels. The probe now uses the selected recording device's *native* sample rate (44.1 kHz for #9, 48 kHz for #14). Do not use any "Not To Use" endpoint or a microphone.

This is experimental until audio output and synchronization are verified on Windows with Discord. The buffer targets a modest latency and may underrun or drift on incompatible drivers; report warnings and actual results.


## Audio input test (recommended before Discord streaming)

**We now have a read-only HDMI-audio diagnostic.** First run `audio-devices` to find the GC553Pro's Windows recording endpoint and the default playback device. Then close the app, play an audible Switch game, and run `audio-test` with the selected input index:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence audio-devices
.\.venv\Scripts\python.exe -m switchautopresence audio-test --input N --seconds 8
~~~

Replace `N` with the correct **AVerMedia recording input index**, not your video device index (the indices may differ). The test reports RMS/peak levels without playing or saving audio.

You no longer need to run the audio-test command before using the app. **Automatic audio detection and playback start on launch** when Automatic mode is active. The GUI shows the selected HDMI input, audio levels and a **Mute / Unmute** control; device dropdowns and Rescan provide manual recovery if needed. The default playback output is used unless you choose otherwise. Discord audio sharing was successfully confirmed by a user, but sustained synchronization still needs measurement.

**A successful audio level test does not prove Discord viewers hear it.** Only a remote listener can confirm sound and synchronization. See [audio testing guide](docs/AUDIO_TESTING.md) for the three-step verification and troubleshooting.

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
.\.venv\Scripts\python.exe -m pip install --no-deps --force-reinstall "opencv-python>=4.8,<5"
.\.venv\Scripts\python.exe -c "import cv2; print(cv2.__version__)"
~~~

This repair operates **only inside the project virtual environment**. The project uses Pillow/Tkinter for previews, so we can use a single OpenCV package.

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

Use **Start stream source** in the UI and share that application window on Discord. **Do not close the app while it is being streamed**.

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

- The Tkinter video-only window renders at up to **60 FPS** (rendering target, not a guaranteed frame rate); this is a functional preview, **not yet a validated 60 FPS streaming renderer**. HDMI passthrough on the AVerMedia is not affected.
- Full-speed capture decode and per-frame Tkinter image drawing may use CPU. OCR is sampled infrequently rather than processed on every frame.
- The GC553Pro hardware probe succeeded alone (426 frames / 8 sec, no read errors), and failed while another app used its video feed. The integrated preview has **not yet been hardware-tested**.
- The capture device must be free when Automatic mode starts. Manual mode relinquishes it.
- Voice/audio monitoring and Discord application audio capture must be tested; the implementation is not a guarantee of working sound.
- The HOME title recognizer is heuristic. Unknown games use generic artwork. It does not recognize arbitrary gameplay scenes.
- This is a Windows developer prototype, not a packaged installer or system-tray release.

## Privacy and license

The app runs locally by default. No video or audio is saved or uploaded by this code. The only intended network-facing presence action is Discord's IPC client, which publishes game title/details/artwork you configure. Do not include personal screenshots, secrets, tokens, or unlicensed game covers in PRs.

Code is **MIT-licensed**. Nintendo, Discord, and AVerMedia are unaffiliated with and do not endorse this project. Game trademarks and third-party artwork belong to their respective owners.

### 60 FPS and HOME OCR diagnostics

- The dedicated stream window now targets a frame refresh every **16 ms** (roughly 60 FPS), but Tkinter/Pillow can be slower. The controller displays measured capture FPS and measured stream-window FPS; neither is guaranteed.
- HOME title candidates survive up to **three consecutive OCR misses** (about 6 seconds at default sampling), to avoid losing a recognized title immediately before a launch. Repeated misses still expire the title to avoid falsely identifying another game.
- When recognition fails, the controller shows the **last HOME OCR text** and candidate title. If the candidate remains `none`, `scan-device` can help tune the OCR region.
- The project now uses **opencv-python 4.x** as its sole OpenCV dependency. If you previously installed both OpenCV variants in the virtual environment, uninstall both and reinstall `.[all]` once.
- Audio is still **experimental**: choose the AVerMedia HDMI audio endpoint and confirm a remote Discord listener hears the sound when application audio sharing is enabled.

### Improved HOME title recognition

- Recognition now isolates the Switch 2's cyan game-title line and tries recognition-only OCR before default OCR.
- Neutral-gray game loading frames are no longer automatically classified as HOME without title evidence.
- Two consecutive HOME observations are required before interrupting active gameplay.
- The scan-device command reports OCR method (cyan_line, normal_ocr, cyan_title_unreadable, neutral_without_title), recognized text and matched game.
- If a title remains unknown, run scan-device while highlighting Zelda on HOME and share its text output. Do not upload captured gameplay.

### Automatic audio and mute (current build)

On Windows the app now discovers the capture-card HDMI audio endpoint itself, preferring **AVerMedia HDMI / Windows WASAPI** and remembering a successful device by name and API even if Windows renumbers it. The audio relay connects automatically when Automatic mode starts. It does **not** auto-select your microphone or any endpoint marked `Not To Use`.

There is no Start Audio Monitor button. You can change the **Recording input** or **Playback output** dropdown and the route restarts automatically; **Rescan** refreshes connected device choices. The **Mute** button silences local output and Discord's application audio without closing the HDMI stream; **Unmute** restores it. Manual game mode deliberately releases the capture card for direct Discord capture, so the app's automatic audio route is used in Automatic mode.

The duplicate control-panel preview widget is **destroyed** while the stream source is open. Closing that stream window recreates the control-panel preview. The source window remains mapped/unminimized behind other applications so Discord may capture it; a truly invisible capture source requires another backend.

### Stream-window frame pacing update

A GC553Pro hardware screenshot showed **59.8 FPS capture** but only **37.9 FPS stream rendering**. The renderer used to wait 16ms *after* each Tkinter image resize and copy, wasting most of its 60fps frame budget. The GUI now schedules against the frame's **start time**, uses efficient linear downscaling and reuses a Tk image object when window dimensions are unchanged.

The controller now displays actual **capture FPS**, **stream-window FPS**, and **average image-render duration in ms**. Continue testing while Discord shares the unminimized stream source. A 60fps target is not a performance guarantee; if 1080p/720p still fails, a GPU-backed renderer is a stronger next step than arbitrarily requesting a higher capture rate.
