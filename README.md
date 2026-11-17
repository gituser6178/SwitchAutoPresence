# SwitchAutoPresence 🎮

**Unofficial Windows app for Nintendo Switch / Switch 2 Discord Rich Presence: automatic detection from an existing video viewer, or a persistent manual game selection.**

> **v0.2 pre-alpha prototype (Windows hardware testing pending).** The application code, desktop controls, offline OCR integration, and Discord RPC integration are implemented, but the actual viewer-window capture, launch heuristics, and Discord artwork must be verified on a Windows PC. This is not a finished or packaged release.

## What it does

- **Automatic:** read occasional frames from an already-running **VideoGameCapture** window via Windows Graphics Capture. This does **not** open the AVerMedia capture device a second time.
- **HOME screen:** read the selected game's title using **offline OCR**. A highlighted HOME tile is a *candidate*, **not** a game currently running. Discord instead displays **Nintendo Switch — Browsing HOME** with generic artwork.
- **Game launch:** after consistent non-HOME frames, promote the last selected title into a likely playing game. The first launch detector is a heuristic and can make mistakes; see limitations.
- **Manual:** choose or type any game title, optionally provide its cover art URL/Discord asset key, and lock that selection until Automatic or Clear is chosen. Works without a capture card.
- **Discord:** local Rich Presence IPC using **pypresence 4.6+**, with the displayed activity name **Nintendo Switch**, game details, artwork, and playtime. No Discord user token or Nintendo login.
- **Privacy:** no gameplay images are saved or uploaded; local settings are stored in Windows AppData.

## Architecture

~~~text
Nintendo Switch 2 --HDMI--> AVerMedia GC553Pro --USB--> VideoGameCapture viewer
                                                      |
                                              Windows Graphics Capture
                                              (existing viewer WINDOW)
                                                      |
                                               1 sample / ~2 sec
                                                      |
                                              HOME layout check
                                                      |
                                               offline RapidOCR
                                                      |
                                            candidate / playing state
                                                      |
                            Manual selection ----------+ (manual wins)
                                                      |
                                        Discord local Rich Presence IPC
~~~

Discord's self-preview pausing doesn't affect this design as long as **VideoGameCapture itself continues rendering**. Occluded and minimized-window capture still need real-machine testing.

## Run on Windows

Python 3.10+ is required; Windows 10 1903+ or Windows 11 recommended. From an existing checkout of this repository (and an existing virtual environment):

~~~powershell
git fetch origin
git switch feat/phase2-auto-manual-presence
.\.venv\Scripts\python.exe -m pip uninstall -y opencv-python
.\.venv\Scripts\python.exe -m pip install -e ".[all]"
.\.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps "opencv-python-headless>=4.8,<5"
.\.venv\Scripts\python.exe -c "import cv2; print('OpenCV:', cv2.__version__)"
~~~

The uninstall removes the older GUI OpenCV wheel from **this project virtual environment only**: RapidOCR now uses the headless OpenCV build, which still supports video processing. Do not uninstall global Python packages.

**The `probe-window` command exists only on the `feat/phase2-auto-manual-presence` branch.** If the help output lists only `devices` and `probe`, run `git branch --show-current`, switch to the v0.2 branch, and reinstall from that checkout. OpenCV 5 is not supported; the repair command above is intentionally version-constrained.

**First test viewer-window capture while VideoGameCapture is open:**

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence windows
.\.venv\Scripts\python.exe -m switchautopresence probe-window --window "VideoGameCapture" --seconds 8
~~~

If the title is different, supply the **visible window title substring** from the first command. Or pass its decimal handle using `--hwnd 123456` instead of name matching.

**Then display Switch HOME and test OCR:**

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence scan-window --window "VideoGameCapture" --seconds 12
~~~

Expected diagnostic: `screen=home | title=The Legend of Zelda: Ocarina of Time` (the exact frame content may differ). No frames are saved. If it reports `screen=other` while on HOME, adjust the capture target/ROI and report it so we can improve the HOME classifier.

**Launch the app (manual UI works even before Discord is configured):**

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence app --window "VideoGameCapture"
~~~

For Discord presence to display for real:

1. Create a Developer Application at [Discord Developer Portal](https://discord.com/developers/applications).
2. Copy its **Application ID** (public identifier, not a user token).
3. Ensure the desktop Discord client is open, then launch:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence app --window "VideoGameCapture" --app-id YOUR_APPLICATION_ID
~~~

The application uses pypresence's modern activity-name override to request **Nintendo Switch** as the displayed Rich Presence name. Discord's actual display should be verified on your client.

### Game images

In the app's **Game artwork** field, enter an **HTTPS URL directly to an image** you have permission to use, or an asset key uploaded in your own Discord application's **Rich Presence → Art Assets**. Then select **Set manual game**. The title and artwork URL are remembered locally.

Automatic mode also uses those saved per-game art mappings. For a generic HOME or unrecognized title, optionally configure `generic` and `small` image asset keys in a local JSON file based on [artwork.example.json](artwork.example.json):

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence app --app-id YOUR_APPLICATION_ID --artwork .\my-artwork.json
~~~

If no image is configured, Discord may show the Developer Application's default icon. **No copyrighted game cover files are bundled with this repository.**

### Add more games

The initial offline title list is intentionally small; see the names in [catalog.py](src/switchautopresence/catalog.py). Create a local JSON array of additional exact game titles (copy [titles.example.json](titles.example.json)), then run with `--titles .\my-titles.json`. Manual mode accepts arbitrary names even without this catalog.

### Legacy diagnostic

The Phase 1 hardware capture probe is still available:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence devices
.\.venv\Scripts\python.exe -m switchautopresence probe --device 1 --seconds 8
~~~

**Don't run the direct hardware probe while an important Discord stream is active.** The tested GC553Pro returned unavailable when another app already held the video source. Use `probe-window` instead.

## Verification and known limitations

- Unit tests include state transitions, manual priority, game matching, artwork resolution, Discord reconnection and window-frame sampling with **mock capture/Discord/OCR**.
- Windows hardware validation is still pending. The HOME visual classifier uses layout heuristics and an adjustable title rectangle (default `--roi 0.08,0.19,0.84,0.19`). OCR can misread titles, and modal windows can resemble launch transitions. **Do not consider automatic launch identification fully reliable yet.**
- Windows Graphics Capture may fail for minimized windows; no hidden background capture guarantee until tested.
- If video is unchanged, Windows may not emit a new frame. A static HOME screen is **not** automatically treated as a lost signal.
- The program does not require or attempt Nintendo account access, cloud OCR, console mods or screenshot uploads.
- Current interface is a **small Tkinter window**, not a system-tray app or installer.

See [Phase 2 testing guide](docs/PHASE2_TESTING.md) for reproducible test steps, expected results, and troubleshooting.

## License / attribution

MIT license for the code. Game images, text, logos and other third-party assets remain subject to their respective copyrights and usage permissions. This project is unofficial and **not affiliated with Nintendo, Discord or AVerMedia**.
