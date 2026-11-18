# v0.4 Windows hardware checklist

Using Switch 2, GC553Pro, LG C6 passthrough, and Discord desktop:

1. Verify Discord's own AVerMedia stream sends smooth 1080p60 video and audio to Cynthia.
2. Start SwitchAutoPresence with: python -m switchautopresence app --device 1 --discord-direct
3. Set The Legend of Zelda: Ocarina of Time manually. Confirm title, session timer and configured cover art in Discord without affecting the capture stream.
4. Minimize to tray, restore, change titles, clear, and restart. Verify the manually selected title and artwork persist.
5. With Discord still streaming, press Try automatic detection. If the card denies a second owner, verify a clear error, no repeated retry and no interference with Discord. Return to Manual mode.
6. Test Auto separately with Discord capture stopped. Go to the Switch HOME menu, select Zelda, launch it, and confirm the detected game. Try returning to HOME and losing HDMI signal.
7. Test the old saved mode direct migration (should be Cleared, no video handle). Confirm no audio relay, recording, display window, or UI preview remains.

Do not declare automatic title detection or multi-client capture production-ready until these pass on actual hardware.
