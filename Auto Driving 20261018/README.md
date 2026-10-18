# Auto Driving 20261018

Python 3.11 snapshot of the NEW track robot, saved before moving from a borrowed
SD card to the owner's new OS installation. This is NOT the older white-paper
road controller in `Auto Driving/` or the teammate snapshot in `Auto Driving@/`.

## Entry Point

`track_web.py` is the Flask application. Without flags it shows camera/vision
only. Manual control and the autonomous panel are deliberately opt-in:

```bash
cd "$HOME/Capstone-Design/Auto Driving 20261018"
./.venv/bin/python -B track_web.py --manual --motor-wiring-confirmed --autonomous --port 5001
```

Open `http://<new-pi-ip>:5001/`. Starting the server does NOT arm or move motors.
The `--motor-wiring-confirmed` flag must only be used after checking the wiring
on the actual reassembled robot. A fresh straight-path reference is needed for
autonomous driving after every restart. Bare IDE "Run Python File" launches the
camera-only mode; missing driving panels do not mean this is an old file.

The earlier `/home/pi/steering_robot_drive_eval_20261012/.venv/bin/python` path
was a shared interpreter on the old SD, NOT a requirement of this source tree.
On the new SD use this folder's `.venv`. Do not copy an old venv or replace the
OS Python: native packages and script shebangs must be installed afresh.

## Included

- Current Pi runtime, Flask HTML/JS/icons, synthetic regression tests.
- OpenCV yellow-boundary/white-dash/road segmentation and guarded path tracking.
- Manual W/A/S/D, independent motor trims, opt-in P/heading autonomous pilot.
- Curve-output reduction/recovery, finite trial and opt-in continuous mode.
- Photo/paired-video capture under `captures/`, which is excluded from Git.
- Preserved gesture source and KNN model under `gesture_reference/`; NOT yet
  connected to this Flask UI or to motor decisions.
- Exact Pi source SHA256s in `SOURCE_MANIFEST.json` and installed-package
  inventory in `environment/installed-pi311.json`.

Runtime flow: camera_source -> track_web.Monitor -> track_vision -> lane_path ->
autonomous.AutoPilot -> manual_drive. GPIO initialization only happens in the
explicit hardware mode. Read HANDOFF.md for physical limits and known failures.

## Restore On The New SD

Use a Raspberry Pi OS **64-bit** installation with working camera support.
The dependency locks target ARM64 Python3.11 and glibc2.36+ (Bookworm or newer);
they are not Windows/32-bit/general-purpose dependency locks.
This procedure is for the owner's new SD, not permission to erase the borrowed SD.
Enable SSH, configure networking, and confirm `uname -m` is `aarch64`.

1. Install OS tools/libraries. Do not install Python3.13 camera bindings into
   the Python3.11 venv:

```bash
sudo apt update
sudo apt install git curl rpicam-apps libgl1 libportaudio2
```

2. Install uv using its [official instructions](https://docs.astral.sh/uv/getting-started/installation/).
   The official Linux installer is:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart the terminal if `uv` is not on PATH. Clone the repository and create a
NEW Python3.11 environment (see [uv Python setup](https://docs.astral.sh/uv/guides/install-python/)):

```bash
git clone https://github.com/chan-1215/Capstone-Design.git
cd "Capstone-Design/Auto Driving 20261018"
uv python install 3.11
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-core-pi311.txt
```

For future gesture work install the compatible, separate gesture environment
lock instead (it includes the core packages):

```bash
uv pip install --python .venv/bin/python -r requirements-gesture-pi311.txt
```

If OpenCV reports missing `libglib-2.0.so.0`, install the matching OS library:
Bookworm `libglib2.0-0`, Trixie `libglib2.0-0t64`. Do not install opencv-python
alongside opencv-contrib-python: they overwrite the same cv2 namespace.
The exact package list from the old SD is an INVENTORY, not an install lock:
it contained duplicate OpenCV distributions and an incompatible JAX/NumPy pair.
Fresh lock resolution is not proof of a successful fresh-SD hardware setup.

3. Verify without motors first:

```bash
./.venv/bin/python -c "import sys,cv2,numpy,flask,gpiozero,lgpio; print(sys.version); print(cv2.__version__)"
./.venv/bin/python -B -m unittest discover -p 'test_*.py'
rpicam-hello --list-cameras
./.venv/bin/python -B track_web.py --port 5001
```

For gesture dependencies only: `./.venv/bin/python -c "import mediapipe; print(mediapipe.__version__)"`.
When camera input works, stop the camera-only server with Ctrl+C before opening
hardware mode. No two camera servers may run together. New GPIO permissions,
physical steering centre, battery, motor directions and stop operation still
need verification before any powered-forward test.

## Camera And Defaults

The old SD's Picamera2 bindings exist only for OS Python3.13. In Python3.11,
camera_source falls back to the [official rpicam-vid application](https://www.raspberrypi.com/documentation/computers/camera_software.html),
quality95 MJPEG decoded by OpenCV. Flask/perception/control stay in3.11. The
latest JPEG replaces old application frames; no cached-frame driving fallback
exists. JPEG changes pixels, so validate masks on the new track/camera setup.

Capture defaults960x720, analysis640x480, requested30FPS, rotation180. Current
camera: OV5647 Rev1.3. Do NOT use the old IMX219 `--sensor-size 1640 1232` override.
Manual output defaults0.30, pilot base0.26, curve_scale0.75. Outputs are PWM
fractions, not measured physical speeds. These values are not universal motor
calibrations. See HANDOFF.md before changing steering or safety limits.

## Evidence And Exclusions

Before this snapshot,135 tests passed on PC and Pi Python3.11; a temporary Pi
Flask test at960x720 measured30.03 completedFPS on a stationary floor scene.
DC outputs stayed0 and servo PWM stayed off. This does NOT prove track accuracy,
a complete autonomous lap, gesture integration or fresh-OS compatibility.

Raw recordings, run logs, previous source backups, whole virtualenvs, OS images,
credentials, VS Code data and the unrelated smart_factory project are not in Git.
The chronological original README/AGENTS are preserved under history/ for review;
their old launch commands are historical, not instructions for the new SD.
