"""Small runtime stabilizers for learned lane following."""


MIN_VISIBLE_PWM = 0.32
VISION_TRIM_GAIN = 0.0022
MAX_VISION_TRIM = 0.18


def clamp(value, low, high):
    return max(low, min(high, value))


def stabilize_learned_pwm(left_pwm, right_pwm, lane_error, lane_visible):
    if not lane_visible:
        return left_pwm, right_pwm

    average_pwm = max(MIN_VISIBLE_PWM, (left_pwm + right_pwm) / 2.0)
    learned_steering = right_pwm - left_pwm
    vision_trim = clamp(
        lane_error * VISION_TRIM_GAIN,
        -MAX_VISION_TRIM,
        MAX_VISION_TRIM,
    )
    steering = learned_steering + vision_trim
    return (
        clamp(average_pwm - steering / 2.0, 0.0, 0.85),
        clamp(average_pwm + steering / 2.0, 0.0, 0.85),
    )
