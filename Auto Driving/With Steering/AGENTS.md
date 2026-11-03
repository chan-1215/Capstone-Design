# Servo project instructions

Read README.md and the repository AGENTS.md. Shared gesture code/models live
in ../../Gesture; gesture_adapter.py only imports that worker. Do not duplicate
the recognizer, worker or models here.

Keep Python 3.11, default disarmed startup, detached servo PWM, ownership,
freshness, output/angle limits and stop guards. Recorded pins for this robot:
motor1 left BCM20/21, motor2 right BCM23/24, servo BCM18, A=-105/D=85.
Reconfirm hardware after physical changes; do not infer wheel state from PWM.
History is not current authorization. This restructure has not been Pi-deployed.
Run unit tests here and in ../../Gesture after changing the shared interface.
