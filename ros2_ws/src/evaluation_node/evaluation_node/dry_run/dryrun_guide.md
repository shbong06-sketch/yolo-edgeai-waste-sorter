# Evaluation Node Dry-run 가이드

## 경로 표기 규칙

이 문서에서는 사용자와 설치 환경에 따라 달라지는 경로를 다음과 같이 표시한다.

| 표기 | 의미 |
|---|---|
| `<워크스페이스>` | `yolo-edgeai-waste-sorter` 프로젝트 루트의 실제 경로 |
| `<설정_파일_경로>` | 사용할 설정 파일이 들어 있는 디렉터리 경로 |
| `<결과_경로>` | 평가 결과를 저장할 디렉터리 경로 |

꺾쇠를 포함한 표기는 설명용이므로 명령에 그대로 입력하지 않는다. 예를 들어
프로젝트가 `/data/yolo-edgeai-waste-sorter`에 있다면:

```bash
cd <워크스페이스>/ros2_ws
```

를 다음처럼 실제 경로로 바꿔 실행한다.

```bash
cd /data/yolo-edgeai-waste-sorter/ros2_ws
```

## 1. 목적

`dry_run`은 실제 카메라, YOLO 모델, SO-ARM 드라이버 없이 `evaluation_node`의
위치 오차 판정과 결과 저장·시각화 과정을 확인하기 위한 모의 평가 노드다.

기존 `evaluation_node`의 구독 및 평가 흐름을 우회하지 않는다. 대신 실제 장비가
발행해야 하는 다음 토픽에 형식이 유효한 모의 메시지를 발행한다.

- `/detection_results` (`vision_msgs/msg/Detection2DArray`)
- `/follower/joint_states` (`sensor_msgs/msg/JointState`)

또한 다음 평가 서비스를 순서대로 호출해 총 9개 회차를 자동 실행한다.

- `/evaluation/start_next_trial`
- `/evaluation/end_trial`
- `/evaluation/stop_run`
- `/evaluation/analyze`

따라서 dry-run에서는 `keyboard_node`를 실행하거나 `s`, `e`, `q`를 누를 필요가
없다.

## 2. 관련 파일 구조

dry-run 구현과 문서는 다음 소스 경로의 Python 하위 패키지에 함께 배치되어
있다.

```text
<워크스페이스>/ros2_ws/src/evaluation_node/evaluation_node/dry_run/
```

```text
<워크스페이스>/
└── ros2_ws/
    └── src/
        └── evaluation_node/
            ├── config/
            │   └── evaluation.yaml       # GT 위치와 평가 임계값
            ├── evaluation_node/
            │   ├── dry_run/
            │   │   ├── __init__.py       # dry-run 공개 클래스·함수 정의
            │   │   ├── dry_run.py        # 모의 토픽과 9회 자동 평가 구현
            │   │   └── dryrun_guide.md   # 현재 문서
            │   ├── evaluation_node.py    # 실제 평가·저장 ROS 노드
            │   ├── config_loader.py      # evaluation.yaml 탐색 및 로딩
            │   ├── core.py               # 회차 상태와 오차 판정
            │   ├── kinematics.py         # 관절값 기반 FK 계산
            │   └── visualization.py      # 평가 그래프 생성
            ├── launch/
            │   └── dryrun.launch.py      # evaluation_node와 dry_run 동시 실행
            ├── test/
            │   └── test_dry_run.py       # 오차 구간 및 FK 역산 테스트
            ├── package.xml               # ROS 실행 의존성
            └── setup.py                  # Python 패키지·실행 엔트리포인트
```

주요 파일의 현재 경로는 다음과 같다.

| 파일 | 현재 소스 경로 |
|---|---|
| 구현 | `<워크스페이스>/ros2_ws/src/evaluation_node/evaluation_node/dry_run/dry_run.py` |
| 가이드 | `<워크스페이스>/ros2_ws/src/evaluation_node/evaluation_node/dry_run/dryrun_guide.md` |
| 패키지 초기화 | `<워크스페이스>/ros2_ws/src/evaluation_node/evaluation_node/dry_run/__init__.py` |
| launch | `<워크스페이스>/ros2_ws/src/evaluation_node/launch/dryrun.launch.py` |
| 테스트 | `<워크스페이스>/ros2_ws/src/evaluation_node/test/test_dry_run.py` |
| 설정 | `<워크스페이스>/ros2_ws/src/evaluation_node/config/evaluation.yaml` |

