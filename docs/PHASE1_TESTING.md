# Phase 1 — Windows capture-card testing

The project is currently a **read-only diagnostic**. It does not detect games or update Discord yet.

## Initial setup

Install Python 3.11+ on Windows, including the Python launcher (py). Open **PowerShell** in the cloned repository:

~~~powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[windows]"
~~~

If PowerShell blocks activation, use Command Prompt or run .\.venv\Scripts\python.exe directly; you do **not** need to weaken your execution policy.

## Test A — Identify AVerMedia device

Keep the console connected and powered on:

~~~powershell
switchautopresence devices
~~~

Look for AVerMedia or Live Gamer (the exact device name may vary) and note its [number]. DirectShow enumeration does not guarantee the same index in every backend.

## Test B — Can we read frames?

First test **without Discord streaming or VideoGameCapture reading the capture card**. Replace 0 with the device index from Test A:

~~~powershell
switchautopresence probe --device 0 --seconds 8
~~~

Look for Status: ok, a nonzero frame count, and dimensions. No screenshots or recordings are saved. A black/sleeping console might return dark_frames or no_frames.

If that fails, try the alternate backend:

~~~powershell
switchautopresence probe --device 0 --backend msmf --seconds 8
~~~

An OpenCV device index can differ from the list returned by DirectShow enumeration. If it appears wrong, try another index **one at a time**, with other capture clients closed.

## Test C — Does it coexist with Discord streaming?

Only after Test B works:

1. Start your usual Switch capture preview or Discord stream.
2. Confirm Discord still shows live gameplay.
3. Run the same 8-second probe again.
4. Check that Discord is still showing frames after the probe.
5. Record the **text status**, backend, resolution, and whether the stream was interrupted. Do not upload screenshots.

An unavailable result during streaming may indicate **exclusive device access**. In that case, we should use a shared pipeline or other safe integration rather than repeatedly forcing access.

> **Warning:** The probe opens a second capture handle. Drivers may forbid shared access, so running Test C could briefly interrupt an existing stream. Only do it when interruption is acceptable.

## What to report

- Windows 10 or 11
- Device name listed by devices
- Whether dshow or msmf worked
- Probe status: ok, unavailable, dark_frames, or no_frames
- Whether Discord/VideoGameCapture was active and if its feed was interrupted

Do not share personal paths, captures, or authentication tokens.
