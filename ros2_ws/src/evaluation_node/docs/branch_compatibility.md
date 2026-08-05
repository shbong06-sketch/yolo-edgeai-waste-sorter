# 브랜치 호환성 정리(wsSIM 제외)

검토한 원격 저장소: `https://github.com/shbong06-sketch/yolo-edgeai-waste-sorter.git`.

| 브랜치 | 카메라/탐지 인터페이스 | 로봇 인터페이스 | 평가 노드 판단 |
|---|---|---|---|
| `main` (`b253550`) | ROS 워크스페이스 구현이 없음. | 없음. | 인터페이스 기준으로 사용할 수 없음. |
| `development` (`7af0a5b`) | `detector_node`가 상대 토픽 `detection_results`를 발행함. 메시지는 `vision_msgs/msg/Detection2DArray`이고 픽셀 중심은 `bbox.center.position.x/y`임. ONNX 엔진은 숫자 ID를 문자열로 발행할 수 있음. | 뼈대 패키지만 있음. | detector 메시지 레이아웃 참고용. |
| `feature/so101-robot-control` (`3c5c511`) | 동일한 토픽/메시지를 사용함. Ultralytics 모델 클래스 이름은 `can`, `pet bottle`, `styrofoam`임. | `/follower/joint_states`(`sensor_msgs/JointState`)를 사용하고 관절 이름은 `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`, `gripper`임. 액션은 `/follower/joint_trajectory_controller/follow_joint_trajectory`임. | 실제 로봇 기준 인터페이스로 사용함. 평가 노드는 액션 상태와 피드백만 구독하고 액션 클라이언트는 만들지 않음. |

## 캘리브레이션과 좌표

실제 로봇 제어 브랜치는 카메라 픽셀을 로봇 XY로 변환하기 위해 3x3
호모그래피를 계산한다. 평가 노드는 detector 픽셀로 위치를 추정하지 않고,
측정된 관절값으로 계산한 FK를 설정 파일의 정답 로봇 XY와 직접 비교한다.
따라서 평가 노드는 호모그래피 파일을 읽거나 요구하지 않는다. 이렇게 하면
평가 지표에 직접 참여하지 않는 캘리브레이션 산출물과 평가 패키지를 분리할
수 있다.

제어 브랜치는 링크 길이 `(L1,L2,L3)=(80,117,223)` mm, 오프셋
`pan=3.1738062501353914`, `lift=1.3330293046726223`,
`elbow=4.535981189777841`, `wrist_flex=4.512971477959557`, 수학적 홈 각도
`lift=-0.1745`, `elbow=-3.0543`, lift 배율 `2.0`을 사용한다. gripper 명령값은
열림 `3.80`, 닫힘 `2.70`이다. 평가는 이 IK 매핑을 역으로 사용해 FK를
계산하지만, 실행 전 실제 장비에서 설정 확인은 반드시 필요하다.

## 작업자가 제공해야 하는 값

승인된 GT XY 위치, 허용/경고 오차 기준, 실제 관절 오프셋과 gripper 임계값이
현재 로봇과 맞는지 확인한 값을 제공한다. 그 다음 `configuration_confirmed`를
true로 바꾸고, 최종 평가라면 `thresholds_locked`도 true로 바꾼다.

## 실행 구조

두 프로세스를 별도로 실행한다. `evaluation_node`는 토픽을 관찰하고 평가
서비스와 결과 파일을 관리한다. `keyboard_node`만 터미널을 cbreak 모드로
열며 `s/e/q`를 `/evaluation/*` 서비스 요청으로 바꾼다. 따라서 평가 노드는
백그라운드에서 실행할 수 있고 키보드 노드만 포그라운드에 두면 된다.

평가 횟수는 설정에 미리 저장하지 않는다. `s`가 들어올 때마다 새 ID를 만들고
`e`가 들어올 때마다 한 행을 저장한다. 설정된 클래스/위치 조합은 안내용으로
순환한다. `q`는 `stop_run`으로 활성 회차를 폐기한 뒤 `analyze`를 요청하여
저장된 행만으로 summary와 PNG를 생성하고 두 노드를 종료한다. 결과는 실행마다
`evaluation_YYYYMMDDTHHMMSS_ffffffZ/` 고유 폴더에 저장되어 이전 결과를
덮어쓰지 않는다.

```bash
# 터미널 1: 평가 서비스와 센서 관찰
ros2 run evaluation_node evaluation_node

# 터미널 2(포그라운드): s/e/q 키 입력
ros2 run evaluation_node keyboard_node
```

두 노드는 별도 인자 없이 같은 설정을 자동 탐색한다. 우선순위는
`EVALUATION_CONFIG` 환경 변수, `~/.config/evaluation_node/evaluation.yaml`,
패키지에 설치된 기본 `evaluation.yaml` 순서다. 보통 실측 설정을 사용자 경로에
한 번 복사하면 이후에는 위의 짧은 명령만 사용하면 된다.

```bash
mkdir -p ~/.config/evaluation_node
cp /path/to/measured/evaluation.yaml \
  ~/.config/evaluation_node/evaluation.yaml
```

`s`는 측정 창을 여는 명령이므로 누른 다음 안내된 객체를 배치해도 된다.
기본 설정은 배치 시간을 포함하여 탐지 제한시간을 30초로 둔다. 단, 30초를
넘기면 `detection_timeout`이 기록되므로 객체와 위치를 먼저 준비한 뒤 `s`를
누르는 방식이 가장 안정적이다.
