# SO-ARM 101 평가 노드

YOLO 탐지 결과와 SO-ARM의 실제 관절 상태를 **관찰만** 하여 성능을 기록하는
ROS 2 패키지입니다. 로봇 이동 명령, trajectory, Action Goal 또는 Cancel을
발행하지 않습니다.

## 무엇을 측정하나요?

- YOLO 탐지 성공률과 클래스 정확도
- 실제 관절각을 FK로 변환한 그리퍼 위치
- 정답 GT XY와 FK XY 사이의 위치 오차 및 허용오차 통과율
- 반복 평가의 오차 분산과 실패 원인
- 클래스별 성능 및 PNG 요약 그래프

## 코드 구조

ROS 2 튜토리얼처럼 노드 파일 하나에 모든 기능을 넣을 수도 있지만, 이
패키지는 평가 상태, 키보드 입력, 그래프 생성을 따로 테스트할 수 있도록
역할별로 파일을 나눴습니다.

```text
evaluation_node/
├── evaluation_node.py   # ROS 2 구독/서비스/timer를 연결하는 실제 평가 노드
├── keyboard_node.py     # s/e/q 키 입력을 평가 서비스 호출로 바꾸는 노드
├── core.py              # ROS 없이 테스트 가능한 평가 회차 상태와 CSV/JSON 저장
├── config_loader.py     # 두 노드가 공유하는 evaluation.yaml 탐색/로딩
├── kinematics.py        # JointState를 평가용 FK XYZ 좌표로 변환
├── visualization.py     # 평가 종료 후 PNG 그래프 생성
└── keyboard_control.py  # 터미널 키 입력 처리와 TTY 복구
```

가장 중요한 흐름은 다음과 같습니다.

```text
evaluation_node.py  ── ROS 메시지/서비스 수신
        │
        ▼
core.py             ── 회차 시작/종료, 실패 사유, 결과 파일 저장
```

따라서 `core.py`는 별도 ROS 노드가 아니라, `evaluation_node.py`가 사용하는
순수 Python 평가 로직입니다. 이 분리 덕분에 `rclpy`를 실행하지 않고도
단위 테스트에서 회차 상태와 결과 저장을 검증할 수 있습니다.

## 설계 의도

이 패키지의 핵심 아이디어는 **로봇을 제어하지 않고 관찰만 해서 평가한다**는
것입니다. 이미 동작 중인 detector와 SO-ARM 제어 노드가 있고, 평가 노드는 그
옆에서 결과만 기록합니다.

- 평가 노드는 로봇 이동 명령을 보내지 않습니다.
- detector 결과는 클래스 성공 여부 판단에만 사용합니다.
- 위치 평가는 카메라 픽셀이 아니라 실제 관절값에서 계산한 FK 좌표로 합니다.
- 회차 시작과 저장 시점은 작업자가 키보드로 정합니다.
- 결과 파일은 매 실행마다 새 폴더에 저장해 이전 평가를 덮어쓰지 않습니다.

이렇게 만든 이유는 평가 코드가 로봇 동작에 영향을 주지 않게 하고, 실패 원인을
탐지·위치·작업자 종료 시점으로 나누어 기록하기 위해서입니다.

## 동작 흐름

평가는 자동으로 정해진 횟수만큼 돌지 않습니다. 작업자가 `s`와 `e`를 누른
횟수가 곧 실제 평가 회차 수입니다.

```text
1. evaluation_node 실행
   └─ 설정 파일을 찾고 값이 유효한지 검사한다.

2. keyboard_node 실행
   └─ s/e/q 키를 평가 서비스 호출로 바꾼다.

3. s 입력
   └─ 새 회차를 시작하고 현재 목표 클래스/위치를 안내한다.

4. 탐지 결과 / 관절 상태 / 액션 피드백 관찰
   ├─ 탐지 결과가 들어오면 최고 점수 클래스를 기록한다.
   └─ gripper가 닫히는 순간의 관절값으로 FK 위치를 기록한다.

5. e 입력
   └─ 현재 회차를 results.csv 한 행으로 저장한다.

6. q 입력
   └─ 활성 회차가 있으면 폐기하고, 저장된 회차만 summary와 그래프로 분석한다.
```

`watchdog`는 시간이 지났다고 회차를 자동 저장하지 않습니다. 대신
`detection_timeout`, `operation_timeout` 같은 실패 사유만 활성 회차에
추가하고, 실제 CSV 저장은 작업자가 `e`를 눌렀을 때 수행합니다.

## 데이터가 기록되는 방식

한 회차는 다음 정보를 모아 `results.csv`의 한 행이 됩니다.

| 항목 | 기록 방식 |
|---|---|
| 목표 클래스/위치 | 설정 파일의 `target_classes`와 `positions`를 순환하며 안내 |
| 탐지 결과 | `/detection_results`의 모든 후보 결과 중 점수가 가장 높은 클래스 |
| 그립 위치 | `/follower/joint_states` 또는 액션 피드백에서 얻은 6축 관절값을 FK로 변환 |
| 위치 오차 | 설정된 GT XY와 FK XY 사이의 거리 |
| 실패 사유 | 탐지 시간 초과, 클래스 불일치, 위치 허용오차 초과, 수동 종료 시점 문제 등 |

