# ♻️ YOLO 기반 에지 AI 쓰레기 자동 분류 시스템
> **YOLO-Based Edge AI Automated Waste Sorting System with SO-ARM 101**

본 프로젝트는 스마트 팩토리 및 자동화 공정의 재활용 분리수거 수작업 의존도 문제를 해결하기 위해 **비전 AI(YOLO)**와 **로봇 공학(ROS2)**을 결합한 자동 선별 시스템입니다. 

카메라 피드를 통해 실시간으로 유입되는 폐기물을 에지 디바이스 환경에서 고속으로 탐지하고, 로봇 마니퓰레이터(SO-ARM 101)와 연동하여 지정된 수거함으로 자동 분류하는 완전 자동화 공정 프로세스를 구현합니다.

---

## 🎯 프로젝트 개요 & 목표 (Objectives)

### 1. 문제 정의
* 스마트 팩토리 및 자동화 공정에서 재활용품 분리수거는 여전히 수작업 의존도가 높고 비용이 많이 드는 영역입니다.
* 작업자의 안전 문제와 구인난을 해결하기 위해, 비전 AI와 로봇 공학을 결합한 고속 자동 선별 시스템의 도입이 시급합니다.

### 2. 핵심 목표 (MVP)
* **데이터셋 구축:** AIHub 데이터를 활용한 **[금속 캔, 페트병, 스티로폼]** 3종 맞춤형 데이터셋 구축 (총 9,999장)
* **AI 모델 최적화:** 실시간 추론을 위한 경량화된 YOLO 객체 탐지 모델 학습 및 성능 확보

### 3. 추가 목표 (Stretch Goal)
* **시뮬레이션 및 실물 연동:** SO-ARM 101 로봇 팔과 소형 가상(Isaac Sim 등)/실물 컨베이어 벨트 연동
* **비전-행동(Vision-to-Action) 구현:** 카메라가 탐지한 쓰레기의 2D 픽셀 좌표를 로봇의 3D 공간 좌표계로 변환(Homography)하여 실시간 그리핑 및 지정 수거함 자동 분류 공정 구현

---

## ⚙️ 연결 다이어그램

┌────────────────────────────────────────────────────────────────────────┐
│ [Node] /camera_node  (Package: camera_node_pkg)                       │
└────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ [Topic]  camera/image_raw
                                 │ [Type]   sensor_msgs/msg/Image
                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│ [Node] /detector_node  (Package: detector_node_pkg)                   │
└────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ [Topic]  detection_results
                                 │ [Type]   vision_msgs/msg/Detection2DArray
                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│ [Node] /robot_control_node  (Package: robot_control_node)             │
├────────────────────────────────────────────────────────────────────────┤
│  * 동기화: threading.Lock() 스레드 격리로 고속 프레임 레이스컨디션 차단 │
│  * 기하학: Homography 행렬 변환 및 역기하학(IK) 수행 (L2 배율 보정)     │
│  * 제어기: 관성 소멸 정착 대기(1.5초)를 포함한 6단계 정밀 순차 상태머신│
└────────────────────────────────────────────────────────────────────────┘
                    │                               ▲
                    │                               │
   [Action Client]  │                               │ [Topic Subscription]
  /follower/joint_trajectory_controller/            │ /follower/joint_states
  follow_joint_trajectory                           │ (sensor_msgs/msg/JointState)
  (control_msgs/action/FollowJointTrajectory)       │ [실물 서보 인코더 피드백]
                    │                               │
                    ▼                               │
┌────────────────────────────────────────────────────────────────────────┐
│ [Node] /ros2_control_node  (Package: controller_manager / so101_bringup)│
├────────────────────────────────────────────────────────────────────────┤
│  * 구동 하드웨어 플러그인: feetech_ros2_driver/FeetechHardwareInterface│
│  * 역할: ROS 궤적 명령을 Feetech 스마트 서보 시리얼 프로토콜로 변환     │
└────────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ [Hardware Interface] USB Serial
                                 │ [Target Port] /dev/ttyACM0
                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│ [Hardware] SO-ARM 101 실물 로봇 암 (6자유도 Feetech 스마트 서보 구조)    │
