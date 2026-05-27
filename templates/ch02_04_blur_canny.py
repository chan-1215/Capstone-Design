from picamera2 import Picamera2
import cv2
import time

cam = Picamera2()
config = cam.create_preview_configuration(
    main={'size': (320, 240), 'format': 'BGR888'}
)
cam.configure(config)
cam.start()

time.sleep(2)
print('Camera is ready.')
print('-'*30)

try:
    if True:
        frame = cam.capture_array()

        # 1) 이미지 자르기
        cropped_frame = frame[120:240, 0:320]

        # 2) 흑백 변환
        gray_frame = cv2.cvtColor(cropped_frame, cv2.COLOR_BGR2GRAY)

        # 3) HSV 변환
        hsv_frame = cv2.cvtColor(cropped_frame, cv2.COLOR_BGR2HSV)

        # 4) 가우시안 블러
        blur_frame = cv2.GaussianBlur(hsv_frame, (5, 5), 0)

        # 5) 캐니 엣지 검출
        edge_frame = cv2.Canny(blur_frame, 50, 150)

        # 결과 저장
        cv2.imwrite('0_original.jpg', frame)
        cv2.imwrite('1_cropped.jpg', cropped_frame)
        cv2.imwrite('2_grayscale.jpg', gray_frame)
        cv2.imwrite('3_hsv_color.jpg', hsv_frame)
        cv2.imwrite('4_blur.jpg', blur_frame)
        cv2.imwrite('5_canny_edge.jpg', edge_frame)
        print('성공! VS Code 왼쪽 탐색기에서 이미지를 확인하세요.')

except KeyboardInterrupt:
    print('Stopped.')
except Exception as err:
    print(f'Error : {err}')
finally:
    cam.stop()
    print('Camera safely terminated.')