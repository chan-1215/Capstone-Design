# Dated Pi snapshot: 2026-10-18

Read README.md and HANDOFF.md before modifying or running hardware.

- This folder is the NEW black/yellow/white track project, copied from the
  deployed Pi, NOT Auto Driving/ or Auto Driving@/. Do not merge old controllers.
- Flask, OpenCV, GPIO and future MediaPipe integration MUST use Python 3.11.
  Install a fresh local .venv on the owner's NEW SD. The old external interpreter
  directory is historical; no dependence on that old folder is required here.
- Start camera-only first. Hardware is opt-in. Never start motion to validate a
  migration, upload, unit test or server startup. New readiness is required.
- motor1 LEFT BCM20/21; motor2 RIGHT BCM23/24; forward multiplier +1 for BOTH.
  These were physically confirmed for this new robot and supersede old wiring
  polarity notes in root handoff files. Servo BCM18, A=-105, D=85. Values are
  servo command units, not measured wheel angles. Reconfirm after reassembly.
- Keep disarmed startup, detached servo PWM, camera/path freshness, ownership,
  browser lease, hardware deadman, bounded angle/rate and all stop guards.
  Continuous mode removes only the elapsed trial deadline, not these guards.
- Keep defaults manual=.30, pilot=.26, curve_scale=.75. Never silently force .26
  onto manual startup or restore the historical near-stalling curve_scale=.55.
- Camera source uses Picamera2 when available and OS rpicam-vid otherwise.
  The 3.11 venv must NOT import system3.13 native libcamera binaries via PYTHONPATH.
- Current camera is OV5647 Rev1.3, NOT IMX219. Do not force IMX219 sensor mode.
  Capture960x720, analysis640x480, requested30FPS; no speed/accuracy guarantee.
- gesture_reference/ is preserved, NOT integrated into track_web.py. Do not
  claim gesture-driven motor control. Do not modify its model/source casually.
- SOURCE_MANIFEST.json records exact original source/model hashes. New docs,
  launchers and dependency files are migration additions, not Pi-proven changes.
- Do not stage raw captures, credentials, venvs, smart_factory, other people's
  edits or any other project. Do not delete/reformat the borrowed SD.
- Run `python -B -m unittest discover -p 'test_*.py'` in this folder after edits.
  Historical notes under history/ do not override this file or HANDOFF.md.
