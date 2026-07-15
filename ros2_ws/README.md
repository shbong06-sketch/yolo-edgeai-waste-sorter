# ros2 구조

## 패키지 구조

*노드별로 독립된 패키지로 구성*
```
ros2_ws/
├── src/
│   ├── camera_node_pkg/        # 패키지 1 (카메라 노드)
│   │   ├── camera_node_pkg/
│   │   │   ├── __init__.py
│   │   │   └── camera_node.py
│   │   ├── resource/camera_node_pkg
│   │   ├── test/
│   │   ├── package.xml
│   │   ├── setup.py
│   │   └── setup.cfg
│   └── detector_node_pkg/      # 패키지 2 (객체 탐지 노드)
│       ├── detector_node_pkg/
│       │   ├── __init__.py
│       │   └── detector_node.py
│       ├── resource/detector_node_pkg
│       ├── test/
│       ├── package.xml
│       ├── setup.py
│       └── setup.cfg
├── .venv/                      # Python 가상환경
├── build/                      # 빌드 중간 파일
├── install/                    # 빌드 결과물
└── log/
```

## 개발 환경 설정 (venv)

```bash
cd ros2_ws

# venv 생성
python3 -m venv .venv

# venv 활성화
source .venv/bin/activate

# colcon 설치
pip install colcon-common-extensions

# 패키지 의존성 설치
pip install camera_node_pkg
pip install detector_node_pkg

# ROS2 환경 등록
source /opt/ros/jazzy/setup.bash

# 빌드
colcon build

# 빌드 결과 등록
source install/setup.bash
```

## 의존성

| 구분 | camera_node_pkg | detector_node_pkg |
|---|---|---|
| ROS2 | rclpy, sensor_msgs | rclpy, sensor_msgs, vision_msgs |
| Python | opencv-python, numpy | ultralytics, opencv-python, numpy, torch |

## 인터페이스 구조

| 토픽 | 메시지 타입 | 발행자 | 구독자 |
|---|---|---|---|
| `/camera/image_raw` | `sensor_msgs/Image` | `camera_node` | `detector_node` |
| `/detection_results` | `vision_msgs/Detection2DArray` | `detector_node` | 나중 부분(`robot_control`) |

## 각 노드 구성

### 1. camera_node

카메라 영상을 구독하여 ROS2 토픽으로 발행하는 노드

*역할:*
- USB 카메라 또는 웹캠에서 영상 프레임을 읽음
- OpenCV 이미지를 ROS2 Image 메시지로 변환
- `/camera/image_raw` 토픽으로 발행

*파라미터:*
- `~camera_id`: 카메라 인덱스 (기본값: 0)
- `~frame_width`: 프레임 너비 (기본값: 640)
- `~frame_height`: 프레임 높이 (기본값: 480)
- `~fps`: 초당 프레임 수 (기본값: 30)

*흐름:*
1. `cv2.VideoCapture.read()`: 카메라에서 프레임 읽기
2. `Image()` 객체 생성: ROS2 메시지 구조 만들기
3. header, width, height 등 설정: 메시지에 정보 채우기
4. `frame.tobytes()`: numpy 배열을 바이트로 변환하여 data 필드에 저장
5. `self.publisher_.publish()`: 토픽(`/camera/image_raw`)으로 발행

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

- `data`: 640×480×3 = 921,600 바이트 (BGR 순서)
- `encoding`: OpenCV는 기본적으로 BGR 포맷 사용

*실행:*
```bash
ros2 run camera_node_pkg camera_node
```

### 2. detector_node

YOLO 기반 객체 탐지 노드

*역할:*
- `/camera/image_raw` 토픽을 구독(카메라 노드에서 이미지를 수신)
- YOLO 모델(yolo11n 또는 best.pt)로 객체 탐지 수행
- 탐지 결과를 `/detection_results` 토픽으로 발행

*파라미터:*
- `~model_path`: YOLO 모델 파일 경로 (기본값: best.pt)
- `~conf_threshold`: 탐지 신뢰도 임계값 (기본값: 0.5)
- `~iou_threshold`: NMS IoU 임계값 (기본값: 0.45)
- `~device`: 추론 디바이스 (기본값: "cpu")

*흐름:*
1. 구독: camera_node에서 `/camera/image_raw` 토픽 수신
2. `imgmsg_to_cv2()`: ROS2 Image 메시지를 OpenCV numpy 배열(BGR)로 변환
3. `model.predict()`: YOLO 모델로 객체 탐지 수행
4. `convert_to_detection_msg()`: 탐지 결과를 `Detection2DArray`로 변환
5. 발행: 토픽(`/detection_results`)으로 탐지 결과 발행

*vision_msgs/msg/Detection2DArray 구조:*
```
Detection2DArray
├── header: 타임스탬프, 프레임 ID
└── detections[]: 탐지된 객체 리스트
    └── Detection2D
        ├── bbox (BoundingBox2D)
        │   ├── center (Pose2D)
        │   │   ├── position.x: 중심점 x 좌표 (픽셀)
        │   │   ├── position.y: 중심점 y 좌표 (픽셀)
        │   │   └── theta: 회전각
        │   ├── size_x: 바운딩박스 폭 (픽셀)
        │   └── size_y: 바운딩박스 높이 (픽셀)
        └── results[] (ObjectHypothesisWithPose)
            └── hypothesis (ObjectHypothesis)
                ├── class_id: 클래스 이름 (string)
                └── score: 신뢰도 (float64, 0.0~1.0)
```

*실행:*
```bash
ros2 run detector_node_pkg detector_node
```

*파라미터 예시:*
```bash
ros2 run detector_node_pkg detector_node --ros-args \
  -p model_path:=best.pt \
  -p conf_threshold:=0.7 \
  -p device:=cuda
```

## ROS2 Jazzy 호환 참고사항

Pose2D와 BoundingBox2D의 속성명이 이전 버전과 다릅니다:

| 속성 | 이전 (Humble 등) | Jazzy |
|---|---|---|
| 중심점 좌표 | `bbox.center.x`, `bbox.center.y` | `bbox.center.position.x`, `bbox.center.position.y` |
| 바운딩박스 크기 | `bbox.size.x`, `bbox.size.y` | `bbox.size_x`, `bbox.size_y` |
