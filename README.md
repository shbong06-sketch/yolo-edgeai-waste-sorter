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
* **데이터셋 구축:** AIHub 데이터를 활용한 **[금속 캔, 페트병, 스티로폼]** 3종 맞춤형 데이터셋 구축 (총 1,500장)
* **AI 모델 최적화:** 실시간 추론을 위한 경량화된 YOLO 객체 탐지 모델 학습 및 성능 확보

### 3. 추가 목표 (Stretch Goal)
* **시뮬레이션 및 실물 연동:** SO-ARM 101 로봇 팔과 소형 가상(Isaac Sim 등)/실물 컨베이어 벨트 연동
* **비전-행동(Vision-to-Action) 구현:** 카메라가 탐지한 쓰레기의 2D 픽셀 좌표를 로봇의 3D 공간 좌표계로 변환(Homography)하여 실시간 그리핑 및 지정 수거함 자동 분류 공정 구현

---

## ⚙️ 시스템 아키텍처 & 흐름도 (Architecture)

### [ 데이터/학습 파이프라인 (Offline) ]
```text
AIHub 데이터 수집 ──> 데이터 전처리/라벨링 ──> YOLO 모델 학습 ──> 경량화 모델 최적화 (.pt/.onnx)

[ 실시간 비전-행동 제어 루프 (Online) ]
Plaintext
컨베이어 벨트 구동 ──> 비전 카메라 스트리밍 ──> 이미지 프레임 입력 ──> YOLO 객체 탐지
                                                                          │ (클래스, 2D 좌표)
수거함 배치 완료 <── ROS2 로봇 팔 제어 <── 3D 공간 좌표 변환 (Homography) <──┘
하드웨어 및 소프트웨어 통합 레이어
레이어 (Layer)	구성 요소	데이터 흐름 및 역할
1. 입력단 (Input)	컨베이어 벨트, RGB 비전 카메라	벨트 위로 이동하는 폐기물 영상을 실시간(FPS)으로 캡처하여 스트리밍 데이터로 전송
2. 인지단 (Perception)	PC / 에지 디바이스 (YOLO Engine)	입력된 프레임에서 [금속 캔, 페트병, 스티로폼]을 탐지하고, 바운딩 박스의 중심점 픽셀 좌표 (x, y) 추출
3. 제어단 (Control)	좌표 변환 모듈, ROS2 프레임워크	카메라 2D 픽셀 좌표 (x, y)를 로봇 작업 공간의 3D 물리 좌표 (X, Y, Z)로 변환 후, 로봇 역기하학(Inverse Kinematics) 기반 궤적 생성
4. 구동단 (Action)	SO-ARM 101 마니퓰레이터	생성된 궤적을 따라 그리퍼를 이동하여 타겟을 집고(Gripping), 지정된 쓰레기 수거함 위치로 이동 및 분류
```

## 📂 프로젝트 구조 (Repository Structure)

```Plaintext
📦 yolo-edgeai-waste-sorter
 ┣ 📂 .github              # GitHub Actions 및 issue/PR 템플릿
 ┣ 📂 ai                   # 1. AI 모델 관련 (데이터 전처리, 학습, 추론)
 ┃ ┣ 📂 configs            # YOLO 학습 설정 파일 (data.yaml 등)
 ┃ ┣ 📂 src                # AI 핵심 소스 코드 (preprocess, train, inference)
 ┃ ┗ 📜 requirements.txt   # AI 패키지 의존성 파일 (PyTorch, Ultralytics 등)
 ┣ 📂 ros2_ws              # 2. 로봇 제어 관련 (ROS2 워크스페이스)
 ┃ ┗ 📂 src
 ┃   ┣ 📂 waste_sorting_bringup   # 전체 노드 실행 및 Launch 파일 패키지
 ┃   ┣ 📂 waste_detector_node     # YOLO 추론 결과를 받아 토픽으로 발행하는 노드
 ┃   ┗ 📂 robot_control_node      # 좌표 변환(Homography) 및 로봇 팔(IK) 제어 노드
 ┣ 📂 docs                 # 3. 문서 및 산출물 관리
 ┃ ┗ 📜 project_report.md  # 최종 수행 보고서
 ┗ 📜 .gitignore           # 대용량 데이터셋 및 모델 가중치(.pt, .onnx) 제외 설정
 ```

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
pip install -r requirements.txt
2. ROS2 로봇 제어 환경 설정 (Ubuntu 네이티브 환경 추천)
```
```Bash
# ROS2 워크스페이스 이동 및 언더레이 소싱
cd ros2_ws
source /opt/ros/humble/setup.bash  # 혹은 본인 ROS2 버전명

# 빌드 및 패키지 환경 적용
colcon build
source install/setup.bash
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
