import time
import cv2
import numpy as np
from picamera2 import Picamera2

# [Optional] Import LCD library (Uncomment if you use I2C LCD 1602)
from RPLCD.i2c import CharLCD
lcd = CharLCD('PCF8574', 0x27) # Change 0x27 to your LCD address

# ========================================================
# [Pre-defined Functions] Merge multiple lines into two representative lanes
# ========================================================
def make_coordinates(image_height, line_parameters):
    """Convert slope and intercept back into image pixel coordinates (x1, y1, x2, y2)"""
    slope, intercept = line_parameters
    y1 = image_height  # Bottom of the image (120)
    y2 = 40  # Slightly below center (Top of the trapezoid ROI)
    x1 = int((y1 - intercept) / slope)
    x2 = int((y2 - intercept) / slope)
    return np.array([x1, y1, x2, y2])

def average_slope_intercept(image_height, lines):
    """Analyze slopes of lines and merge them into single left and right representative lines"""
    left_fit = []
    right_fit = []

    if lines is None:
        return None, None

    for line in lines:
        x1, y1, x2, y2 = line[0]
        if x1 == x2:  # Prevent vertical line division by zero error
            continue

        parameters = np.polyfit((x1, x2), (y1, y2), 1)
        slope = parameters[0]
        intercept = parameters[1]

        # Filter out horizontal lines (near slope 0) as noise
        if slope < -0.3:
            left_fit.append((slope, intercept))
        elif slope > 0.3:
            right_fit.append((slope, intercept))

    left_line = None
    right_line = None

    if len(left_fit) > 0:
        left_fit_average = np.average(left_fit, axis=0)
        left_line = make_coordinates(image_height, left_fit_average)

    if len(right_fit) > 0:
        right_fit_average = np.average(right_fit, axis=0)
        right_line = make_coordinates(image_height, right_fit_average)

    return left_line, right_line


# ========================================================
# [Main Execution] AI-Rover Vision Pipeline
# ========================================================

# 1. Initialize and configure Camera object
cam = Picamera2()
config = cam.create_preview_configuration(
    main={"size": (320, 240), "format": "BGR888"}
)
cam.configure(config)
cam.start()
time.sleep(2)
print("Camera is ready.")
print("-" * 30)

