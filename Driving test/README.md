# Driving test

OpenCV filtering + P-control road driving test code.

This folder is isolated from the existing project code. It does not modify
`Lee`, `Dataset Project`, dataset, model, gesture, ultrasonic, LCD, or IMU code.

## What it does

- Reads camera frames with OpenCV or the existing Lee camera adapter.
- Detects a white lane/road guide on a dark road.
- Also handles the opposite case by inverting bright-road/dark-line frames.
- Calculates lane center error.
- Uses P-control to create left/right motor PWM.
- Drives only forward; if a side speed becomes too small, that side stops.
- Stops when the lane is lost for several frames.

## Files

- `motor_module.py`: GPIO pin setup, motor objects, movement functions.
- `motor_test_pdf.py`: motor test runner that imports `motor_module.py`.
- `road_drive_p_control.py`: OpenCV lane detection + P-control road driving.
- `dataset_model.py`: dataset-trained `.npz` model loader and preprocessing.
- `road_drive_dataset.py`: dataset-trained road driving using `motor_module.py`.

This matches the professor PDF structure: reusable motor code is separated from
the test or driving program that calls it.

## First motor test

Use this before camera or road driving. Keep the robot lifted from the floor.

```bash
cd ~/Capstone-Design/Driving\ test
python3 motor_test_pdf.py each --speed 0.35 --duration 1.0
```

If one motor spins backward, swap that motor's pin pair:

```bash
python3 motor_test_pdf.py each --motor3-pins 27,22
```

To find the minimum speed where the wheels start turning:

```bash
python3 motor_test_pdf.py ramp --duration 2.0 --ramp-step 0.1
```

## First camera-only test

Use this before connecting motors:

```bash
cd ~/Capstone-Design/Driving\ test
python3 road_drive_p_control.py --dry-run --camera opencv --preview
```

If the Pi camera is not available through OpenCV, use the existing camera module:

```bash
python3 road_drive_p_control.py --dry-run --camera lee --preview
```

## Dataset-Trained Driving

The dataset is applied through the trained model files in `models/`, not by
loading raw dataset images during driving.

```bash
cd ~/Capstone-Design/Driving\ test
python3 road_drive_dataset.py --dry-run --camera rpicam --duration 10
```

First real driving test:

```bash
python3 road_drive_dataset.py --camera rpicam --duration 20 --max-pwm 0.45
```

To watch the camera and dataset-model decisions while driving, use the combined
Flask program instead of running `road_drive_web.py` and
`road_drive_dataset.py` at the same time:

```bash
python3 road_drive_dataset_web.py --camera rpicam --rotation 180
```

Open `http://<PI_IP>:5000`, confirm that the safety state is `driveable`, then
press `Start driving`. The same camera frames are used for the web stream and
model inference, so there is no camera conflict. Closing the dashboard or
losing its status connection for two seconds stops the motors.

The `Model` and `OpenCV` views use the same camera frames. The OpenCV view
shows the earlier P-control lane detector's center lines and threshold mask;
it is a visual diagnostic and does not change the dataset-model driving command.
Its detection mode and threshold can be adjusted with `--lane-mode` and
`--lane-threshold`. The diagnostic view updates at 5 FPS by default to limit
load on the Pi; use `--lane-fps` to change it.

Video turn assistance supplements the dataset model with the
direction of diagonal road markings seen in the manual-driving recording.
Three consecutive OpenCV observations are required before this cue can request
a turn. If a strong model command and a confirmed visual cue disagree, driving
stops and must be restarted manually. The existing driveability safety check,
four-second turn timeout, and browser heartbeat still apply. This is an
experimental aid, not a model trained from the screen recording; it requires
supervised low-speed testing on the actual track. `Line heading` is positive
for a right bend and negative for a left bend; `Turn assist` shows the
confirmed direction. The assist is on by default; `--no-video-turn-assist`
turns it off for comparison. The dashboard reports `off` when disabled.

Autonomous driving requires a visible road line within 40 pixels of the image
center and a ready vision gate before Start is accepted. The default surface
profile (`--road-surface white`) checks for the white paper track independently
of line detection. A brief surface or lane uncertainty pauses the motors, then
automatically resumes after three clear observations. For the first second
after resuming, the forward base PWM and turn speed are capped at 0.34
(`--resume-seconds`, `--resume-speed`). Two definite off-track observations,
ten consecutive uncertain surface observations, or ten lost-line observations
stop driving and require another manual Start. At the default 5 FPS diagnostic
rate, ten observations take about two seconds. These thresholds were selected
from a screen recording and still require supervised validation with raw Pi
camera frames. The white profile admits the slight tint seen in the Pi camera
while excluding brighter tan floors by requiring near-neutral LAB color.
At a sharp bend, three matching observations with white track close to the
camera and clearly more white track on one far side permit a limited pivot
toward that side. This corner recovery never commands forward PWM, stops when
the near track disappears or the safety model becomes unsafe, and latches a
stop after `--max-turn-seconds`. Start can be pressed while this confirmed
corner state is visible, even if the lane-center error exceeds 40 pixels.
A centered pair of road borders
suppresses model-only pivot turns, and a model-only pivot requires three
consecutive turn commands. These checks do not affect manual driving.