파일 이동으로 Python 모듈 경로는 다음처럼 변경되었다.

```text
이전: evaluation_node.dry_run
현재: evaluation_node.dry_run.dry_run
```

`setup.py`가 현재 모듈의 `main()`을 `dry_run` 실행 파일로 등록하므로 사용자 실행
명령은 바뀌지 않는다.

```bash
ros2 run evaluation_node dry_run
```

launch의 executable 이름과 토픽·서비스 이름도 기존과 동일하다.

## 3. 사전 설정

다음 경로의 설정 파일에서 최소한 아래 값을 확인한다.

```text
<워크스페이스>/ros2_ws/src/evaluation_node/config/evaluation.yaml
```

아래 값은 dry-run 동작과 그래프 구간을 확인하기 위해 입력한 **임의의 예시값**이다.
실제 로봇의 위치 정확도나 장비 임계값으로 사용하면 안 된다. 실물 평가 전에는
반드시 작업 환경에서 측정한 값으로 수정하고 담당자가 확인해야 한다.

```yaml
configuration_confirmed: true
thresholds_locked: true

positions:
  P01:
    x_mm: 122.0
    y_mm: 84.5

position_warning_mm: 7.0
position_tolerance_mm: 10.0

cooldown_sec: 3.0
gripper_open_threshold: 3.5
gripper_closed_threshold: 3.0
```

실물 평가 전에 반드시 실측값으로 교체할 항목은 다음과 같다.

- `positions.*.x_mm`, `positions.*.y_mm`: 객체 배치 위치별 실제 GT 좌표
- `position_warning_mm`: 위치 오차를 조기에 확인할 경고 기준
- `position_tolerance_mm`: 최종 위치 합격 기준
- `gripper_open_threshold`: 실제 관절 피드백에서 확인한 열린 그리퍼 기준
- `gripper_closed_threshold`: 실제 관절 피드백에서 확인한 닫힌 그리퍼 기준

`configuration_confirmed`와 `thresholds_locked`는 위 값을 입력했다는 의미가 아니라,
실측과 검토가 끝났음을 작업자가 명시적으로 확인하는 잠금값이다. 실제 값이 확정되기
전에는 둘 다 `false`로 유지하고, dry-run 예시를 실행할 때만 의도를 확인한 뒤
임시로 `true`로 바꾼다.

다음 조건을 만족해야 한다.

- `positions`에 하나 이상의 유효한 GT XY 좌표가 있어야 한다.
- `position_tolerance_mm`은 0보다 커야 한다.
- `position_warning_mm`은 0 이상이고 `position_tolerance_mm` 이하여야 한다.
- 기본 `gripper_open=4.0`은 `gripper_open_threshold` 이상이어야 한다.
- 기본 `gripper_closed=2.7`은 `gripper_closed_threshold` 이하여야 한다.

## 4. 빌드

다음 파일처럼 launch, Python 패키지 구조 또는 `setup.py`를 변경한 경우 다시
빌드한다.

```text
<워크스페이스>/ros2_ws/src/evaluation_node/launch/dryrun.launch.py
<워크스페이스>/ros2_ws/src/evaluation_node/evaluation_node/dry_run/dry_run.py
<워크스페이스>/ros2_ws/src/evaluation_node/setup.py
```

```bash
cd <워크스페이스>/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select evaluation_node --symlink-install
source install/setup.bash
```

설치된 실행 파일과 launch 파일은 다음 명령으로 확인할 수 있다.

```bash
ros2 pkg executables evaluation_node
ls install/evaluation_node/share/evaluation_node/launch/
```

## 5. 권장 실행 방법: launch 한 번으로 실행

`dryrun.launch.py`는 `evaluation_node`와 `dry_run`을 함께 실행한다.

```bash
source /opt/ros/jazzy/setup.bash
source <워크스페이스>/ros2_ws/install/setup.bash
ros2 launch evaluation_node dryrun.launch.py
```

