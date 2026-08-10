# ♻️ YOLO 기반 에지 AI 쓰레기 자동 분류 시스템
> **YOLO-Based Edge AI Automated Waste Sorting System with SO-ARM 101**

본 프로젝트는 스마트 팩토리 및 자동화 공정의 재활용 분리수거 수작업 의존도 문제를 해결하기 위해 **비전 AI(YOLO)**와 **로봇 공학(ROS2)**을 결합한 자동 선별 시스템입니다.

카메라 피드를 통해 실시간으로 유입되는 폐기물을 에지 디바이스 환경에서 고속으로 탐지하고, 로봇 마니퓰레이터(SO-ARM 101)와 연동하여 지정된 수거함으로 자동 분류하는 완전 자동화 공정 프로세스를 구현합니다.

---

## 🗺️ 저장소 둘러보기 (Repository Map)

프로젝트는 4개의 파트로 구성되어 있으며, 각 파트는 독립된 워크스페이스와 문서를 가집니다. 아래 표에서 해당 파트로 바로 이동할 수 있습니다.

| 파트 | 경로 | 담당 | 핵심 내용 | 상세 문서 |
|---|---|---|---|---|
| 1️⃣ AI 모델 | [`AI/`](./AI/) | 봉승현 | 데이터셋 구축, YOLO 학습·실험, 경량화·배포 | [AI/docs](./AI/docs/) |
| 2️⃣ ROS2 실물 파이프라인 | [`ros2_ws/`](./ros2_ws/) | 박성현 | 카메라·탐지·제어·평가 노드 | [ros2_ws/README.md](./ros2_ws/README.md) |
| 3️⃣ 시뮬레이션 | [`wsSIM/`](./wsSIM/) | 한세교 | Isaac Sim 기반 SO-ARM101 제어 | [wsSIM/README.md](./wsSIM/README.md) |
| 4️⃣ 프로젝트 문서 | [`docs/`](./docs/) | 봉승현 | 제안서·최종 보고서 | [docs/](./docs/) |

