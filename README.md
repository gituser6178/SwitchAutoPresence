# SwitchAutoPresence 🎮

**Automatically detect Nintendo Switch and Nintendo Switch 2 games from a capture card and show what you're playing on Discord.**

SwitchAutoPresence is a planned free, open-source Windows utility that uses an HDMI capture feed to recognize the game you're playing and update **Discord Rich Presence**—without Nintendo account credentials, console mods, or sending gameplay to a cloud recognition service.

> [!IMPORTANT]
> **Status: early development / planning.** This repository does not yet contain a working application. Automatic game detection, Discord integration, and capture-card compatibility still need to be implemented and tested.

## The idea

**Nintendo Switch / Switch 2 → HDMI capture card → local game detection → Discord Rich Presence**

1. Read occasional frames from an already-connected capture card.
2. Detect the Switch HOME menu, then identify a game using its title and/or icon.
3. Confirm a game launch rather than assuming that a highlighted HOME tile is running.
4. Remember the active title during gameplay and update Discord Rich Presence.
5. Clear or pause presence when the console is asleep, the signal disappears, or confidence is too low.

The initial approach focuses on recognizing HOME-menu game artwork and text. **Arbitrary gameplay identification is not part of the first milestone**: recognizing games from gameplay alone is harder and less reliable.

## Planned features

- [ ] Capture-device discovery and selection on Windows
- [ ] Lightweight background frame sampling (without requiring a permanent preview window)
- [ ] Switch HOME-screen detection
- [ ] Local game-title recognition using OCR and/or image matching
- [ ] Game-launch confirmation, persistence, and false-positive protection
- [ ] Discord Rich Presence with game title, artwork when available, and session timer
- [ ] Manual game selection/override for unrecognized titles
- [ ] Signal-loss and sleep handling
- [ ] System-tray UI, startup options, and basic diagnostics
- [ ] Local recognition database that can be updated and contributed to

## Initial test hardware

| Component | Planned test setup |
| --- | --- |
| Console | Nintendo Switch 2 |
| Capture card | AVerMedia Live Gamer ULTRA S (GC553Pro) |
| Operating system | Windows |
| Output | Discord desktop application / Rich Presence |
| Other software | Discord streaming and VideoGameCapture |

**Hardware support is not yet verified.** A major early test is whether the capture card can be read while Discord or VideoGameCapture also accesses it. Some devices and drivers permit only one active capture consumer. The app must detect contention and explain it; it must not silently interrupt an existing stream.

## Proposed architecture

This is a starting design, **not an implemented API or final technology choice**.

```text
Capture device
    |
    v
Frame sampler (low-frequency)
    |
    v
HOME-menu detector
    |
    +--> Game title / icon matcher
    |         |
    |         v
    |    Confidence + launch confirmation
    |         |
    v         v
Session state machine (unknown / HOME / playing / signal lost)
    |
    v
Discord Rich Presence client
```

Possible tools: **Python**, **OpenCV**, an offline OCR engine, and a Discord Rich Presence client. Packaging into a standalone Windows application comes after the proof of concept.

### Detection rules

- Do not change games simply because a different HOME-menu tile is selected.
- Require several consistent observations or a recognized launch transition before updating presence.
- Keep the last confirmed game during gameplay when the HOME menu is no longer visible.
- Offer manual override and a clear **Unknown game** state.
- Handle capture devices that are busy, unplugged, asleep, or returning blank frames.
- Avoid excessive polling and unnecessary CPU/GPU usage.

## Roadmap

### Phase 1 — Capture proof of concept
- [ ] Enumerate Windows capture devices and open a selectable feed
- [ ] Confirm frames from the GC553Pro
- [ ] Measure CPU usage and detection latency
- [ ] Test concurrent access with Discord streaming and VideoGameCapture

### Phase 2 — Game recognition
- [ ] Collect *locally generated* test frames from the Switch HOME menu
- [ ] Detect HOME-menu state and identify a small test set of game titles
- [ ] Validate game-launch transitions and avoid false positives
- [ ] Add an offline/manual fallback

### Phase 3 — Discord integration
- [ ] Register a Discord developer application and configure presence assets
- [ ] Show game name and session start time
- [ ] Switch titles cleanly and clear activity after signal loss

### Phase 4 — Windows app
- [ ] Add system-tray settings and diagnostics
- [ ] Package a Windows release
- [ ] Document supported cards, limitations, and troubleshooting
- [ ] Test additional capture hardware with community help

## Privacy and security

- Game recognition should run **locally** by default.
- Do **not** commit gameplay screenshots, personal footage, Nintendo account data, private Discord identifiers, or secrets.
- Do not transmit capture frames to remote services.
- Keep user-specific settings and logs out of version control.
- Discord integration should use the local Rich Presence mechanism and a public application ID—not a user account token.

## Contributing

Contributions, testing reports, and game-recognition ideas will be welcome as the project develops. In particular, reports about different capture cards and simultaneous streaming are valuable.

Before opening a feature PR, describe the problem and proposed behavior in an issue. Please avoid submitting copyrighted game screenshots or artwork without permission.

## License and attribution

An **MIT license is planned**; a LICENSE file will be added before the first code release. Any game metadata, assets, or third-party libraries will need separate licensing and attribution review.

SwitchAutoPresence is an **unofficial community project** and is not affiliated with, endorsed by, or sponsored by Nintendo, Discord, or AVerMedia.
