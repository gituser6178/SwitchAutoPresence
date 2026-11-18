# SwitchAutoPresence v0.4 — Presence Only

Small, local Windows app that updates Discord Rich Presence with the game you're playing on Nintendo Switch / Switch 2, artwork and an elapsed session timer.

**Discord captures and streams the AVerMedia video and game audio directly.** This application no longer has a video preview, separate stream window, audio relay, recorder, or gameplay display. You can still minimize the controller to the system tray.

## Manual mode — recommended when using Discord's direct capture

- Select a game such as The Legend of Zelda: Ocarina of Time and click **Set Discord game**.
- Optionally paste an HTTPS game-art image URL or a Discord Developer Application asset key to show the appropriate cover.
- The timer starts and updates automatically. Selecting the same title again retains the session start time.
- The selected game and artwork are saved locally. The app does not open the capture card's video handle in this mode, so Discord can directly use the card.
- Click **Clear Discord status** to remove your Rich Presence activity.

## Optional automatic game recognition

**Try automatic detection** reads local frames from the capture card every two seconds for HOME-screen OCR and launch confirmation, with no rendering or recording.

There is a hardware constraint: on some AVerMedia drivers, only one application can open the capture card. If Discord already owns it, automatic detection might not work at the same time. The program will show a capture error and stop retrying rather than repeatedly contest the stream; use Manual mode instead. Support for multiple camera consumers depends on Windows and the device driver. Windows cannot make this program read Discord's already-captured frames.

Auto recognition only identifies titles it sees selected on the Switch HOME screen, then waits for a launch transition. It cannot reliably identify Zelda when first opened in the middle of gameplay. The previous HOME title OCR was unreliable in hardware testing, so v0.4 preserves it but does **not** claim it has been fixed.

## Install and use on Windows

1. In your existing SwitchAutoPresence checkout, install dependencies: 
   
       python -m pip install -e ".[all,dev]"

2. Provide a **Discord Developer Application ID** with the environment variable SWITCHAUTOPRESENCE_DISCORD_APP_ID, or add the argument --app-id YOUR_APP_ID. Do not use your user token.
3. Discover the AVerMedia video device index with:
   
       python -m switchautopresence devices

4. Open the controller (the card is usually index 1 on the original test system):
   
       python -m switchautopresence app --device 1

5. Start with Manual game selection while streaming through Discord. Auto is experimental and should only be selected when shared capture can be confirmed.

The old --discord-direct option is accepted for existing shortcuts. It now starts the controller with video capture off and clears the old generic streaming activity; then select your game manually.

For a one-off capture diagnostic without Discord, run:

    python -m switchautopresence scan-device --device 1 --seconds 12

## Discord activity appearance

- Name: Nintendo Switch (Discord Rich Presence application)
- Details: Playing The Legend of Zelda: Ocarina of Time (or your selected game)
- State: Nintendo Switch 2
- Elapsed time: the playing session's start timestamp
- Image: the per-game HTTPS image or configured Discord Rich Presence asset key, with a generic fallback

The app cannot magically discover the exact Ocarina of Time edition artwork. Provide the image URL or configure the asset for your Discord Developer Application. The app does not bundle copyrighted game cover images.

Game recognition and artwork preferences remain local. Captured frames are not uploaded, recorded, displayed or stored. Discord Rich Presence is published through the local RPC connection. This is an unofficial app not affiliated with Nintendo, Discord, or AVerMedia.

## Development

Tests: python -m pytest -q

v0.4 is an experimental **stacked branch** based on v0.3 draft PR #3, not on main. Do not merge before Windows GC553Pro hardware validation. See docs/PRESENCE_TESTING.md.
