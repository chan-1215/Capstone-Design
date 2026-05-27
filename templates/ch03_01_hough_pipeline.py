from picamera2 import Picamera2
import cv2
import numpy as np
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
        blur_frame = cv2.GaussianBlur(gray_frame, (5, 5), 0)

        # 5) 캐니 엣지 검출
        edge_frame = cv2.Canny(blur_frame, 50, 150)

        # 6) ROI 마스킹
        mask = np.zeros_like(edge_frame)
        polygon = np.array([[(0, 120), (100, 40), (220, 40), (320, 120)]], np.int32)
        cv2.fillPoly(mask, polygon, 255)
        masked_edge = cv2.bitwise_and(edge_frame, mask)

        # 7) Bird's Eye View 변환
        src_pts = np.float32([(0, 120), (100, 40), (220, 40), (320, 120)])
        dst_pts = np.float32([(0, 120), (0, 0), (320, 0), (320, 120)])
        matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        birdseye_frame = cv2.warpPerspective(masked_edge, matrix, (320, 120))

        # 8) 허프 변환
        lines = cv2.HoughLinesP(birdseye_frame, 1, np.pi/180, 30,
                                minLineLength=30, maxLineGap=20)

        line_result = cv2.warpPerspective(cropped_frame, matrix, (320, 120))

        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                cv2.line(line_result, (x1, y1), (x2, y2), (0, 0, 255), 2)

        # 결과 저장
        cv2.imwrite('8_hough_result.jpg', line_result)
        print('성공! 8_hough_result.jpg 파일을 확인하세요.')

except KeyboardInterrupt:
    print('Stopped.')
except Exception as err:
    print(f'Error : {err}')
finally:
    cam.stop()
    print('Camera safely terminated.')