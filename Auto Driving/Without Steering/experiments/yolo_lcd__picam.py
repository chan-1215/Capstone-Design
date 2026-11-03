import cv2
import time
from ultralytics import YOLO
from smbus2 import SMBus
from RPLCD.i2c import CharLCD
from picamera2 import Picamera2

# --- 1. I2C LCD Initialization ---
try:
    lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=1, cols=16, rows=2)
    lcd.clear()
    lcd.write_string("AI Rover Ready")
    print("✨ LCD Init Success!")
except Exception as e:
    print(f"❌ LCD Init Failed: {e}")

# --- 2. Load YOLOv11 Model ---
print("🧠 Loading YOLOv11 Model...")
model = YOLO('yolo11n.pt')  
print("✅ Model Loaded Successfully!")

# --- 3. Optimized Picamera2 Configuration ---
print("📷 Initializing Low-Resolution High-FPS Camera Stream...")
try:
    picam = Picamera2()
    
    # 🛠️ [OPTIMIZATION 1] Downscale resolution to 320x240 to reduce pixel data by 75%
    # If it's still lagging, change (320, 240) to (160, 120) below for extreme speed.
    cam_config = picam.create_video_configuration(main={"size": (320, 240), "format": "RGB888"})
    
    picam.configure(cam_config)
    picam.start()
    print("🚀 Turbo Camera Stream Started!")
except Exception as e:
    print(f"🚨 Critical Error: {e}")
    exit()

time.sleep(1.0)
last_displayed_text = "" 

# Variables to calculate real-time FPS
prev_time = 0
fps_text = "FPS: 0"

try:
    print("▶️ Starting AI Object Detection Loop... (Press Ctrl+C to Quit)")
    while True:
        # Grab the small, lightweight frame
        frame_raw = picam.capture_array()
        frame = cv2.cvtColor(frame_raw, cv2.COLOR_RGB2BGR)
        
        if frame is None:
            continue

        # Calculate FPS (Frame Per Second)
        current_time = time.time()
        fps = 1 / (current_time - prev_time) if prev_time != 0 else 0
        prev_time = current_time
        fps_text = f"FPS: {fps:.1f}"

        # 🛠️ [OPTIMIZATION 2] Advanced AI Inference Speed-Up Options
        # - imgsz=320: Forces the AI to process at 320px scale instead of default 640px.
        # - half=True: Uses FP16 precision instead of FP32 (significantly reduces CPU overhead).
        results = model(frame, verbose=False, imgsz=320, half=True)
        
        detected_object = "Scanning..." 
        highest_conf = 0.0

        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = model.names[cls_id]
                conf = float(box.conf[0])

                if conf > highest_conf and conf > 0.45: # Adjusted threshold to 45% for faster capture
                    highest_conf = conf
                    detected_object = cls_name

        # --- 4. I2C LCD Non-blocking Update ---
        if detected_object != last_displayed_text:
            lcd.clear()
            lcd.cursor_pos = (0, 0)
            lcd.write_string("Detected:")
            
            lcd.cursor_pos = (1, 0)
            lcd.write_string(detected_object.upper()) 
            
            print(f"📺 LCD Updated ➔ [{detected_object.upper()}] ({fps_text})")
            last_displayed_text = detected_object

        # --- 5. Draw Debug Information on Frame ---
        # Display the real-time calculated FPS on the screen
        cv2.putText(frame, fps_text, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        cv2.putText(frame, f"AI: {detected_object}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        cv2.imshow("AI Rover Vision", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    print("\n⚠️ Program interrupted by user.")

finally:
    try:
        picam.stop()
        print("📷 Camera stream stopped.")
    except:
        pass
    cv2.destroyAllWindows()
    try:
        lcd.clear()
        lcd.write_string("System Stopped")
    except:
        pass
    print("🏁 System shutdown complete safely.")