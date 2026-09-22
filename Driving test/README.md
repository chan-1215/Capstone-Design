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
