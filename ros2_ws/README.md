# YOLO Edge AI waste Sorter - ROS2

## 패키지 구조

*노드별로 독립된 패키지로 구성*
```
ros2_ws/
├── best.pt / best.onnx / best_int8.onnx   # 탐지 모델 가중치 (gitignore 대상)
├── make_homography.py                     # 호모그래피 캘리브레이션 스크립트
├── homography_matrix.npy                  # 캘리브레이션 산출물 (gitignore 대상)
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
    │   │   ├── detector_node.py        # 노드 메인 (멀티스레드 프레임 스킵)
    │   │   └── inference_engine.py     # EngineFactory (pt/onnx 공용 인터페이스)
    │   ├── resource/detector_node_pkg
    │   ├── test/                       # 콜백/스레딩/프레임 스킵 테스트
    │   ├── package.xml
    │   ├── setup.py
    │   └── setup.cfg
    │
    ├── robot_control_node/         # 패키지 3 (호모그래피 및 IK 제어 노드)
    │   ├── robot_control_node/
    │   │   ├── __init__.py
    │   │   └── robot_control_node.py
    │   ├── resource/robot_control_node
    │   ├── test/
    │   ├── package.xml
    │   ├── setup.py
    │   └── setup.cfg
    │
    ├── evaluation_node/            # 패키지 4 (평가 노드 - 관찰 기반 성능 기록)
    │   ├── evaluation_node/
    │   │   ├── __init__.py
    │   │   ├── evaluation_node.py      # 노드 (구독 + 서비스)
    │   │   ├── keyboard_node.py        # 키보드 제어 노드 (s/e/q)
    │   │   ├── keyboard_control.py
    │   │   ├── config_loader.py
    │   │   ├── core.py                 # 회차 상태/결과 파일 로직 (ROS 비의존)
    │   │   ├── kinematics.py           # FK / 관절 순서 정렬
    │   │   └── visualization.py        # 평가 그래프 생성
    │   ├── config/
    │   │   └── evaluation.yaml
    │   ├── resource/evaluation_node
    │   ├── test/
    │   ├── README.md
    │   ├── package.xml
    │   ├── setup.py
    │   └── setup.cfg
    │
    └── (feetech_ros2_driver/)      # 외부 의존성 (실물 SO-ARM101 드라이버)
        └── (upstream에서 clone하여 배치 - 아래 "외부 의존성" 참고)
```

> **참고**: `so101-ros-physical-ai`와 `feetech_ros2_driver`는 이전에 git submodule로
> 연결되었으나 submodule 구성(.gitmodules)이 누락된 채 커밋되어 복제 시 빈 디렉토리가 생성되는 문제가 있었습니다. 이를 해결하기 위해 gitlink를 제거하고
> 실물 드라이버는 아래 "외부 의존성" 절차로 직접 내려받아 사용합니다.
> `src/feetech_ros2_driver/`는 `ros2_ws/.gitignore`에 포함되어 커밋되지 않습니다.

## 시스템 흐름

```text
┌─────────────────────────────────────────────────────────────────┐
│  camera_node_pkg                                                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ /camera_node                                              │  │
│  │ USB 카메라 → JPEG 인코딩 → CompressedImage 발행                │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           │
           │ /camera/image_raw (sensor_msgs/msg/CompressedImage)
           │ (qos_profile_sensor_data, frame_id: "camera_frame")
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  detector_node_pkg                                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ /detector_node                                            │  │
│  │ YOLO(pt/onnx) 탐지 → Detection2DArray 발행 (멀티스레드)        │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           │
           │ /detection_results (vision_msgs/msg/Detection2DArray)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  robot_control_node                                             │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ /robot_control_node                                       │  │
│  │ 픽셀좌표 → Homography 변환 → IK 연산 → 상태머신 순차 제어         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           │
           │ Action: /follower/joint_trajectory_controller/follow_joint_trajectory
           │ (control_msgs/action/FollowJointTrajectory)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│  feetech_ros2_driver (외부 드라이버)                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  실물 SO-ARM101 액션 서버 (관절 명령 → Serial → USB)          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
           │
           │ Topic: /follower/joint_states (sensor_msgs/msg/JointState)
           ▼
      ┌───────────┐
      │ SO-ARM101 │
      └───────────┘

  ※ evaluation_node는 위 흐름과 병렬로 실행되며 제어 명령은 발행하지 않고
    /detection_results, /follower/joint_states, 액션 상태/피드백만 관찰한다.
```

