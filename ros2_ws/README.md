# YOLO Edge AI waste Sorter - ROS2

## 패키지 구조

*노드별로 독립된 패키지로 구성*
```
ros2_ws/
└── src/
    ├── camera_node_pkg/            # 패키지 1 (카메라 노드)
    │   ├── camera_node_pkg/
    │   │   ├── __init__.py
    │   │   └── camera_node.py
    │   ├── resource/camera_node_pkg
    │   ├── test/
    │   ├── package.xml
    │   ├── setup.py
    │   └── setup.cfg
    │
    ├── detector_node_pkg/          # 패키지 2 (객체 탐지 노드)
    │   ├── detector_node_pkg/
    │   │   ├── __init__.py
    │   │   └── detector_node.py
    │   ├── resource/detector_node_pkg
    │   ├── test/
    │   ├── package.xml
    │   ├── setup.py
    │   └── setup.cfg
    │
    ├── robot_control_node/         # 패키지 3 (호모그래피 및 IK 제어 노드)
    │   ├── robot_control_node/
    │   │   ├── __init__.py
    │   │   └── robot_control_node.py
    │   ├── package.xml
    │   ├── setup.py
    │   └── setup.cfg
    │
    ├── evaluation_node/            # 패키지 4 (평가 노드 - 관찰 기반 성능 기록)
    │   ├── evaluation_node/
    │   ├── config/
    │   ├── test/
    │   ├── package.xml
    │   ├── setup.py
    │   └── setup.cfg
    │
    └── feetech_ros2_driver/        # 외부 의존성 (실물 SO-ARM101 드라이버)
        └── (upstream에서 clone하여 배치 - 아래 "외부 의존성" 참고)
```

> **참고**: `so101-ros-physical-ai`와 `feetech_ros2_driver`는 이전에 git submodule로
> 연결되었으나 submodule 구성(.gitmodules)이 누락된 채 커밋되어 복제 시 빈
> 디렉토리가 생성되는 문제가 있었습니다. 이를 해결하기 위해 gitlink를 제거하고
> 실물 드라이버는 아래 "외부 의존성" 절차로 직접 내려받아 사용합니다.

## 시스템 흐름

```text
┌─────────────────────────────────────────────────────────────────┐
│  camera_node_pkg                                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ /camera_node                                              │  │
│  │ USB 카메라 → ROS Image 메시지 발행                            │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           │
           │ /camera/image_raw (sensor_msgs/msg/Image)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  detector_node_pkg                                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ /detector_node                                            │  │
│  │ YOLO 모델로 객체 탐지 → Detection2DArray 발행                  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           │
           │ /detection_results (vision_msgs/msg/Detection2DArray)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  robot_control_node                                             │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ /robot_control_node                                       │  │
│  │ 픽셀좌표 → Homography 변환 → IK 연산 → 관절 각도 산출            │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           │
           │ /joint_trajectory_controller/joint_trajectory
           │ (trajectory_msgs/msg/JointTrajectory)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  so101-ros-physical-ai                                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ /so101_bringup_node                                       │  │
│  │ ROS2 관절 명령 → Serial 신호 변환 → USB 통신                   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           │
           │ USB Serial (/dev/ttyUSBX)
           ▼
      ┌───────────┐
      │ SO-ARM101 │
      └───────────┘
```

## 의존성

| 구분 | ROS2 | Python |
|---|---|---|
| camera_node_pkg | rclpy, sensor_msgs | opencv-python, numpy |
| detector_node_pkg | rclpy, sensor_msgs, vision_msgs | ultralytics, opencv-python, numpy, torch |
| robot_control_node | rclpy, vision_msgs, control_msgs, trajectory_msgs, action_msgs, sensor_msgs | numpy |
| evaluation_node | rclpy, sensor_msgs, vision_msgs, std_srvs | numpy, matplotlib, pyyaml |
| feetech_ros2_driver (외부) | rclpy, control_msgs, trajectory_msgs, sensor_msgs | - |

## 외부 의존성 (feetech_ros2_driver)

`robot_control_node`는 실물 SO-ARM101 구동을 위해 아래 ROS2 인터페이스를
사용합니다. 이들은 **프로젝트 저장소에 포함되지 않은 외부 드라이버**가
제공합니다.

- Action: `/follower/joint_trajectory_controller/follow_joint_trajectory` (`FollowJointTrajectory`)
- Topic: `/follower/joint_states` (`sensor_msgs/msg/JointState`)

드라이버는 [LeRobot](https://github.com/huggingface/lerobot) 저장소의
SO-ARM101 / Feetech 구동 코드를 기반으로 한 외부 컴포넌트입니다. 팀에서 확보한
드라이버 소스를 `ros2_ws/src/feetech_ros2_driver/`에 배치한 뒤 전체 워크스페이스를
빌드합니다.

```bash
cd ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build
source install/setup.bash
```

> **주의**: 이 경로는 `ros2_ws/.gitignore`에 포함되어 있어 커밋되지 않습니다.
> 상위 프로젝트의 ROS2 파이프라인(detector/robot_control)과 독립적으로 동작하며,
> 시뮬레이션(`wsSIM`)만 사용할 때는 이 드라이버가 필요 없습니다.

## 빌드 테스트 환경 설정 (.venv)

```bash
cd ros2_ws

# 1. venv 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 2. ROS2 환경 등록
source /opt/ros/jazzy/setup.bash

# 3. 빌드 도구 설치
pip install colcon-common-extensions

# 4. 빌드
colcon build

# 5. 빌드 결과 등록
source install/setup.bash
```

## 각 노드 구성

### 1. camera_node

카메라 영상을 읽어서 ROS2 토픽으로 발행하는 노드

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

### 3. robot_control_node


### 4. so101_bringup_node


## 실행/테스트 방법

```bash
# 전체 실행

```