"""Dispatch decisions to a real or virtual motor module."""

from .drive_policy import DriveCommand


def apply_decision(motor, decision):
    actions = {
        DriveCommand.STOP: lambda: motor.move_stop(),
        DriveCommand.FORWARD: lambda: motor.move_forward(decision.speed),
        DriveCommand.CURVE_LEFT: lambda: motor.move_curve_left(decision.speed),
        DriveCommand.CURVE_RIGHT: lambda: motor.move_curve_right(decision.speed),
    }
    actions[decision.command]()
