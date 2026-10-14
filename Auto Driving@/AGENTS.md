# Agent instructions for Auto Driving@

Read `README.md` and `HANDOFF.md` before editing or operating this project.
This is the 2026-10-14 rear-wheel calibration snapshot, separate from `Auto Driving/`, `Lee/`,
`Driving test/`, and `Dataset Project/`. Do not modify those folders as a
side effect of work here. Root `AGENTS.md` also applies.

Do not infer physical wiring or servo neutral from code constants alone.
Do not run motor/servo commands without the user's current confirmation that
the robot is positioned safely and they can stop it immediately. Never use
an offline score as proof of safe autonomous motion. Keep raw recordings,
private data, credentials, and generated browser artifacts out of Git.

The runtime entry point is `road_drive_web.py`; `road_vision.py` provides
image measurements. Gesture output is display-only and manual-driving models
are not active in the motor controller. Preserve those boundaries unless
the user explicitly asks to change them. Add focused tests for control or
vision edits and report whether validation was PC-only or on the Pi.

Read `CHANGES_20261014.md` for motor formulas and unresolved observations.
Motor 1 is currently left rear and motor 2 right rear, based on the owner's
latest correction, not an independently verified wheel-by-wheel test.
The PWM status fields report commands, not measured RPM. The manual servo
sign correction is not applied to automatic steering. The imported Pi source
has `MAX_CORNER_SECONDS = 0`; do not silently reinterpret it as a validated value.