## 의존성

| 구분 | ROS2 | Python |
|---|---|---|
| camera_node_pkg | rclpy, sensor_msgs | opencv-python, numpy |
| detector_node_pkg | rclpy, sensor_msgs, vision_msgs | ultralytics==8.4.87, opencv-python, numpy, onnxruntime-gpu |
| robot_control_node | rclpy, vision_msgs, control_msgs, trajectory_msgs, action_msgs, sensor_msgs | numpy |
| evaluation_node | rclpy, sensor_msgs, vision_msgs, std_srvs, control_msgs, action_msgs | numpy, matplotlib, pyyaml |
| feetech_ros2_driver (외부) | rclpy, control_msgs, trajectory_msgs, sensor_msgs | - |

## 외부 의존성 (feetech_ros2_driver)

`robot_control_node`와 `evaluation_node`는 실물 SO-ARM101과 통신하기 위해 아래
ROS2 인터페이스를 사용합니다. 이들은 **프로젝트 저장소에 포함되지 않은 외부
드라이버**가 제공합니다.

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

## 호모그래피 캘리브레이션 (make_homography.py)

픽셀 좌표를 로봇 기준 실제 좌표(mm)로 변환하는 행렬을 만드는 스크립트입니다.

```bash
# 1. 카메라 화면(Calibration Window)에서 기준점 4개를 클릭
# 2. 각 점에 대해 로봇 기저 기준 실제 X, Y 거리(mm)를 입력
# 3. ros2_ws/homography_matrix.npy 로 저장
python3 make_homography.py
```

> **주의**: 기본 카메라 인덱스는 `2`입니다(`cv2.VideoCapture(2)`). 저장 경로가
> 스크립트 내부에서 고정되어 있으므로 필요 시 수정하세요.

## 각 노드 구성

### 1. camera_node

카메라 영상을 읽어서 JPEG 압축 후 ROS2 토픽으로 발행하는 노드

*역할:*
- USB 카메라 또는 웹캠에서 영상 프레임을 읽음
- OpenCV BGR 프레임을 JPEG(`quality 80`)으로 인코딩
- `/camera/image_raw` 토픽으로 `CompressedImage` 발행 (QoS: `qos_profile_sensor_data`)

*파라미터:*
- `~camera_id`: 카메라 인덱스 (기본값: **2**)
- `~frame_width`: 프레임 너비 (기본값: 640)
- `~frame_height`: 프레임 높이 (기본값: 480)
- `~fps`: 초당 프레임 수 (기본값: 30)

*흐름:*
1. `cv2.VideoCapture.read()`: 카메라에서 프레임 읽기
2. `cv2.imencode('.jpg', frame, quality=80)`: JPEG 인코딩
3. `CompressedImage()` 메시지 생성 (`format='jpeg'`, `frame_id='camera_frame'`)
4. `encoded.tobytes()`를 `data` 필드에 저장
5. `self.publisher_.publish()`: 토픽(`/camera/image_raw`)으로 발행

*sensor_msgs/msg/CompressedImage 구조:*
```
CompressedImage
├── header
│   ├── stamp: 초 단위 타임스탬프 (float64)
│   └── frame_id: 좌표계 이름 ("camera_frame")
├── format: 압축 방식 ("jpeg")
└── data: JPEG 압축된 픽셀 데이터 (uint8[])
```

*실행:*
```bash
# 카메라 인덱스 변경 예시
ros2 run camera_node_pkg camera_node --ros-args -p camera_id:=2
```

### 2. detector_node

YOLO 기반 객체 탐지 노드 (멀티스레드 프레임 스킵 적용)

