# Phase 2 — Windows viewer + Discord validation

This procedure targets the Nintendo Switch 2, AVerMedia GC553Pro, VideoGameCapture viewer and desktop Discord.

## 0. Safety

No captures or gameplay frames are saved or uploaded. Always open the **viewer window**, not a second AVerMedia capture handle. Avoid testing direct device access during important streams. A manual game may be displayed without any capture card.

## 1. Update the development branch

~~~powershell
cd C:\WINDOWS\system32\SwitchAutoPresence
git fetch origin
git switch feat/phase2-auto-manual-presence
.\.venv\Scripts\python.exe -m pip uninstall -y opencv-python
.\.venv\Scripts\python.exe -m pip install -e ".[all]"
.\.venv\Scripts\python.exe -m pip install --force-reinstall --no-deps opencv-python-headless
.\.venv\Scripts\python.exe -c "import cv2; print('OpenCV:', cv2.__version__)"
~~~

Use your actual local repository path if it differs.

## 2. Find viewer window

Open VideoGameCapture with the Switch 2 powered on, then:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence windows
~~~

Locate the exact title, e.g. **VideoGameCapture**. If name matching fails, use the decimal HWND from this output.

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence probe-window --window "VideoGameCapture" --seconds 8
~~~

Expected: `Status: ok`, nonzero samples, real frame dimensions. The capture card should remain available to the existing stream. Test while Discord is streaming, and note whether streaming ever stops.

**If no frames:** check window title, whether the viewer is minimized, exclusive fullscreen / protected windows, Windows version, and hardware acceleration. Try `--hwnd N` with the window's handle. Report whether the viewer was foreground, covered, or minimized. Windows Graphics Capture may stop for minimized windows.

## 3. Verify OCR on HOME

Navigate to the Switch 2 HOME menu and **highlight Zelda: Ocarina of Time**.

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence scan-window --window "VideoGameCapture" --seconds 12
~~~

Expected at least one `screen=home` result with `title=The Legend of Zelda: Ocarina of Time`. Test a second title such as Pokémon Violet.

If HOME shows as `screen=other`, the visual heuristic or window crop is not yet calibrated to the real video. If HOME is detected but title is blank, adjust the normalized title ROI:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence scan-window --window "VideoGameCapture" --roi "0.08,0.19,0.84,0.19" --seconds 12
~~~

ROI format is `x,y,width,height`, all values in 0..1. Tuning affects only where OCR reads, not the HOME layout classification. To prevent personal footage exposure, report **the text output**, not gameplay screenshots.

## 4. Run the UI, including manual without Discord

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence app --window "VideoGameCapture"
~~~

- Enter `Pokémon Violet`, select **Set manual game**: manual mode remains selected regardless of camera/recognition updates.
- Optionally enter a direct HTTPS artwork URL or Discord asset key before selecting it.
- Close and reopen: manual selection should restore from Windows AppData.
- Select **Automatic**: manual override disappears and a fresh HOME observation is required.
- Select **Clear activity**: stays cleared until you explicitly select Manual or Automatic.

This runs in **dry-run** mode if no Discord Application ID was supplied.

## 5. Test Discord Rich Presence

Create a Discord Developer Application, then use its public Application ID (never a user token):

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence app --app-id YOUR_APP_ID --window "VideoGameCapture"
~~~

- **Manual Pokémon:** should show `Nintendo Switch` with `Playing Pokémon Violet`; a configured artwork URL/asset should appear as large image.
- **Automatic + HOME:** should show `Nintendo Switch` / `Browsing HOME`, not claim the highlighted game is running.
- **Automatic + launch:** after a few new non-HOME frames, should display the previously selected title. **Launch detection is still heuristic**; record false positives.
- **Back to HOME:** should immediately revert to browsing.
- **Clear:** should remove this app's Rich Presence.
- **Discord closed:** app should remain running and retry connection periodically.
- **Viewer unavailable:** manual selection still works.

Note that Discord client rendering and external image URL support must be verified on Windows.

## 6. Report back

Text to provide:

- Viewer window title (from `windows`)
- Result of `probe-window` (samples/resolution)
- Result of `scan-window` on HOME
- Whether Discord streaming continued normally
- Whether manual Rich Presence and artwork displayed
- Any minimized-window or OCR issue

Do not post private API tokens, screenshots containing personal information, or captured gameplay footage.
