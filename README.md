# SwitchAutoPresence 🎮

**Automatically detect Nintendo Switch and Nintendo Switch 2 games through a capture feed and display them in Discord Rich Presence — with manual game selection when you want it.**

> **Status: pre-alpha.** This repository currently has a **Phase 1 capture diagnostic**. Game recognition, window capture, manual selection, and Discord integration are **planned, not implemented**.

SwitchAutoPresence is an unofficial, free, locally running Windows project. No Nintendo account login or console modifications are planned.

## Planned modes: automatic + manual

| Mode | Expected behavior |
| --- | --- |
| **Automatic** (default) | Sample frames from the existing video viewer, recognize the Switch HOME screen, confirm the running title, and update Discord. |
| **Manual** | Search/select a Nintendo Switch or Switch 2 title and show that title on Discord, even if there is no capture feed. Manual mode **locks the selected title** until the user returns to Automatic mode or clears activity. |
| **Clear activity** | Remove the app's Discord activity until the user explicitly selects a game or resumes Automatic mode. |

**Priority:** Manual selection always wins over automatic recognition. Detection must never silently overwrite a manual game. Switching back to Automatic releases that override; if recognition is uncertain, show an unknown/unset state instead of claiming the wrong game. A future tray UI should clearly show the current mode, game, and detection confidence.

This makes the app useful for people **without a capture card** too: they can use manual mode as a basic Switch Discord presence application.

## Capture architecture

**Nintendo Switch / Switch 2 → AVerMedia capture card → VideoGameCapture viewer → local window-frame sampling → game recognition → Discord Rich Presence**

We should **not open the capture card a second time** while VideoGameCapture/Discord uses it. A real Windows test with the AVerMedia Live Gamer ULTRA S (GC553Pro) returned `Status: unavailable` when another viewer was active; exclusive capture access is the leading explanation, though exact driver behavior still needs validation.

In that same setup, **only Discord's small self-preview pauses to save resources; the VideoGameCapture window itself continues rendering**. Therefore, the next experiment is sampling occasional frames from the **VideoGameCapture window**, rather than opening the hardware again.

Window capture must be tested for occluded, minimized, or off-screen windows. If the viewer stops rendering when minimized, we should provide a supported fallback (for example, a shared video pipeline) rather than claiming invisible capture always works.

### Detection rules

- A game being **highlighted** on HOME does not prove it has launched.
- Confirm launch/transitions before changing activity.
- Require consistent observations, avoid oscillating statuses, and preserve the last confirmed title when gameplay replaces HOME.
- Never infer a game solely from a stale or frozen frame.
- Do not collect or upload gameplay frames or personal footage to a remote service.
- Unknown titles can be selected manually, with a local game catalog and room for custom entries.



### HOME screen recognition and Discord activity

The Switch HOME menu displays the **highlighted game's full title above its tile** (for example, `The Legend of Zelda: Ocarina of Time`). Automatic detection should start by cropping that title area from frames captured from the **VideoGameCapture window** and reading it with offline OCR, optionally verifying a title against the tile artwork.

**Do not mistake the highlighted tile for the game currently running.** Store it as a *candidate* until a launch transition is confirmed. If the console is on HOME, Discord should **still show Nintendo Switch as the activity**, with a generic Switch image and details like `Browsing HOME`. Never display `Playing <title>` merely because its tile is selected.

### Discord artwork

Use the Discord application identity **Nintendo Switch** for both modes. Its Rich Presence **large image** should change with the confirmed game, with an optional **small Nintendo Switch icon** overlay. In manual mode use the manually selected game's art, regardless of what the video recognizer sees.

| Observation | Discord activity name | Details | Large image |
| --- | --- | --- | --- |
| HOME menu visible | Nintendo Switch | Browsing HOME | Generic Switch artwork |
| Game launch confirmed | Nintendo Switch | Playing [confirmed title] | Game cover/icon |
| Unknown active game | Nintendo Switch | Game not recognized | Generic Switch artwork |
| Manual game chosen | Nintendo Switch | Playing [selected title] | Selected game's cover/icon |
| Console off / signal lost in AUTO | Clear after a reasonable grace period | — | — |

The image source should come from a **licensed/approved asset catalog**, or a valid publicly accessible URL when permitted; use the generic Switch image if a game has no safe art source. Do not dump copyrighted game cover artwork into the public GitHub repository without permission. Discord supports uploaded Rich Presence art assets and publicly accessible external URLs, subject to the specific RPC/SDK integration and valid image requirements. Images should not require uploading captured gameplay.

## Phase 1: Capture diagnostics

Requires Windows 10/11 and Python 3.10+.

~~~powershell
git clone https://github.com/gituser6178/SwitchAutoPresence.git
cd SwitchAutoPresence
git switch feat/phase1-capture-diagnostics
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[windows]"
.\.venv\Scripts\python.exe -m switchautopresence devices
.\.venv\Scripts\python.exe -m switchautopresence probe --device 1 --seconds 8
~~~

**Replace 1 with your own device index.** The diagnostic does not save images, video, or audio; it reports aggregate frame statistics only. It does not connect to Discord.

See the **[Phase 1 testing guide](docs/PHASE1_TESTING.md)** for the reproducible test procedure.

### Hardware findings (one initial Windows setup)

- Nintendo Switch 2 and **AVerMedia Live Gamer ULTRA S (GC553Pro)** detected as capture device index 1.
- DirectShow probe when used alone: **426 frames in 8.01 seconds, no read errors, 640×480 negotiated resolution, ~53.2 observed FPS**.
- The same probe while the existing streaming/capture application was active returned **unavailable**.
- Discord's *self-preview* pauses for resource savings; the independent **VideoGameCapture window is still live**.

These are **observations from one system**, not broad hardware guarantees. The detected resolution is not necessarily the console's output resolution.

## Roadmap

- [x] Phase 1 diagnostic CLI, device enumeration and automated unit tests
- [x] Confirm initial GC553Pro direct-capture success and failure alongside the existing viewer
- [ ] Phase 1B: read frames from the VideoGameCapture **window** without opening the capture device
- [ ] Test minimized/occluded windows, Discord streaming, viewer compatibility and CPU usage
- [ ] Phase 2: OCR the HOME title strip, retain selected candidate, confirm actual launch and keep a generic Nintendo Switch activity while browsing HOME
- [ ] Phase 3: Discord Rich Presence with per-game large artwork, small Nintendo Switch icon, fallback art, and **manual/automatic mode selection with explicit override behavior**
- [ ] Phase 4: Windows tray app, settings, packaging and optional community title catalog

## Privacy

Recognition should run locally. This Phase 1 tool does not transmit or save captured gameplay. Do not commit game footage, screenshots, Nintendo credentials, or Discord user tokens.

## License

Code is released under the [MIT License](LICENSE). Nintendo game art, third-party assets and metadata have their own licensing requirements; MIT does not grant rights to those.

SwitchAutoPresence is **not affiliated with or endorsed by Nintendo, Discord, or AVerMedia**.
