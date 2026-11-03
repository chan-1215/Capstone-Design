# 제스처 인식

소스·모델·PC 실행·주행 연결을 [Gesture](../Gesture/README.md)에 통합했습니다.

Lee에서 시작한 KNN과 손 좌표 보조 함수는 공통 모듈로 유지합니다.
PC의 사람 윤곽 검출, 카메라 중복 실행 방지와 주행용 최신 프레임 worker를 함께 관리합니다.
모델은 `Gesture/models`에만 있으며 Flask도 이 모델과 구현을 참조합니다.
수집·학습의 이전 실험은 `Gesture/experiments`, 출처는 `Gesture/history`에 있습니다.

[전체 이동 내역](repository-map.md)