각 파트의 세부 항목과 소스 파일 연결은 아래 [파트별 구성](#파트별-구성-part-by-part)에서 확인할 수 있습니다.

---

## 🎯 프로젝트 개요 & 목표 (Objectives)

### 1. 문제 정의
- 스마트 팩토리 및 자동화 공정에서 재활용품 분리수거는 여전히 수작업 의존도가 높고 비용이 많이 드는 영역입니다.
- 작업자의 안전 문제와 구인난을 해결하기 위해, 비전 AI와 로봇 공학을 결합한 고속 자동 선별 시스템의 도입이 시급합니다.

### 2. 핵심 목표 (MVP)
- **데이터셋 구축:** AIHub 데이터를 활용한 **[금속 캔, 페트병, 스티로폼]** 3종 맞춤형 데이터셋 구축 (총 9,999장)
- **AI 모델 최적화:** 실시간 추론을 위한 경량화된 YOLO 객체 탐지 모델 학습 및 성능 확보 → 최종 **yolo11n (mAP50-95 0.898)**

### 3. 추가 목표 (Stretch Goal)
- **시뮬레이션 및 실물 연동:** SO-ARM 101 로봇 팔과 가상(Isaac Sim) 실험 환경 연동
- **비전-행동(Vision-to-Action) 구현:** 카메라가 탐지한 쓰레기의 2D 픽셀 좌표를 로봇의 3D 공간 좌표계로 변환(Homography)하여 실시간 그리핑 및 지정 수거함 자동 분류 공정 구현

---

## ⚙️ 시스템 아키텍처 & 흐름도 (Architecture)

### [ 데이터/학습 파이프라인 (Offline) ]
```text
AIHub 데이터 수집 ──> 전처리·라벨링 ──> YOLO 모델 학습 ──> 오류 분석(HNM) ──> 경량화 배포 (.pt / .onnx)
                         │                  │                  │                 │
                   AI/src/preprocessing  AI/src/training   AI/src/analysis   AI/src/training
                   build_dataset.py      train.py          error_analysis.py export_onnx.py
```

### [ 실시간 비전-행동 제어 루프 (Online) ]
```text
 폐기물 영상 ────> 비전 카메라 ────> 카메라 노드 ────> YOLO 탐지 노드 ─────────────────────
                                       camera_node         detector_node          │
                                      (Compressed)        (Detection2DArray)      │
                                                                                  ▼
                타겟 파지 <──── SO-ARM101 제어 <──── 호모그래피·IK 변환 <──── (클래스, 2D 픽셀 좌표)
               robot_control_node    robot_control_node    robot_control_node
               (FollowJointTrajectory Action)
```

| 레이어 (Layer) | 구성 요소 | 역할 |
|---|---|---|
| 1. 입력단 (Input) | RGB 비전 카메라 | 정지된 폐기물 영상을 실시간(FPS)으로 캡처·스트리밍 |
| 2. 인지단 (Perception) | 에지 디바이스 (YOLO Engine) | [금속 캔, 페트병, 스티로폼] 탐지 및 바운딩 박스 중심 픽셀 좌표 추출 |
| 3. 제어단 (Control) | 좌표 변환 모듈, ROS2 프레임워크 | 2D 픽셀 → 로봇 3D 물리 좌표(Homography) 변환 후 역기구학(IK) 기반 궤적 생성 |
| 4. 구동단 (Action) | SO-ARM 101 마니퓰레이터 | 궤적을 따라 그리퍼로 타겟 파지 |

---

## 파트별 구성 (Part by Part)

### 1️⃣ AI 모델 (Part 1) — [`AI/`](./AI/)

데이터셋 구축부터 모델 학습, 오류 분석, ONNX 경량화·배포까지의 AI 파이프라인입니다. 파이프라인 전체 로그는 [AI/docs/](./AI/docs/)에서 확인할 수 있습니다.

| 단계 | 소스 코드 | 상세 문서 |
|---|---|---|
| 데이터셋 구축 | [`build_dataset.py`](./AI/src/preprocessing/build_dataset.py) · [`sample_dataset.py`](./AI/src/preprocessing/sample_dataset.py) | [dataset.md](./AI/docs/dataset.md) |
| 전처리 / 증강 | [`preprocess.py`](./AI/src/preprocessing/preprocess.py) · [`preprocess_fast.py`](./AI/src/preprocessing/preprocess_fast.py) · [`fix_jpeg.py`](./AI/src/preprocessing/fix_jpeg.py) | [dataset.md](./AI/docs/dataset.md) |
| 모델 학습 | [`train.py`](./AI/src/training/train.py) | [experiment_log.md](./AI/docs/experiment_log.md) |
| 오류 분석 / HNM | [`error_analysis.py`](./AI/src/analysis/error_analysis.py) · [`generate_hnm_dataset.py`](./AI/src/analysis/generate_hnm_dataset.py) · [`count_overlap.py`](./AI/src/analysis/count_overlap.py) | [model_improvement.md](./AI/docs/model_improvement.md) |
| 실시간 추론 | [`detect_realtime.py`](./AI/src/inference/detect_realtime.py) | [week01_progress.md](./AI/docs/week01_progress.md) |
| ONNX 변환·양자화 | [`export_onnx.py`](./AI/src/training/export_onnx.py) | [deployment.md](./AI/docs/deployment.md) |
| 호모그래피 캘리브레이션 | [`calibrate_homography.py`](./AI/src/inference/calibrate_homography.py) | [deployment.md](./AI/docs/deployment.md) |

**최종 모델: yolo11n** (Hard Negative Mining 적용)

| 지표 | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| Baseline (yolo11n) | 0.8121 | 0.8164 | 0.8719 | 0.8066 |
| **최종 (HNM 적용)** | **0.917** | **0.898** | **0.957** | **0.898** |

> 최종 성능 및 클래스별 결과는 [model_improvement.md](./AI/docs/model_improvement.md) 참고

---

### 2️⃣ ROS2 실물 파이프라인 (Part 2) — [`ros2_ws/`](./ros2_ws/)

실물 SO-ARM101을 구동하는 ROS2 (Jazzy) 워크스페이스입니다. 카메라 → 탐지 → 호모그래피·IK 제어 → 평가 순서로 노드가 독립 패키지로 구성됩니다. 상세 내용은 [ros2_ws/README.md](./ros2_ws/README.md)를 참고하세요.

| 패키지 | 노드 | 역할 | 토픽/액션 |
|---|---|---|---|
| [`camera_node_pkg`](./ros2_ws/src/camera_node_pkg/) | camera_node | USB 카메라 영상을 JPEG 압축 발행 | `/camera/image_raw` (CompressedImage) |
| [`detector_node_pkg`](./ros2_ws/src/detector_node_pkg/) | detector_node | YOLO(pt/onnx) 멀티스레드 추론 (프레임 스킵) | `/detection_results` (Detection2DArray) |
| [`robot_control_node`](./ros2_ws/src/robot_control_node/) | robot_control_node | 호모그래피·IK 연산 및 상태머신 기반 순차 제어 | `/follower/joint_trajectory_controller/follow_joint_trajectory` (Action) |
| [`evaluation_node`](./ros2_ws/src/evaluation_node/) | evaluation_node · keyboard_node | 관찰 기반 성능 평가 및 그래프 생성 | `/evaluation/*` (Service) |

부가 도구:
- **호모그래피 캘리브레이션**: [`make_homography.py`](./ros2_ws/make_homography.py) — 픽셀 ↔ 로봇 좌표 변환 행렬(`homography_matrix.npy`) 생성
- **모델 가중치**: `best.pt` / `best.onnx` / `best_int8.onnx`

```text
camera_node ──/camera/image_raw(CompressedImage)──> detector_node
                                                       │ /detection_results(Detection2DArray)
                                                       ▼
                                   robot_control_node (호모그래피 → IK → 상태머신)
                                                       │ FollowJointTrajectory Action
                                                       ▼
                                               SO-ARM101 (실물 드라이버)
```

---

### 3️⃣ 시뮬레이션 (Part 3) — [`wsSIM/`](./wsSIM/)

Isaac Sim 기반 SO-ARM101 시뮬레이션 워크스페이스입니다. Mock 탐지 → 픽셀 매핑 → FK/IK → 6축 MoveJoints 액션 → Isaac Sim 이동까지 구현되어 있습니다. 상세 내용은 [wsSIM/README.md](./wsSIM/README.md)를 참고하세요.

| 패키지 | 역할 |
|---|---|
| [`so_arm101_control_pkg`](./wsSIM/src/so_arm101_control_pkg/) | MockDetector · FK/IK · MoveJoints Action Client/Server 노드 |
| [`so_arm101_description`](./wsSIM/src/so_arm101_description/) | SO-ARM101 URDF 및 STL mesh |
| [`so_arm101_interface_pkg`](./wsSIM/src/so_arm101_interface_pkg/) | `MoveJoints.action` 인터페이스 정의 |

> 설계 로직·시나리오·개발항목은 [`wsSIM/_docs/`](./wsSIM/_docs/)에서 확인할 수 있습니다.
> 전체 시나리오 진행률: **48/94 (51%)** — 기본 이동 파이프라인 구현 단계

---

### 4️⃣ 프로젝트 문서 (Part 4) — [`docs/`](./docs/)

| 문서 | 설명 |
|---|---|
| [`project_proposal.md`](./docs/project_proposal.md) | 프로젝트 제안서 (개요, 문제 정의, MVP/Stretch 목표) |
| [`project_report.md`](./docs/project_report.md) | 최종 수행 보고서 (시스템 설계, 구현, 결과) |

> 참고: `references/` (회의록, 계획서 등)는 `.gitignore` 대상으로 저장소에 포함되지 않습니다.

---

## 📊 데이터셋 (Dataset)

| 구분 | 내용 |
|---|---|
| 전체 | 9,999장 (train 7,999 / val 2,000, 80:20 split) |
| 클래스 | Can (3,333), Pet bottle (3,333), Styrofoam (3,333) |
| 출처 | AIHub 선별영상 추출 이미지 9,000장 + 직접 촬영 999장 ([AIHub 링크](https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&aihubDataSe=data&dataSetSn=71362)) |
| 해상도 | 640×640 (YOLO 입력 기준) |
| 라벨 포맷 | YOLO format (`class_id x_center y_center width height`) |

| Class | Train | Val | Total |
|---|---|---|---|
| Can | 2,667 | 666 | 3,333 |
| Pet bottle | 2,666 | 667 | 3,333 |
| Styrofoam | 2,666 | 667 | 3,333 |
| **Total** | **7,999** | **2,000** | **9,999** |

> 상세 데이터 명세는 [AI/docs/dataset.md](./AI/docs/dataset.md) 참고

> HNM 재학습용 하드 네거티브 데이터셋은 [model_improvement.md](./AI/docs/model_improvement.md) 참고

> 다운로드 링크 : [yolo_waste_dataset_v3.0.zip](https://drive.google.com/file/d/1YwxGctreCivOjuJ5DvqFp6z17AK1IuOL/view?usp=drive_link) [hnm_dataset.zip](https://drive.google.com/file/d/1qLXKsI64R1wKvXUHEHsLN9n1poKLQCxC/view?usp=drive_link)
---

## 🛠️ 기술 스택 (Tech Stack)

- **AI / Data**: PyTorch, Ultralytics (yolov8n · yolo11n), ONNX Runtime (FP32/INT8), OpenCV, NumPy, Pandas, Matplotlib
- **Robotics / HW**: ROS2 Jazzy, Isaac Sim, Python-Serial (로봇 팔 통신), SO-ARM101
- **배포 환경**: Ubuntu 24.04, Python 3.10, CUDA, ultralytics 8.4.87
- **Collaboration**: GitHub, Slack

---

## 🚀 시작하기 (Setup & Installation)

가상환경 충돌을 예방하기 위해 파트별로 환경을 분리하여 터미널을 실행해 주세요.

### 1. AI 모델 환경
```bash
# AI 폴더 이동 및 가상환경 생성
cd AI
conda create -n env_sorter_ai python=3.10 -y
conda activate env_sorter_ai

# 의존성 패키지 설치
pip install -r requirements.txt
```

### 2. ROS2 실물 파이프라인 환경 (Ubuntu 네이티브 추천)
```bash
# ROS2 워크스페이스 이동 및 언더레이 소싱
cd ros2_ws
source /opt/ros/jazzy/setup.bash

# 가상환경 생성 후 빌드 도구 설치
python3 -m venv .venv
source .venv/bin/activate
pip install colcon-common-extensions

# 빌드 및 패키지 환경 적용
colcon build
source install/setup.bash
```

### 3. 시뮬레이션 환경
```bash
cd wsSIM
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

---

## ▶️ 실행 흐름 (Run Pipeline)

```bash
# 1. 카메라 노드
ros2 run camera_node_pkg camera_node

# 2. 객체 탐지 노드 (별도 터미널)
ros2 run detector_node_pkg detector_node

# 3. 로봇 제어 노드 (별도 터미널, 실물 연결 시)
ros2 run robot_control_node robot_control_node

# 4. 평가 노드 + 키보드 노드 (별도 터미널 2개, 선택)
ros2 run evaluation_node evaluation_node --ros-args \
  -p config_path:=src/evaluation_node/config/evaluation.yaml
ros2 run evaluation_node keyboard_node
```

> 시뮬레이션 실행 방법은 [wsSIM/README.md](./wsSIM/README.md)의 "실행" 섹션을 참고하세요.
> ONNX 모델 생성/변환은 [AI/docs/deployment.md](./AI/docs/deployment.md)를 참고하세요.

---

## 👥 팀원 및 역할 분배 (Team & Roles)

| 성명 | 역할 | 담당 업무 |
|---|---|---|
| 봉승현 | 팀장 / AI | 데이터 분석, YOLO 모델 학습·최적화, ROS2 노드(카메라, 객체 탐지) 설계, 문서화 |
| 박성현 | 팀원 / ROS, HW | ROS2 노드 설계, 통신 및 제어, 카메라/에지 디바이스 구성, 하드웨어 연동 |
| 한세교 | 팀원 / Simulation | 시뮬레이션 환경 구축, 테스트, 통신, 시뮬레이션 연동 |
| 민범진 | 팀원 / 평가 | ROS2 노드(평가 자동화) 설계 |

---

## 🌿 브랜치 전략 및 협업 규칙

### 📌 브랜치 운영 규칙

1. **main** (최종 배포용)
   - 언제든 시연 및 출시 가능한 수준의 가장 안정적인 코드만 관리합니다.
   - 모든 팀원은 이 브랜치에 직접 Push할 수 없습니다.

2. **development** (개발 통합용)
   - 각 파트별 기능 개발이 완료된 코드들이 모여 최종 통합 테스트를 거치는 공간입니다.

3. **feature/기능명-#이슈번호** (단기 작업용)
   - 기능을 잘게 쪼개어 최대 1~2일 이내에 상위 브랜치로 병합(Merge)하는 것을 원칙으로 합니다.
   - 브랜치를 오래 유지하여 대형 충돌(Merge Conflict)이 발생하는 것을 방지합니다.
   - 예시: `feature/ai-preprocess-#1`, `feature/ros2-control-#4`

### 🤝 협업 워크플로우 (Workflow)

1. **브랜치 생성**: development 브랜치로부터 파생된 개별 작업 브랜치를 생성합니다. (`git checkout -b feature/기능명-#이슈번호`)
2. **Pull Request (PR) 및 코드 리뷰**:
   - 코드 작성이 완료되면 development 브랜치를 향해 PR을 생성합니다.
   - 최소 1명 이상의 팀원에게 코드 리뷰를 받고 승인(Approve/LGTM)을 얻어야만 병합할 수 있습니다.