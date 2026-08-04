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
