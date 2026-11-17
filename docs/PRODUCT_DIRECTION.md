# Detection and release priorities (decision locked 2026-11-16)

## Product goal

A reliable Windows Nintendo Switch / Switch 2 Discord activity tool that **does not require perfect automatic recognition to be useful**. The current AVerMedia GC553Pro prototype has working video preview on one test machine; 60 FPS rendering, audio delivery to remote Discord viewers, and automatic title recognition are **not validated**.

## Priority order

1. **P0 — Streaming actually works:** stabilize video preview, measure actual (not requested) 1080p60 or 720p60 capture/render performance, reduce unnecessary CPU work, test Discord window sharing, and guarantee/verify capture-card audio is heard by a remote Discord viewer without echo or drift. Do not advertise a full streamer until sound is verified.
2. **P1 — Reliable manual Discord presence:** title entry/search, persistent override, session timer, generic Nintendo Switch branding, artwork mapping/fallback, correct Discord activity updates and reconnects. Manual mode must release direct hardware capture for Discord if selected.
3. **P2 — Simple HOME-only automatic recognition:** local image library of cover/tile images, selected-tile localization and visual matching; only use OCR for a title that's not matched. No attempt to classify arbitrary gameplay frames.
4. **P3 — Polish:** game library management UI, diagnostics, window/tray controls and packaging, wider capture-card compatibility.

## Automatic mode: deliberately limited

- **Recognize the HOME UI** with more than a neutral-background heuristic; avoid loading-screen false positives.
- Identify **which tile is highlighted**, then crop that tile's artwork *inside* selection borders, not the blue border or neighboring tiles. Do not assume the highlighted tile is always at the same position.
- Compare it with a **local reference library** of per-game images (one or more variants per title) using a lightweight perceptual hash / feature matching approach; require a confidence threshold AND a clear margin over second-best match. If unrecognized or ambiguous, show an unknown candidate rather than a wrong game. OCR can be an optional fallback.
- Keep matching to **one frame every ~1–2 seconds on HOME only**, not 60 FPS gameplay. Recognition should not affect the live preview frame rate.
- Remember the most recent **confirmed** active title through loading screens, cutscenes and pauses. Do not use the appearance of a black screen to decide a game has closed.
- On HOME, display **Nintendo Switch — Browsing HOME** even if the selected tile is known. Store the selected tile only as a *candidate* until a supported launch transition is detected. Do not equate a highlighted tile to an active game.
- When the player returns to HOME, display Browsing HOME, retaining the last confirmed title only internally; a suspended versus closed game cannot be distinguished with certainty from HDMI footage alone.
- On X/Close Software, do not claim closure unless a visible cue can be reliably distinguished; staying on HOME remains the accurate public presence either way.
- On loss of HDMI frames for a configurable grace period, clear auto activity; do not treat a still but valid video frame as signal loss.
- Manual mode is always authoritative: changing HOME selection does not overwrite manual game, and manual works with no capture hardware.

## Local game image library

A proposed **Add Game Image** action captures the currently highlighted tile from the application's own in-memory feed at the user's request. The user confirms the game's name and the crop. Save locally in Windows AppData under SwitchAutoPresence (not the repo); allow importing additional local image files as reference images, replacing or deleting erroneous entries, and storing multiple editions/covers per title.

Use game title metadata separate from reference image bytes. Do not bundle copyrighted Nintendo/third-party cover images in this public MIT repository without permission. A local user-managed library is different from redistributing those images in GitHub. Do not silently download artwork from websites or store captured whole screens; provide an explicit choice and a private local destination.

## State transitions and examples

| Input/condition | Activity shown | Internal state |
| --- | --- | --- |
| First capture opens in gameplay, no known title | Nintendo Switch — Playing on Nintendo Switch | Unknown |
| HOME seen, Zelda highlighted | Nintendo Switch — Browsing HOME | Zelda candidate only |
| User actually launches Zelda from HOME (confirmed transition) | Nintendo Switch — Playing Zelda | Zelda confirmed |
| Zelda loading screen / dark cutscene | Keep Playing Zelda | No reset |
| Return to HOME (game may be suspended) | Nintendo Switch — Browsing HOME | Last confirmed game retained internally |
| HOME X → Close Software | Nintendo Switch — Browsing HOME | No claim that game is running |
| HOME switches from Zelda to Pokémon (before launch) | Nintendo Switch — Browsing HOME | Pokémon candidate, Zelda not silently replaced |
| Signal lost for defined grace period | Clear automatic activity | No signal |
| User manually selects Pokémon | Nintendo Switch — Playing Pokémon | Manual locked |
| User changes HOME selection while manual locked | Keep Playing Pokémon | Manual locked |

## Acceptance tests

- Local reference image match works on multiple resolutions, thumbnail crop sizes, selected-border colors and dark/light HOME themes without sending captured frames to an external server.
- Different game covers and alternate editions do not cross-match; ambiguous images remain unknown.
- Negative tests: black loading scenes, cutscenes, gray game screens, HOME dialogs, text overlays and HOME with no selected game.
- No gameplay frame recognition loop; HOME detection only and carefully validated transitions.
- No false game changes while manual override is active; resetting to Auto requires a fresh HOME match.
- Capture and preview measure stable frame rate, with screenshots/photos and app logs shared only at user discretion. Prefer diagnostic text.
- Sound reaches a remote Discord viewer with video in sync. If not, do not mark streaming as complete.

## Scope of existing prototype

The current v0.3 draft PR still implements HOME OCR and a heuristic launch state. The visual-library matcher and image-management UI are **planned**, not yet implemented. Do not mark the new matcher as done based on the existing OCR test suite or assume hardware support from mock unit tests.

## Stream-window rendering policy (November 2026)

- [x] Disable and release the duplicate main GUI video preview entirely while the Discord-streamable source window exists; restore when it closes
- [x] Launch the stream source in the **background** rather than foreground or always-on-top, and keep rendering to that source while it is covered by normal Windows apps
- [x] Provide a **Show stream for Discord picker** recovery button to raise it if Discord fails to enumerate the source
- [ ] Verify covered-window capture with the user's Discord client and actual Windows Graphics Capture mode
- [ ] If a truly invisible source is required, design/test an alternative **virtual capture/display** architecture; a hidden/minimized Tkinter HWND is **not** a reliable Discord source
- [ ] Measure CPU usage and actual sustained preview/Discord frame rate during occluded streaming