└────────────────────────────────────────────────────────────────────────┘

# 📂 Project Structur

```text
ros2_ws/
├── src/                                 # 메인 소스코드 소스 폴더
│   ├── camera_node_pkg/                 # 카메라 비전 스트림 송출 패킷 노드 Package
│   ├── detector_node_pkg/               # YOLO 기반 객체 탐지 및 픽셀 좌표 추출 Package
│   ├── robot_control_node/              # [핵심] 스레드 격리형 6단계 안전 순차 제어 노드
│   ├── feetech_ros2_driver/             # Feetech 스마트 서보모터 하드웨어 인터페이스 드라이버
│   └── so101-ros-physical-ai/           # SO-ARM 101 로봇 팔 통합 운용 프레임워크
│       ├── so101_bringup/               # 실물 로봇 가동 및 비전 런칭 스크립트 (Launch, YAML)
│       ├── so101_description/           # 로봇 URDF 모델링 및 메쉬(STL) 하드웨어 정의 파일
│       ├── so101_kinematics/            # 기하학 연산 및 Cartesian 모션 플래너 노드
│       ├── so101_kinematics_msgs/       # 관절 및 포즈 제어 전용 커스텀 ROS2 서비스(SRV) 정의
│       ├── so101_moveit_config/         # MoveIt 오프라인 궤적 기획 및 충돌 방지 셋업
│       ├── policy_server/               # VLA/ACT 모델 추론 연동 전용 gRPC/ZMQ 서버
│       └── rosbag_to_lerobot/           # 모방 학습(Imitation Learning) 데이터셋 변환 툴
├── make_homography.py                   # 카메라-로봇 스페이스 캘리브레이션 행렬 생성 스크립트
└── README.md                            # 프로젝트 메인 개발 문서

 ```

## 📊 데이터셋 (Dataset)

| 구분 | 내용 |
|---|---|
| 전체 | 9,999장 (train 7,999 / val 2,000, 80:20 split) |
| 클래스 | Can (3,333), Pet bottle (3,333), Styrofoam (3,333) |
| 출처 | AIHub 선별영상 추출 이미지(영상추출) 9,000장, 개별 재활용품 이미지(직접촬영) 999장 ([AIHub 링크](https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&aihubDataSe=data&dataSetSn=71362)) |
| 해상도 | 640×640 (YOLO 입력 기준) |
| 라벨 포맷 | YOLO format (`class_id x_center y_center width height`) |

| Class        | Train    | Val      | Total    |
|---|---|---|---|
| Can          | 2,667    | 666      | 3,333    |
| Pet bottle   | 2,666    | 667      | 3,333    |
| Styrofoam    | 2,666    | 667      | 3,333    |
| **Total**    | **7,999**| **2,000**| **9,999**|

