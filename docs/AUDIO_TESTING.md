# HDMI audio troubleshooting: AVerMedia GC553Pro → SwitchAutoPresence → Discord

The AVerMedia GC553Pro supports HDMI audio. **OpenCV only reads video**, so sound requires capturing the card's Windows audio endpoint separately. The current prototype uses \`sounddevice\` (PortAudio) to monitor that input through a Windows output. Discord may capture the application's audio when sharing the SwitchAutoPresence stream window, but this has **not been confirmed on the user's PC**.

## Step 1: Find the HDMI recording input (no recording/playback)

Run from your existing checkout:

~~~powershell
git fetch origin
git switch feat/phase2-auto-manual-presence
git pull --ff-only origin feat/phase2-auto-manual-presence
.\.venv\Scripts\python.exe -m pip install -e ".[all]"
.\.venv\Scripts\python.exe -m switchautopresence audio-devices
~~~

- Find an **AVerMedia**, **Live Gamer ULTRA S** or **HDMI** *recording input*. Note its number. Device names can differ between Windows drivers and host APIs; seeing a similarly named device more than once is normal.
- Also note the **default playback output** (headphones/speakers); the CLI identifies it in the output.
- Avoid selecting a microphone. It can capture private conversations and can create feedback when monitored.

## Step 2: Verify incoming game audio (nothing played or saved)

Temporarily **close SwitchAutoPresence** and any other program using the capture-card audio input. On the Switch, run a game with audible music/effects, not a silent HOME screen.