launch는 실행 위치와 무관하게 현재 오버레이 워크스페이스의 `tmp`를 기본 결과
경로로 사용한다.

```text
<워크스페이스>/ros2_ws/tmp/evaluation_YYYYMMDDTHHMMSS_ffffffZ/
```

다른 결과 경로를 사용하려면 launch 인자를 전달한다.

```bash
ros2 launch evaluation_node dryrun.launch.py \
  output_directory:=<결과_경로>
```

다른 평가 설정 파일을 사용하려면 두 노드가 동일한 파일을 읽도록 launch 인자를
전달한다.

```bash
ros2 launch evaluation_node dryrun.launch.py \
  config_path:=<설정_파일_경로>/evaluation.yaml
```

실행 초기에 `evaluation_node`가 "키보드 제어 노드를 실행하세요"라고 안내할 수
있다. 일반 실행을 위한 고정 로그이므로 dry-run에서는 무시해도 된다.

## 6. 개별 실행 방법

문제를 진단할 때는 두 노드를 별도 터미널에서 실행할 수 있다.

터미널 1:

```bash
source /opt/ros/jazzy/setup.bash
source <워크스페이스>/ros2_ws/install/setup.bash
ros2 run evaluation_node evaluation_node
```

터미널 2:

```bash
source /opt/ros/jazzy/setup.bash
source <워크스페이스>/ros2_ws/install/setup.bash
ros2 run evaluation_node dry_run
```

이 방식에서는 `evaluation_node`가 YAML의 `output_directory`를 사용한다. 필요하면
직접 ROS 파라미터로 덮어쓸 수 있다.

YAML의 `output_directory`가 상대경로이면 `ros2 run`을 입력한 터미널의 현재
디렉터리(`pwd`)를 기준으로 해석된다. 예를 들어 다음처럼 설정하고:

```yaml
output_directory: tmp
```

다음 위치에서 실행하면:

```bash
cd <워크스페이스>/ros2_ws
ros2 run evaluation_node evaluation_node
```

결과는 아래에 생성된다.

```text
<워크스페이스>/ros2_ws/tmp/evaluation_YYYYMMDDTHHMMSS_ffffffZ/
```

같은 명령을 다른 디렉터리에서 실행하면 그 디렉터리 아래의 `tmp`가 사용된다.
즉, 단독 실행의 상대경로는 source한 워크스페이스가 아니라 실행 직전 `pwd`를
기준으로 한다.

반대로 YAML 값이 `/tmp/so_arm101_evaluation` 같은 절대경로라면 터미널 실행
위치와 무관하게 해당 절대경로를 사용한다. launch 실행은 YAML 값을 덮어쓰므로
앞 절에서 설명한 `<워크스페이스>/ros2_ws/tmp`를 사용한다.

```bash
ros2 run evaluation_node evaluation_node --ros-args \
  -p output_directory:=<결과_경로>
```

## 7. 생성되는 9개 위치 오차

dry-run은 YAML의 경고값과 허용오차를 이용해 세 구간의 데이터를 각각 3개씩
생성한다.

| 구간 | 생성 기준 | 의미 |
|---|---:|---|
| 통과(`pass`) | `error <= warning` | 경고선 안쪽의 안정적인 통과 |
| 경고(`warning`) | `warning < error <= tolerance` | 최종 통과지만 경고선에 근접 |
| 불합격(`fail`) | `error > tolerance` | 위치 허용오차 초과 |

예를 들어 다음 설정에서는:

```yaml
position_warning_mm: 7.0
position_tolerance_mm: 10.0
```

다음 오차가 만들어진다.

- 통과: `1.75`, `3.50`, `5.25` mm
- 경고: `7.75`, `8.50`, `9.25` mm
- 불합격: `11.00`, `12.50`, `15.00` mm

9개 케이스는 `random_seed`로 순서가 섞인다. 기본 seed `101`에서는 다음 순서가
재현된다.

```text
fail(11.00), fail(12.50), pass(5.25), pass(3.50),
warning(8.50), pass(1.75), fail(15.00),
warning(9.25), warning(7.75)
```