*역할:*
- `/camera/image_raw` 토픽 구독 (`CompressedImage`, QoS: `qos_profile_sensor_data`)
- `EngineFactory`가 모델 확장자에 따라 엔진 선택
  - `.pt` → `YoloEngine` (ultralytics)
  - `.onnx` → `OnnxEngine` (onnxruntime)
- 탐지 결과를 `/detection_results` 토픽으로 발행 (`Detection2DArray`)

*파라미터:*
- `~model_path`: YOLO 모델 파일 경로 (기본값: **best.onnx**)
- `~conf_threshold`: 탐지 신뢰도 임계값 (기본값: 0.5)
- `~iou_threshold`: NMS IoU 임계값 (기본값: 0.45)
- `~device`: 추론 디바이스 (기본값: "cpu", "cuda" 지원)
- `~imgsz`: 추론 입력 해상도 (기본값: 640)

*스레딩 구조:*
1. 이미지 콜백은 `MutuallyExclusiveCallbackGroup`으로 직렬 처리되고 즉시 반환
2. 추론은 백그라운드 스레드(`_inference_loop`)에서 수행
3. 프레임 큐(`queue.Queue(maxsize=1)`)에 최신 프레임 1개만 유지
   - 추론 중(`_busy=True`) 도착한 프레임은 스킵하고 카운터 기록
4. `MultiThreadedExecutor`로 콜백과 추론 스레드를 병렬 실행
5. 1초 간격 타이머로 클래스별 탐지 요약 로깅

*흐름:*
1. 구독: camera_node에서 `/camera/image_raw` 수신
2. `_imgmsg_to_cv2()`: JPEG 바이트를 OpenCV numpy 배열(BGR)로 디코딩
3. `engine.predict()`: YOLO 탐지 수행 → `[{class_name, confidence, bbox}]`
4. `_make_detection_msg()`: `Detection2DArray` 메시지로 변환 (header 타임스탬프 유지)
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
                ├── class_id: 클래스 이름 (string, 예: "can")
                └── score: 신뢰도 (float64, 0.0~1.0)
```

*실행:*
```bash
ros2 run detector_node_pkg detector_node
```

*파라미터 예시:*
```bash
ros2 run detector_node_pkg detector_node --ros-args \
  -p model_path:=best.onnx \
  -p conf_threshold:=0.5 \
  -p iou_threshold:=0.45 \
  -p device:=cuda \
  -p imgsz:=640
```

### 3. robot_control_node

탐지 결과를 받아 호모그래피 변환 → IK 역기구학 → 상태머신 기반 순차 제어를
수행하는 독립 제어 노드

*역할:*
- `/detection_results` 토픽 구독
- `target_class`에 해당하는 객체만 처리
- 픽셀 좌표 → `homography_matrix.npy` 행렬 → 로봇 기준 실제 좌표(mm)
- 6축 관절각을 IK로 계산하고 `FollowJointTrajectory` 액션 서버로 전송
- 실물 관절 상태는 `/follower/joint_states` 구독으로 피드백

*파라미터:*
- `~target_class`: 처리할 객체 클래스 목록 (기본값: `['can', 'pet bottle', 'styrofoam']`)
- `~homography_path`: 캘리브레이션 행렬 경로 (기본값: `homography_matrix.npy`)

*상태머신:*
```
IDLE ──> APPROACH_1 ──> APPROACH_2 ──> APPROACH_2_WAIT(1.5s)
  ▲                                          │
  │                                          ▼