Replace \`N\` with the AVerMedia *audio input* number found above:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence audio-test --input N --seconds 8
~~~

Example summary (illustrative, not an observed measurement):

~~~text
Input: [N] AVerMedia HDMI Audio
Status: signal | 2 channels | 48000 Hz | 8.0 seconds
RMS: -24.0 dBFS | Peak: -8.5 dBFS | Blocks: 750
Input detected. Next enable audio monitoring...
~~~

- **Status: signal** — audio energy is reaching Windows through that recording endpoint. It does not yet prove Discord receives it.
- **Status: silent** — the endpoint opened but the meter saw virtually no signal. Check Switch volume and mute state, HDMI audio input format (try 48 kHz stereo/PCM), and whether you've chosen the right input.
- **Status: no_frames** — the input opened but delivered no audio blocks. Recheck Windows recording permissions and exclusivity.
- **Error about 48000 Hz** — try a different listed entry for the capture card, or check Windows Sound → Recording → the HDMI input → Advanced default format.

The test **does not write a sound file**, play sound through speakers, or send audio to a server; it only prints energy statistics.

## Step 3: Monitor it through SwitchAutoPresence

Once the audio-test shows a signal:

~~~powershell
.\.venv\Scripts\python.exe -m switchautopresence app --device 1 --fps 60
~~~

- Choose **Automatic** and confirm video preview works.
- The app automatically discovers an AVerMedia HDMI input and selects it; you can override this using the **Recording input** dropdown.
- The **Windows playback output #** can be left blank to use your default headphone/speaker output; you can enter the output index if needed.
- Audio routing begins automatically in Automatic mode; watch the **RMS/peak** numbers change while Switch audio plays.
- You should hear the game through your selected Windows playback device. Use headphones to prevent acoustic feedback. Turn the volume down first.
- If PortAudio rejects the paired input/output devices, note their **host APIs** from \`audio-devices\`. Try an AVerMedia input and playback output on the same compatible host API, or adjust both Windows default formats to 48 kHz.
- Use **Mute / Unmute** to silence or restore the app's output, or switch the input/output dropdown to reconfigure. Use **Rescan** if you reconnect hardware. No separate Start Audio button is required.

## Step 4: Verify remote Discord audio

1. In Discord desktop on Windows, use **Share Your Screen → Applications** and select **SwitchAutoPresence Stream**. Do **not** select the AVerMedia device separately while the app owns it.
2. Enable **Share audio** when the option is offered.
3. Ask a second person listening to your stream whether they can **hear the game clearly and in sync**.
4. Check for echo, double audio, crackles, clipping and lip-sync delay.

If you hear sound locally but a remote viewer hears nothing, **the HDMI capture works and the problem is now between this Python app's playback output and Discord application-audio capture**. This may require a different output architecture (e.g. a virtual audio device or a dedicated streaming backend); don't keep changing game-recognition code or capture-card settings randomly.

Discord's audio capture support varies by client and sharing mode. Sharing the entire desktop may include unrelated application sounds, so use care with privacy.

## What to send back

Provide only text:
- The AVerMedia recording input line(s) and default playback output from \`audio-devices\`.
- The \`audio-test\` status, RMS dBFS and peak dBFS.
- Whether **you** hear the monitored audio and whether **someone in Discord** hears it.

**Do not share microphone recordings, device credentials, or personal conversations.**

## Nintendo Switch 2 stereo setting and weak-signal readings

If the AVerMedia input opens and reports many audio blocks but the overall RMS is very low (for example, -63.6 dBFS) while peaks are higher (for example, -30.4 dBFS), it is **not absolute digital silence**. The updated probe reports `weak_signal` for noticeable isolated peaks. These could be intermittent game audio or background noise; the level meter alone cannot identify their source.

On the Switch 2, select **System Settings → Audio → TV Sound → Stereo**, then try **Test Output** while measuring the AVerMedia HDMI input again. AVerMedia specifically warns that the GC553Pro cannot accept the Switch 2's 5.1 LPCM format; stereo is the recommended capture format. Make sure sound isn't redirected to wired or Bluetooth headphones.

Official references:
- Nintendo Switch 2 audio menu: https://en-americas-support.nintendo.com/app/answers/detail/a_id/68202
- AVerMedia HDMI audio troubleshooting: https://www.avermedia.com/in/support/faq/why-cant-i-hear-the-game-audio-on-recentral-4-and-recording-video-clip-oJ2Go2vZ-pdbwqKzM

If Stereo + Test Output still yields very low readings, test the same HDMI source using the alternative **HDMI (GC553Pro)** recording device exposed through DirectSound (index 9 on the initial test PC) or WDM-KS (index 28). **Device indices are system-specific**; check `audio-devices` each time. The 48 kHz probe may be unavailable on some 44.1 kHz endpoints. Avoid the entries labeled `Not To Use` and do not capture a microphone.


## No Windows "Listen to this device" needed — direct in-app relay

This revision fixes a PortAudio routing incompatibility identified on the test PC:

- AVerMedia HDMI input **#14**, Windows WASAPI at **48,000 Hz**
- Default TOPPING USB DAC output **#5**, Windows MME at **44,100 Hz**

PortAudio requires all devices within one duplex stream to share a host API. SwitchAutoPresence now opens separate input/output streams where APIs or sample rates differ, and uses a bounded in-memory converter to resample HDMI 48 kHz audio to the default 44.1 kHz playback device. This does **not** change your Windows default output or use Windows "Listen to this device."

**Test:**

1. In Windows Recording device properties, disable **Listen to this device** for the GC553Pro HDMI input to prevent duplicates.
2. Ensure the Switch 2 is outputting **Stereo** and has an audible game running.
3. Start SwitchAutoPresence in **Automatic** mode with capture device 1.
4. Enter **14** as the AVerMedia HDMI audio input; **leave output index blank** to use the default TOPPING DAC.
5. Audio should start automatically in Automatic mode. The controller should show the selected HDMI endpoint, the actual conversion rate and live RMS/peak levels. If the TOPPING output was set to 48 kHz, both sides should now report 48 kHz.
6. Verify you actually hear the game in your default headphones/speakers. Only after this succeeds should you try Discord application sharing with **Share audio** enabled and ask a remote viewer to confirm the sound.

The audio diagnostic \`audio-test --input N --seconds 8\` now uses each device's default capture sample rate. So #14 uses 48 kHz, while the alternate **HDMI input #9 (DirectSound)** uses 44.1 kHz. If #14 stays around -66 dBFS, try #9 while a game is producing continuous sound. This will help distinguish device-selection/input-volume issues from output routing.

Input and output streams are decoupled with ~70 ms target buffer and a 400 ms maximum capacity. Any periodic clicking, stutter or sync drift still needs hardware testing and follow-up optimization; don't present it as finished or guaranteed.

## Current controls: auto-connect and mute

SwitchAutoPresence now automatically chooses a verified **AVerMedia HDMI** input when Automatic mode starts, without requiring audio-devices, audio-test or a Start Audio button. It remembers your successful input by name/host API across app launches, so it can survive changed Windows device indices. **Not To Use** and microphone inputs are never automatically selected. Audio continues through your Windows default output unless manually overridden.

The **Recording input** and **Playback output** dropdowns let you manually choose another device (immediately restarting the route), and **Rescan** enumerates freshly connected USB endpoints. **Mute** silences local/Discord playback but preserves input capture, metering, and the selected endpoint; **Unmute** restores sound. Mute does not affect your systemwide sound settings or Windows Listen checkbox. In Manual game mode the app still releases capture to Discord by design.

## Discord Direct: video from Discord, local audio from SwitchAutoPresence

The app now has a **Discord direct** mode that never opens the AVerMedia's video handle, keeping native video capture in Discord at full speed. HDMI audio from the capture card is independently monitored by SwitchAutoPresence through the preferred Windows recording endpoint and sent to the default TOPPING DAC. The Discord audience already receives game sound through the card's own audio path. Windows **Listen to this device** should remain off.

- Launch the app and choose **Discord direct** first; wait briefly while the video handle is released.
- Then configure Discord to capture the AVerMedia GC553Pro directly. If video capture reports the device busy, verify the application is in **DIRECT** or **MANUAL** mode (not AUTO).
- **Local headphones:** the in-app HDMI audio monitor connects automatically regardless of Direct or Manual mode. It uses the default Windows output, and the **Mute** button silences its playback.
- **Manual Rich Presence:** choose a game title in SwitchAutoPresence without stopping local audio or claiming the capture-card video.
- **Minimize to tray:** hides the control panel while audio and presence keep running; use the tray menu to restore/exit.
- Verify simultaneous sound while Discord owns video on your specific driver. Audio devices can have exclusive access restrictions; do not promise this combination until hardware confirms it.