주의: `position_warning_mm`은 평가 CSV에 별도의 합격/불합격 상태를 만들지 않는다.
`position_pass`는 오직 `position_tolerance_mm`을 기준으로 계산한다. 따라서
`warning` 데이터도 CSV에서는 `position_pass=True`이고, 경고 구간은 위치 오차
그래프의 경고선과 허용오차선 사이에서 확인한다.

## 8. 모의 관절 데이터 생성 방식

각 회차에서 현재 GT 좌표의 X축 방향으로 목표 오차만큼 이동한 XY를 만든다.

```text
dry-run 목표 XY = (GT x_mm + error_mm, GT y_mm)
```

`joints_for_xy()`는 이 XY가 `evaluation_node`의 순기구학 결과로 다시 계산되도록
6개 관절값을 역산한다. 생성된 값은 다음 이름 순서의 `JointState`로 발행된다.

```text
shoulder_pan
shoulder_lift
elbow_flex
wrist_flex
wrist_roll
gripper
```

대기 상태에서는 열린 그리퍼 값을, 활성 회차에서는 닫힌 그리퍼 값을 발행한다.

```text
warmup/cooldown: gripper_open=4.0
capturing:        gripper_closed=2.7
```

그 결과 사전점검에서는 열린 그리퍼로 인식되고, 활성 회차에서는 닫힌 순간의
관절값으로 FK 위치가 캡처된다.

## 9. 자동 실행 상태 흐름

dry-run은 `phase` 상태에 따라 다음 순서로 동작한다.

```text
warmup
  열린 그리퍼와 두 모의 토픽을 1초간 발행
  -> start_next_trial

capturing
  탐지 결과와 닫힌 그리퍼 관절값을 settle_sec 동안 발행
  -> end_trial

cooldown
  열린 그리퍼를 발행하며 YAML의 cooldown_sec + 0.2초 대기
  -> 남은 케이스가 있으면 다음 start_next_trial
  -> 9개가 끝났으면 stop_run

stopped
  -> analyze

done
  결과 및 그래프 생성 완료, 추가 동작 없이 대기
```

`pending`에는 현재 응답을 기다리는 비동기 서비스 Future가 저장된다. 값이 있는
동안에는 다음 서비스 요청을 보내지 않아 타이머에 의한 중복 호출을 방지한다.

## 10. dry-run 파라미터

| 파라미터 | 기본값 | 용도 |
|---|---:|---|
| `config_path` | 빈 문자열 | 사용할 `evaluation.yaml`; 비우면 기본 탐색 규칙 사용 |
| `publish_rate_hz` | `10.0` | 두 모의 토픽의 초당 발행 횟수 |
| `random_seed` | `101` | 9개 케이스의 재현 가능한 배치 순서 |
| `settle_sec` | `0.6` | 회차 시작 후 모의 입력을 수집하는 시간 |
| `gripper_open` | `4.0` | 사전점검을 통과시킬 열린 그리퍼 값 |
| `gripper_closed` | `2.7` | FK 위치 캡처를 유도할 닫힌 그리퍼 값 |

개별 실행 시 파라미터 변경 예:

```bash
ros2 run evaluation_node dry_run --ros-args \
  -p random_seed:=200 \
  -p publish_rate_hz:=5.0 \
  -p settle_sec:=1.0
```

launch에서 이 값을 바꾸려면 해당 launch argument와 dry-run 노드 parameter 연결을
`dryrun.launch.py`에 추가해야 한다. 현재 launch가 외부에 노출하는 인자는
`config_path`와 `output_directory`이다.

## 11. 정상 로그

정상 시작 시 두 프로세스가 모두 표시된다.

```text
[evaluation_node-1]: process started
[dry_run-2]: process started
```

dry-run은 시작할 때 배치 순서를 출력하고 회차마다 저장 결과를 출력한다.

```text
DRY RUN: 임의 데이터로 9회 평가를 자동 수행합니다.
무작위 배치: 1:fail(...), 2:fail(...), ...
1/9 저장: fail, 목표 오차=11.00 mm
...
9/9 저장: warning, 목표 오차=7.75 mm
9회 일괄 평가와 그래프 생성이 완료되었습니다.
```

