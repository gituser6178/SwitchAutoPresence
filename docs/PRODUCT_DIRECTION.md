# v0.4 direction — Discord Rich Presence only

Decision on November 17, 2026: remove the Tkinter video viewer, Discord stream window, recording/window capture tools, HDMI audio monitor/bridge, mute and stream controls.

Keep:
- HOME-only local game recognition with launch confirmation, OCR diagnostics and manual title override
- Discord activity, title-specific artwork configuration and elapsed session timer
- Lightweight Windows controller, system tray, local preferences and safe device selection
- Respect native Discord direct video+audio capture as the preferred streaming workflow

**Hardware limitation:** Auto requires video access. AVerMedia GC553Pro may be exclusively owned by Discord; do not reopen repeatedly or interrupt the stream. Manual works without capture. HOME OCR for Zelda is still unverified and should be fixed separately after testing.

Do not claim that the application can read frames already owned by Discord or that Windows multi-application sharing is guaranteed. Preserve the draft v0.3 branch for rollback.