try:
    # while True:                         # VNC environment (For real-time video)
    while True:  # VS Code SSH environment (For single frame test)

        # 4. Capture the latest frame
        frame = cam.capture_array()

        # --- [Autonomous Driving Vision Algorithm Steps 1~10] ---

        # 1) Image Cropping (y-axis 120~240)
        cropped_frame = frame[120:240, 0:320]

        # 2) Convert to Grayscale
        gray_frame = cv2.cvtColor(cropped_frame, cv2.COLOR_BGR2GRAY)

        # ========================================================
        # [NEW LOGIC] Crosswalk Detection (Detect Black on White Floor)
        # ========================================================
        # Threshold to find black pixels (Pixel values close to 0)
        # On a white floor, black crosswalk lines will have very low brightness.
        _, black_mask = cv2.threshold(gray_frame, 50, 255, cv2.THRESH_BINARY_INV)

        # Calculate how many black pixels are in the center driving zone
        # We check the middle 60% of the cropped frame width
        center_roi = black_mask[:, 64:256]
        black_pixel_count = np.sum(center_roi == 255)

        # If there are too many black pixels, assume it's a crosswalk
        if black_pixel_count > 8000:  # Adjust this threshold based on tests
            print("[STOP] Crosswalk Detected! Stopping RC Car.")

            # LCD Display: Crosswalk Stop
            lcd.clear()
            lcd.write_string("CROSSWALK DETECTED\nSTATUS: STOP")

            # Insert your motor stop code here (e.g., motor.stop())
            time.sleep(0.1)
            
            continue  # Skip the rest of the lane detection loop

        # 4) Noise Reduction (Gaussian Blur)
        blur_frame = cv2.GaussianBlur(gray_frame, (5, 5), 0)

        # 5) Canny Edge Detection
        edge_frame = cv2.Canny(blur_frame, 50, 150)

        # 6) Region of Interest (ROI) Masking
        mask = np.zeros_like(edge_frame)
        polygon = np.array(
            [[(0, 120), (100, 40), (220, 40), (320, 120)]], np.int32
        )
        cv2.fillPoly(mask, polygon, 255)
        masked_edge = cv2.bitwise_and(edge_frame, mask)

        # 7) Bird's Eye View Perspective Transform
        src_pts = np.float32([(0, 120), (100, 40), (220, 40), (320, 120)])
        dst_pts = np.float32([(0, 120), (0, 0), (320, 0), (320, 120)])
        matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        birdseye_frame = cv2.warpPerspective(masked_edge, matrix, (320, 120))

        # 8) Lane Detection (Hough Transform) and Merging
        lines = cv2.HoughLinesP(
            birdseye_frame,
            1,
            np.pi / 180,
            30,
            minLineLength=30,
            maxLineGap=20,
        )
        image_height = cropped_frame.shape[0]  # Cropped height: 120
        left_line, right_line = average_slope_intercept(image_height, lines)

        # Background for visualization (Perspective transformed color image)
        line_result = cv2.warpPerspective(cropped_frame, matrix, (320, 120))

        # 9) Calculate Lane Center and Steering Error
        camera_center = 160  # Center coordinate of 320px resolution
        error = 0  # Initialize error

        if left_line is not None and right_line is not None:
            # Both lanes detected (Normal straight section)
            cv2.line(
                line_result,
                (left_line[0], left_line[1]),
                (left_line[2], left_line[3]),
                (255, 0, 0),
                5,
            )
            cv2.line(
                line_result,
                (right_line[0], right_line[1]),
                (right_line[2], right_line[3]),
                (255, 0, 0),
                5,
            )

            # Average of bottom x-coordinates of left and right lines
            lane_center = (left_line[0] + right_line[0]) // 2
            error = camera_center - lane_center

            # Draw AI-Rover target center point (Green line) on screen
            cv2.line(
                line_result, (lane_center, 120), (lane_center, 100), (0, 255, 0), 5
          )
            
        elif left_line is not None and right_line is None:
            # Only left lane detected (Sharp right curve)
            cv2.line(
                line_result,
                (left_line[0], left_line[1]),
                (left_line[2], left_line[3]),
                (255, 0, 0),
                5,
            )
            error = -50  # Assign large negative error for right turn

        elif right_line is not None and left_line is None:
            # Only right lane detected (Sharp left curve)
            cv2.line(
                line_result,
                (right_line[0], right_line[1]),
                (right_line[2], right_line[3]),
                (255, 0, 0),
                5,
            )
            error = 50  # Assign large positive error for left turn

        else:
            # No lanes detected
            error = 0

        # 10) Steering Logic Decision and Output
        print(f"Current Steering Error: {error}")
        if abs(error) < 15:
            print("Lane Centered -> Go Forward")
        elif error < 0:
            print("Robot drifted Left -> Turn Right")
        elif error > 0:
            print("Robot drifted Right -> Turn Left")

        # ========================================================
        # [NEW LOGIC] Display Steering Value on LCD
        # ========================================================
        print(f"Steering Error: {error}")

        # Update LCD with current steering error
        lcd.clear()
        lcd.write_string(f"Steering : {error}")


        cv2.imwrite("test_result.jpg", line_result)
        # Insert your motor steering code here using the 'error' value

        # Small delay to prevent CPU from overloading
        time.sleep(0.03)

except KeyboardInterrupt:
    print("Stopped. Ctrl+C pressed.")
except Exception as err:
    print(f"Error : {err}")
finally:
    # 6. Safe resource release
    cv2.destroyAllWindows()
    cam.stop()
    lcd.clear()
    print("Camera safely terminated.")