`done` 상태에서는 dry-run 프로세스가 대기하므로 로그 확인 후 `Ctrl+C`로 launch를
종료할 수 있다.

## 12. 결과 확인

launch 기본 경로를 사용했다면 최신 실행 폴더를 확인한다.

```bash
cd <워크스페이스>/ros2_ws
latest_run=$(ls -dt tmp/evaluation_* | head -1)
echo "$latest_run"
```

생성 파일:

```text
results.csv
summary.json
run_state.json
charts/
  overall_summary.png
  class_performance.png
  trial_position_error.png
  target_vs_fk.png
  failure_reasons.png
  visualization_manifest.json
```

CSV에서 주요 열을 확인한다.

```bash
column -s, -t < "$latest_run/results.csv"
```

주요 확인 항목:

- `estimated_total_error_mm`: dry-run이 의도한 위치 오차
- `position_pass`: tolerance 기준 최종 위치 통과 여부
- `failure_reasons`: 불합격이면 `position_tolerance_exceeded`
- `detected_class`: 회차 목표 클래스와 동일한 모의 탐지 클래스
- `grasp_pose_captured`: 닫힌 그리퍼 상태에서 FK가 기록됐는지 여부

`charts/trial_position_error.png`에서는 7 mm 경고선과 10 mm 허용오차선을 기준으로
세 구간의 데이터가 올바르게 배치됐는지 한 번에 확인할 수 있다.

## 13. 문제 해결

### `dry_run` 실행 파일을 찾지 못하는 경우

```bash
colcon build --packages-select evaluation_node --symlink-install
source install/setup.bash
ros2 pkg executables evaluation_node
```

목록에 `evaluation_node dry_run`이 있어야 한다.

### launch가 이전 파일명을 찾는 경우

launch 파일 이름을 변경했다면 패키지 설치 정보를 다시 만든다.

```bash
rm -rf build/evaluation_node install/evaluation_node
colcon build --packages-select evaluation_node --symlink-install
source install/setup.bash
```

### `publisher_missing`이 발생하는 경우

두 노드가 모두 실행 중인지 확인한다.

```bash
ros2 node list
ros2 topic info /detection_results
ros2 topic info /follower/joint_states
```

두 토픽 모두 `Publisher count: 1` 이상이어야 한다.

### `gripper_not_open`이 발생하는 경우

dry-run의 `gripper_open`이 YAML의 `gripper_open_threshold` 이상인지 확인한다.

### `cooldown_active`가 발생하는 경우

dry-run은 YAML의 `cooldown_sec + 0.2초`를 기다린다. 두 노드가 서로 다른 YAML을
읽으면 대기시간이 달라질 수 있으므로 launch의 `config_path`로 같은 설정 파일을
전달한다.

### 결과 오차가 의도한 값과 다른 경우

- `evaluation_node`와 `dry_run`이 동일한 YAML을 읽는지 로그에서 확인한다.
- GT 좌표가 로봇 FK 작업 가능 범위 안에 있는지 확인한다.
- 실제 장비 노드가 동시에 같은 토픽을 발행하고 있지 않은지 확인한다.

dry-run 중에는 실제 detector나 SO-ARM joint-state publisher를 함께 실행하지 않는
것이 좋다. 동일 토픽에 복수 publisher가 있으면 평가 노드가 실제 데이터와 모의
데이터를 함께 받을 수 있다.

## 14. 단위 테스트

전체 패키지 테스트:

```bash
cd <워크스페이스>/ros2_ws
source /opt/ros/jazzy/setup.bash
PYTHONPATH=src/evaluation_node:$PYTHONPATH \
python3 -m pytest -v src/evaluation_node/test
```

dry-run 테스트만 실행:

```bash
PYTHONPATH=src/evaluation_node:$PYTHONPATH \
python3 -m pytest -v src/evaluation_node/test/test_dry_run.py
```

이 테스트는 세 구간의 데이터가 각각 3개인지, 순서가 섞이는지, 역산한 관절값을
다시 FK로 계산했을 때 요청한 XY와 일치하는지를 검증한다.