`summary.json`은 저장된 CSV 행을 다시 요약한 파일이고, `run_state.json`은 실행
중 상태와 키보드 노드 발견 여부, 그래프 생성 상태를 확인하기 위한 파일입니다.

## 1. 설정

`config/evaluation.yaml`을 열고 한글 주석에 따라 다음 값만 실제 측정값으로
입력합니다.

1. `positions`: 위치 ID별 실제 GT X/Y 좌표(mm)
2. `position_tolerance_mm`: 위치 합격 기준
3. `position_warning_mm`: 그래프에만 표시하는 경고선
4. 실제 장비에서 확인한 그리퍼 임계값

값을 모두 확인한 후 아래 두 항목을 `true`로 바꿉니다.

```yaml
configuration_confirmed: true
thresholds_locked: true
```

평가 횟수는 설정하지 않습니다. 실제 `s` 입력 수만큼 회차가 생성됩니다.

## 2. 설치 및 빌드

```bash
cd ros2_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --packages-select evaluation_node
source install/setup.bash
```

Ubuntu 그래프 글꼴과 Matplotlib가 없다면 설치합니다.

```bash
sudo apt install python3-matplotlib fonts-nanum
```

## 3. 실행

먼저 detector, SO-ARM bringup 및 robot control 노드를 실행합니다. 그 다음 두
터미널에서 평가 노드를 실행합니다. 설정 경로 인자는 필요 없습니다.

### 터미널 1: 센서 관찰 및 결과 저장

```bash
source install/setup.bash
ros2 run evaluation_node evaluation_node
```

### 터미널 2: 키보드 입력

```bash
source install/setup.bash
ros2 run evaluation_node keyboard_node
```

## 4. 키 사용법

| 키 | 동작 |
|---|---|
| `s` | 새 회차를 시작합니다. 중복 `s`는 거부됩니다. |
| `e` | 현재 회차를 CSV 한 행으로 저장합니다. |
| `q` | 활성 회차를 폐기하고 저장된 회차를 분석한 뒤 종료합니다. |
| `Ctrl+C` | `q`와 같은 종료 절차를 수행합니다. |

`s`를 누른 뒤 객체를 배치해도 됩니다. 기본 탐지 대기시간은 30초이므로 그
안에 배치해야 합니다. 가장 안정적인 방법은 안내된 객체와 위치를 준비한 뒤
`s`를 누르고 즉시 배치하는 것입니다.

정상 운용 순서는 다음과 같습니다.

```text
NEXT 안내 확인 → s → 객체 배치 → YOLO/로봇 작업 확인 → e → 다음 회차
```

## 5. 시작되지 않을 때

다음 명령으로 원인을 확인합니다.

```bash
ros2 service call /evaluation/preflight std_srvs/srv/Trigger "{}"
```

주요 차단 사유는 다음과 같습니다.

| 사유 | 확인할 내용 |
|---|---|
| `configuration_not_confirmed` | YAML의 `configuration_confirmed` |
| `thresholds_not_locked` | final 평가의 `thresholds_locked` |
| `publisher_missing:/detection_results` | detector 노드 실행 여부 |
| `publisher_missing:/follower/joint_states` | SO-ARM 드라이버 실행 여부 |
| `valid_joint_state_missing` | 6개 관절 이름과 유효한 position 값 |
| `gripper_not_open` | 그리퍼 측정값과 open 임계값 |

## 6. 결과 파일

기본 출력 경로는 `/tmp/so_arm101_evaluation`입니다. 매 실행마다 UTC 시간이
포함된 새 폴더를 만들어 이전 결과를 보존합니다.

```text
/tmp/so_arm101_evaluation/
└── evaluation_YYYYMMDDTHHMMSS_ffffffZ/
    ├── results.csv
    ├── summary.json
    ├── run_state.json
    └── charts/
        ├── overall_summary.png
        ├── class_performance.png
        ├── trial_position_error.png
        ├── target_vs_fk.png
        ├── failure_reasons.png
        └── visualization_manifest.json
```

`q`로 폐기된 활성 회차는 CSV와 통계에 포함되지 않습니다.

## 7. ROS 인터페이스와 독립성

### 구독

- `/detection_results` (`vision_msgs/msg/Detection2DArray`)
- `/follower/joint_states` (`sensor_msgs/msg/JointState`)
- FollowJointTrajectory Action status 및 feedback 토픽

### 서비스

- `/evaluation/start_next_trial`
- `/evaluation/end_trial`
- `/evaluation/abort_trial`
- `/evaluation/stop_run`
- `/evaluation/status`
- `/evaluation/preflight`
- `/evaluation/record_grasp`
- `/evaluation/record_sort`
- `/evaluation/analyze`

모든 서비스 형식은 `std_srvs/srv/Trigger`입니다. 평가 패키지에는 로봇 제어
publisher와 FollowJointTrajectory Action client가 없습니다.

## 8. 테스트

```bash
cd ros2_ws
colcon test --packages-select evaluation_node
colcon test-result --verbose
```

브랜치별 인터페이스 선택 근거와 실제 장비에서 확인해야 할 값은
`docs/branch_compatibility.md`를 참고하세요.