COOL_DOWN(3s) <── RELEASE <── LIFT_AND_MOVE <── LIFT_UP <── GRASP <── APPROACH_3
```

- **APPROACH_1**: 허리 조준, L3 90° 부양, 집게 최대 개방
- **APPROACH_2**: 팔꿈치 90° 유지한 채 어깨만 선제 전진
- **APPROACH_2_WAIT**: L2 모터 완전 정지까지 1.5초 대기
- **APPROACH_3**: 팔꿈치만 수직 하강 (파지 자세 도달)
- **GRASP**: 집게 오므리기 (gripper_close)
- **LIFT_UP**: 팔꿈치만 다시 90°로 수직 복귀
- **LIFT_AND_MOVE**: 안전 고공 높이로 홈(홈 위치) 이송 → 파지 검증 CSV 기록
- **RELEASE**: 집게 열고 폐기물 배출
- **COOL_DOWN**: 비전 차단 3초 후 IDLE 복귀

*파지 검증 (grasp_metrics_log.csv):*
- 작업 디렉토리에 `grasp_metrics_log.csv` 생성
- 컬럼: `trial_id, class_name, real_angle_rad, is_grasped`
- `is_grasped = real_angle > 3.20` (그리퍼 인코더 실측값 기준)

*실행:*
```bash
ros2 run robot_control_node robot_control_node
```

*파라미터 예시:*
```bash
ros2 run robot_control_node robot_control_node --ros-args \
  -p target_class:=['can','pet bottle','styrofoam'] \
  -p homography_path:=homography_matrix.npy
```

### 4. evaluation_node (+ keyboard_node)

SO-ARM101의 파지·분류 성능을 **관찰만으로** 측정하는 평가 노드
(제어 명령은 발행하지 않음)

*역할:*
- `/detection_results`, `/follower/joint_states`, 액션 상태/피드백 구독
- FK(순기구학)로 실제 파지 위치를 계산하고 GT와 비교
- 회차별 결과를 CSV(`results.csv`)에 기록하고 종료 시 PNG 그래프 5종 생성
- 키보드 노드(`keyboard_node`)로 s/e/q 입력 제어

*키보드 제어 (keyboard_node):*
- `s`: 다음 회차 시작 (`start_next_trial`)
- `e`: 현재 회차 저장/종료 (`end_trial`)
- `q`: 평가 종료 및 분석 (`stop_run` → `analyze`)

*서비스 (std_srvs/srv/Trigger):*
- `/evaluation/start_next_trial`
- `/evaluation/end_trial`
- `/evaluation/abort_trial`
- `/evaluation/stop_run`
- `/evaluation/status`
- `/evaluation/preflight`
- `/evaluation/record_grasp`
- `/evaluation/record_sort`
- `/evaluation/analyze`

*설정 (config/evaluation.yaml):*
- `target_classes`: `[can, pet bottle, styrofoam]`
- `positions`: `{P01: {x_mm, y_mm}}` 형태의 GT 좌표 (반드시 실측값 입력)
- `position_tolerance_mm`: 위치 통과 기준
- `gripper_open_threshold` / `gripper_closed_threshold`: 그리퍼 상태 판정
- `configuration_confirmed` / `thresholds_locked`: 실장비 확인 후 `true`
- `output_directory`: 기본값 `/tmp/so_arm101_evaluation`

*실행:*
```bash
ros2 run evaluation_node evaluation_node \
  --ros-args -p config_path:=src/evaluation_node/config/evaluation.yaml
ros2 run evaluation_node keyboard_node
```

*결과물 (config의 output_directory 아래 `evaluation_<UTC타임스탬프>/`):*
- `results.csv`: 회차별 측정 결과
- `summary.json`: 평가 요약
- `run_state.json`: 실시간 상태
- `charts/`: PNG 그래프 (visualization_enabled 시)

## 실행/테스트 방법

```bash
# 1. 카메라 노드
ros2 run camera_node_pkg camera_node

# 2. 객체 탐지 노드 (별도 터미널)
ros2 run detector_node_pkg detector_node

# 3. 로봇 제어 노드 (별도 터미널, 실물 연결 시)
ros2 run robot_control_node robot_control_node

# 4. 평가 노드 + 키보드 노드 (별도 터미널 2개)
ros2 run evaluation_node evaluation_node --ros-args \
  -p config_path:=src/evaluation_node/config/evaluation.yaml
ros2 run evaluation_node keyboard_node

# 토픽/액션 확인
ros2 topic list
ros2 topic echo /detection_results
ros2 action list
```

*테스트:*
```bash
# 패키지별 테스트 (각 패키지 디렉토리에서)
cd src/detector_node_pkg && python3 -m pytest test/ -v
cd src/evaluation_node && python3 -m pytest test/ -v
```
