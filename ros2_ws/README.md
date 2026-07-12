# ros2 구조

## waste_detector 패키지 생성

*기능 단위로 패키지 묶어 구성*
```
ros2_ws/src/
┗ waste_detector/           # 패키지 1 (비전 파이프라인)
  ┣ waste_detector/
  ┃  ┣ __init__.py
  ┃  ┣ camera_node.py       # 노드 1 (카메라 노드)
  ┃  ┗ detector_node.py     # 노드 2 (객체 탐지 노드)
  ┗ setup.py, package.xml, setup.cfg ... etc
```

*의존성:*
- ROS2 : rclpy, sensor_msgs, vision_msgs
    - 이미지 : sensor_msgs/msg/Image
    - 2D 객체 탐지 결과 전달 : Detection2DArray
        (BBox + 클래스 + 신뢰도 전달)
- Python : ultralytics, opencv, numpy

*인터페이스 구조:*
| 토픽 | 메시지 타입 | 발행자 | 구독자 |
|---|---|---|---|
| `/camera/image_raw` | `sensor_msgs/Image` | `camera_node` | `detector_node` |
| `/detection_results` | `vision_msgs/Detection2DArray` | `detector_node` | 나중 부분(`robot_control`) |


### 각 노드 구성
1. camera_node

*카메라 영상을 구독하여 ROS2 토픽으로 발행하는 노드*

*역할:*
- USB 카메라 또는 웹캠에서 영상 프레임을 읽음
- OpenCV 이미지를 ROS2 Image 메시지로 변환
- `/camera/image_raw` 토픽으로 발행
    
*파라미터:*
- `~camera_id`: 카메라 인덱스 (기본값: 0)
- `~frame_width`: 프레임 너비 (기본값: 640)
- `~frame_height`: 프레임 높이 (기본값: 640)
- `~fps`: 초당 프레임 수 (기본값: 30)

*흐름:*
a. cv2.VideoCapture.read() : 카메라에서 프레임 읽기
b. Image() 객체 생성 : ROS2 메시지 구조 만들기
c. header, width, height 등 설정 : 메시지에 정보 채우기
d. frame.tobytes() : numpy 배열을 바이트로 변환하여 data 필드에 저장
e. self.publisher_.publish() : 토픽(`/camera/image_raw`)으로 발행
    - `sensor_msgs/msg/Image` 메시지로 변환하여 발행

*sensor_msgs/msg/Image 구조:*
```
Image
├── header
│   ├── stamp: 초 단위 타임스탬프 (float64)
│   └── frame_id: 좌표계 이름 ("camera_frame")
├── height: 이미지 높이 (uint32)
├── width: 이미지 너비 (uint32)
├── encoding: 코딩 방식 ("bgr8", "rgb8", "mono8")
├── is_bigendian: 바이트 순서 (bool)
├── step: 한 줄의 바이트 수 (width × 채널 수)
└── data: 실제 픽셀 데이터 (uint8[])
```

- `data`: 640×640×3 = 1,228,800 바이트 (BGR 순서)
- `encoding`: OpenCV는 기본적으로 BGR 포맷 사용

2. detector_node

YOLO 기반 객체 탐지 노드

*역할:*
- `/camera/image_raw` 토픽을 구독(카메라 노드에서 이미지를 수신)
- YOLO 모델(yolo11n의 best.pt)로 객체 탐지 수행
- 탐지 결과를 `/detection_results` 토픽으로 발행

*파라미터:*
- `~model_path`: YOLO 모델 파일 경로 (.pt)
- `~conf_threshold`: 탐지 신뢰도 임계값 (0.0 ~ 1.0)
- `~iou_threshold`: NMS IoU 임계값
- `~device`: 추론 디바이스 ("cpu" 또는 "cuda")

*흐름:*
- 구독: camera_node에서 `/camera/image_raw` 토픽 수신
- `imgmsg_to_cv2()`: ROS2 Image 메시지를 OpenCV numpy 배열(BGR)로 변환
- `model.predict()`: YOLO 모델로 객체 탐지 수행 (바운딩박스, 클래스, 신뢰도 반환)
- `convert_to_detection_msg()`: 탐지 결과를 `Detection2DArray`로 변환
    - 바운딩박스: 좌상단/우하단(xyxy) → 중심점/크기(center, size) 변환
    - 클래스: 정수 ID → 문자열 이름 변환
- 발행: 토픽(`/detection_results`)으로 탐지 결과 발행
    - `vision_msgs/msg/Detection2DArray` 메시지로 변환하여 발행

*vision_msgs/msg/Detection2DArray 구조:*
```
Detection2DArray
├── header: 타임스탬프, 프레임 ID
└── detections[]: 탐지된 객체 리스트
    └── Detection2D
        ├── bbox (BoundingBox2D)
        │   ├── center (Point2D)
        │   │   ├── x: 중심점 x 좌표 (픽셀)
        │   │   └── y: 중심점 y 좌표 (픽셀)
        │   └── size (Vector2)
        │       ├── x: 바운딩박스 폭 (픽셀)
        │       └── y: 바운딩박스 높이 (픽셀)
        └── results[] (ObjectHypothesisWithPose)
            └── hypothesis (ObjectHypothesis)
                ├── class_id: 클래스 이름 (string)
                └── score: 신뢰도 (float64, 0.0~1.0)
```

- `header`: 원본 카메라 이미지의 타임스탬프를 그대로 복사 (동기화용)
- `bbox`: YOLO의 xyxy 포맷을 ROS2 표준 포맷(center+size)으로 변환하여 저장
- `results`: 클래스 이름과 신뢰도를 하나의 리스트로 저장 (여러 클래스 탐지 가능)