> 메타데이터: `dataset_metadata.csv` (이미지별 출처, 클래스, split 정보 포함)
> 다운로드: [Google Drive](https://drive.google.com/file/d/1G4qchajo2-Tmv9D_KOxuKr_NzRUwT2DO/view?usp=sharing) - `yolo_waste_dataset_v1.0.zip`

## 🛠️ 기술 스택 (Tech Stack)
- AI / Data: PyTorch, Ultralytics (YOLOv8/v10), OpenCV, Pandas, NumPy, Scikit-learn, Roboflow

- Robotics / HW: ROS2 (Humble/Jazzy), Isaac Sim, Python-Serial (로봇 팔 통신)

- Full-Stack / UI: Streamlit (또는 FastAPI + React), Matplotlib, Plotly

- Collaboration: GitHub

## 🚀 시작하기 (Setup & Installation)
가상환경 충돌을 예방하기 위해 AI 환경과 ROS2 환경을 반드시 분리하여 터미널을 실행해 주세요.

1. AI & 전처리 환경 설정 (Conda 환경 추천)
```Bash
# AI 폴더 이동 및 가상환경 생성
cd ai
conda create -n env_sorter_ai python=3.10 -y
conda activate env_sorter_ai

# 의존성 패키지 설치
pip install --upgrade pip
pip install -r requirements.txt
2. ROS2 로봇 제어 환경 설정 (Ubuntu 네이티브 환경 추천)
```
```Bash
# ROS2 ROS 2 워크스페이스 빌드
cd ros2_ws
source /opt/ros/jazzy/setup.bash  # 혹은 본인 ROS2 버전명

# 빌드 및 패키지 환경 적용
colcon build --symlink-install
source install/setup.bash
```

실행 방법 (Execution Guide)

```Bash
# [모든 터미널 공통 사전 실행 명령]
cd ~/yolo-edgeai-waste-sorter/ros2_ws
source /.venv/bin/activate
source /opt/ros/jazzy/setup.bash
source install/setup.bash

# 1. 카메라 노드 구동 (Terminal 1)
ros2 run camera_node_pkg camera_node

# 2. YOLO 객체 탐지 노드 구동 (Terminal 2)
ros2 run camera_node_pkg camera_node

# 3. 로봇 하드웨어 & 비전 드라이버 런칭 (Terminal 3)
ros2 launch so101_bringup follower_vision.launch.py

# 4. 순차 제어 노드 구동 (Terminal 4)
ros2 run robot_control_node robot_control_node

# 5. [선택] 실시간 비전 모니터링 (Terminal 5)
ros2 run rqt_image_view rqt_image_view
```

## 👥 팀원 및 역할 분배 (Team & Roles)
### AI 모델 개발 (Model)

- 데이터 전처리/증강 가이드라인 설계 및 AIHub 데이터 정제 (승현: 0~124 / 성현: 1000~1124 / 범진: 2000~2124 / 세교: 3000~3124)

- YOLO 모델 파인 튜닝, 성능 평가 지표(mAP, IoU) 분석 및 경량화 최적화

### 하드웨어 및 인프라 (HW/Cloud)

- 비전 카메라 센서 셋업 및 데이터 수집

- ROS2 프레임워크 기반 SO-ARM 101 액추에이터 제어 및 공간 좌표 변환(Homography) 궤적 설계

### 풀스택 및 인터페이스 (Full-Stack)

- 실시간 비전 추론 스트리밍 대시보드 웹 개발

- 상태 피드백 제어 인터페이스 및 데이터 로그 모니터링 구축


## 🌿 브랜치 전략 및 협업 규칙 (Git Flow)

### 📌 브랜치 운영 규칙

1. main (최종 배포용)

    - 언제든 시연 및 출시 가능한 수준의 가장 안정적인 코드만 관리합니다.

    - 모든 팀원은 이 브랜치에 직접 Push할 수 없습니다.

2. development (개발 통합용)

    - 각 파트별 기능 개발이 완료된 코드들이 모여 최종 통합 테스트를 거치는 공간입니다.

3. feature/기능명-#이슈번호 (단기 작업용)

    - 기능을 잘게 쪼개어 최대 1~2일 이내에 상위 브랜치로 병합(Merge)하는 것을 원칙으로 합니다.

    - 브랜치를 오래 유지하여 대형 충돌(Merge Conflict)이 발생하는 것을 방지합니다.

    - 예시: feature/ai-preprocess-#1, feature/ros2-control-#4

### 🤝 협업 워크플로우 (Workflow)

1. Issue 발행: 개발 시작 전, GitHub Issues에 작업할 내용을 등록하고 이슈 번호(예: #1)를 발급받습니다.

2. 브랜치 생성: development 브랜치로부터 파생된 개별 작업 브랜치를 생성합니다. (git checkout -b feature/기능명-#이슈번호)

3. Pull Request (PR) 및 코드 리뷰:

    - 코드 작성이 완료되면 development 브랜치를 향해 PR을 생성합니다.

    - 최소 1명 이상의 팀원에게 코드 리뷰를 받고 승인(Approve/LGTM)을 얻어야만 병합할 수 있습니다.
