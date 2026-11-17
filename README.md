# SwitchAutoPresence 🎮

**Automatically detect Nintendo Switch and Nintendo Switch 2 games through a capture card and display them in Discord Rich Presence.**

> **Status: pre-alpha.** This repository has a **Phase 1 capture diagnostic**, not automatic game recognition or Discord integration yet.

SwitchAutoPresence is an unofficial, free, locally running Windows project. No Nintendo account login or console modifications are planned.

## How it should work

Nintendo Switch / Switch 2 → USB capture device → offline HOME-menu game detection → confirmed game state → Discord Rich Presence.

First, we need to prove we can inspect the capture feed without breaking existing Discord streaming. A game highlighted on the Switch HOME menu must **not** be treated as a launched game; future versions will verify launch transitions.

## Phase 1: Capture diagnostics

Requires Windows 10/11 and Python 3.10+.

~~~powershell
git clone https://github.com/gituser6178/SwitchAutoPresence.git
cd SwitchAutoPresence
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[windows]"
switchautopresence devices
switchautopresence probe --device 0 --seconds 8
~~~

**Replace 0 with the video-device index reported by devices.** The device name/index depends on Windows and driver ordering. The application does not save images, video, or audio; it reports only frame statistics. It does not connect to Discord yet.

For a safe step-by-step test, including a second test during Discord streaming, see **[Phase 1 testing guide](docs/PHASE1_TESTING.md)**.

### Initial target hardware

- Nintendo Switch 2
- AVerMedia Live Gamer ULTRA S (GC553Pro)
- Windows desktop with Discord
- Existing VideoGameCapture viewer / Discord screen sharing

**Hardware compatibility has not been verified.** Some capture cards only allow one application to read the device. If that occurs, we'll need a shared capture architecture.

## Roadmap

- [x] Phase 1 diagnostic CLI, camera enumeration, and automated unit tests (hardware validation pending)
- [ ] Test simultaneous device access while Discord is streaming
- [ ] Phase 2 offline HOME-screen detection, game-title recognition, and launch confirmation
- [ ] Phase 3 Discord Rich Presence, game artwork, play timer, and inactivity handling
- [ ] Phase 4 Windows tray app, settings, packaging, and community game database

## Privacy

All recognition is intended to run locally. This Phase 1 tool does not transmit or save captured gameplay. Do not commit game footage, screenshots, Nintendo credentials, or Discord user tokens.

## License

Code is released under the [MIT License](LICENSE). Nintendo game art, third-party assets, and metadata have their own licensing requirements; MIT does not grant rights to those.

SwitchAutoPresence is **not affiliated with or endorsed by Nintendo, Discord, or AVerMedia**.
