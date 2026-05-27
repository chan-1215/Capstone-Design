import os
import time
import cv2
from flask import Flask, render_template, Response
from picamera2 import Picamera2
from motor_module import *

app = Flask(__name__)

SAVE_DIR = 'dataset_images'
os.makedirs(SAVE_DIR, exist_ok=True)

cam = Picamera2()
current_frame = None

def gen_frames():
    global current_frame
    while True:
        frame = cam.capture_array()
        current_frame = frame.copy()
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/action/<cmd>')
def action(cmd):
    speed = 0.7
    if cmd == 'forward':
        move_forward(speed)
    elif cmd == 'backward':
        move_backward(speed)
    elif cmd == 'left':
        move_turn_left(speed)
    elif cmd == 'right':
        move_turn_right(speed)
    elif cmd == 'stop':
        move_stop()
    return "OK"

@app.route('/capture')
def capture():
    global current_frame
    if current_frame is not None:
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        filename = f'img_{timestamp}.jpg'
        filepath = os.path.join(SAVE_DIR, filename)
        cv2.imwrite(filepath, current_frame)
        return f"성공! {filename} 저장 완료"
    return "에러: 카메라 프레임이 없습니다."

def main():
    print("카메라를 초기화합니다...")
    config = cam.create_preview_configuration(
        main={'size': (320, 240), 'format': 'BGR888'}
    )
    cam.configure(config)
    cam.start()
    print("-" * 40)
    print("AI-Rover 웹 서버가 시작되었습니다!")
    print("http://[라즈베리파이 IP주소]:5000")
    print("서버를 종료하려면 Ctrl+C 를 누르세요.")
    print("-" * 40)
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n사용자 요청으로 서버를 종료합니다.")
    finally:
        move_stop()
        cam.stop()
        print("하드웨어 자원이 안전하게 해제되었습니다.")

if __name__ == '__main__':
    main()