With both road borders visible, forward driving now applies a small OpenCV
P-correction to the left/right motor PWM instead of holding a fixed ratio.
The defaults are `--lane-kp 0.0025` PWM per pixel and
`--lane-max-correction 0.07`. The dashboard displays the road-surface fractions
and vision-gate state alongside the OpenCV view. The `black` road-surface
profile is experimental and is not calibrated for the white-paper track.

To test the assisted mode, start the combined dashboard with:

```bash
python3 road_drive_dataset_web.py --camera rpicam --rotation 180
```

The motor remains stopped until `Start driving` is pressed. Keep the first
track test supervised and use the dashboard `Stop` button when the visual cue
or model disagrees with the visible road.

The dashboard also provides `Forward`, `Backward`, `Left`, and `Right` manual
controls. A manual button drives only while it is held; releasing it, changing
browser tabs, or losing command refreshes for 0.6 seconds stops the motors.
Manual mode disables autonomous driving and uses direct PWM `0.38` by default.
Adjust it at startup with `--manual-speed`, for example `--manual-speed 0.30`.
The final motor output applies a physical straight-line calibration of `1.00`
on the left and `0.90` on the right. Override these with `--left-motor-scale`
and `--right-motor-scale` after repeating a straight five-second test.

Manual turns use the rear inside wheel as an active brake. For a right turn,
both left motors move forward, the right-front motor stops, and the right-rear
motor reverses. A left turn mirrors this behavior. Manual and autonomous turns
use `--turn-speed` (default direct PWM `0.48`); `--manual-speed` controls only
manual forward and backward movement.

The same hold-to-run manual controls are available from the keyboard: `W`
forward, `S` backward, `A` left, and `D` right. Releasing the active key or
moving away from the browser window stops the motors.

In autonomous mode, a steering difference of at least `0.10` for three frames stops forward
motion and uses the same rear-inside-wheel turn pattern. It resumes equal-speed
forward motion after the difference stays at or below `0.04` for four frames.
Three consecutive opposite turn signals reverse the turn direction.
An unsafe camera frame stops the motors; a turn lasting over four seconds also
stops autonomous driving until it is started again. The turn thresholds, speed,
and timeout can be adjusted with `--turn-enter-threshold`,
`--turn-exit-threshold`, `--turn-speed`, and `--max-turn-seconds`.
Autonomous forward driving uses `--speed-scale 1.07`, a minimum PWM of `0.34`,
and a maximum PWM of `0.58` by default.

This uses the current motor calibration in `motor_module.py`, including:

```text
motor1 trim = 0.75
motor2 trim = 1.00
motor3 trim = 1.00
motor4 trim = 1.00
```

## First motor driving test

Keep the robot lifted from the floor first.

```bash
python3 road_drive_p_control.py --duration 10 --base-speed 0.22 --kp 0.0035
```

## Web lane monitor

Install Flask once on the Raspberry Pi:

```bash
sudo apt update
sudo apt install -y python3-flask
```

Start the camera and lane-recognition dashboard without driving first:

```bash
cd ~/Capstone-Design/Driving\ test
python3 road_drive_web.py --camera rpicam --dry-run
```

If the camera is mounted upside down, rotate the frame before lane detection:

```bash
python3 road_drive_web.py --camera rpicam --rotation 180 --dry-run
```

Open `http://<PI_IP>:5000` from a computer on the same network. The page shows
the camera frame, threshold mask, detected lane center, P-control error, and
planned left/right PWM.

After checking recognition, stop the dry-run process and enable real motor
control. The motors remain stopped until `Start driving` is pressed in the web
page. Driving is rejected while no lane is visible, and the robot stops if the
dashboard status connection is lost for more than two seconds.

```bash
python3 road_drive_web.py --camera rpicam
```

If steering reacts backward, do not edit code first. Run:

```bash
python3 road_drive_p_control.py --duration 10 --invert-steering
```

If motor forward/backward pin order is wrong, swap that motor pin pair in the
command line, for example:

```bash
python3 road_drive_p_control.py --left-front-pins 27,22
```

## Default motor GPIO

Defaults follow the professor PDF motor table:

- motor1 / right side: `26,19`
- motor2 / right side: `20,21`
- motor3 / left side: `22,27`
- motor4 / left side: `24,23`

For the new robot, check these with a motor-only test before road driving.
