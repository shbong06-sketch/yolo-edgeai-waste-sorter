# Branch compatibility (wsSIM excluded)

Reviewed remote: `https://github.com/shbong06-sketch/yolo-edgeai-waste-sorter.git`.

| Branch | Camera/detection | Robot interface | Evaluation decision |
|---|---|---|---|
| `main` (`b253550`) | No ROS workspace implementation. | None. | Not usable as an interface source. |
| `development` (`7af0a5b`) | `detector_node` publishes relative `detection_results`; `vision_msgs/msg/Detection2DArray`; pixel centre is `bbox.center.position.x/y`. ONNX engine may emit numeric IDs as strings. | Skeleton package only. | Detector message layout reference only. |
| `feature/so101-robot-control` (`3c5c511`) | Same topic/message; Ultralytics model names include `can`, `pet bottle`, `styrofoam`. | `/follower/joint_states` (`sensor_msgs/JointState`), joints `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`, `gripper`; action `/follower/joint_trajectory_controller/follow_joint_trajectory`. | Primary physical-robot interface. Evaluation subscribes to Action status and feedback only and creates no action client. |

## Calibration and coordinates

The physical control branch calculates a 3x3 homography from camera pixels to
robot XY for motion planning. The evaluation node does not use detector pixels
to estimate position: it compares FK from measured joints directly with the
configured ground-truth robot XY. Therefore it neither loads nor requires a
homography file. This keeps the evaluation package independent of a calibration
artefact that does not participate in its metrics.

The control branch uses link lengths `(L1,L2,L3)=(80,117,223)` mm, offsets
`pan=3.1738062501353914`, `lift=1.3330293046726223`,
`elbow=4.535981189777841`, `wrist_flex=4.512971477959557`, mathematical home
angles `lift=-0.1745`, `elbow=-3.0543`, and lift scale `2.0`. Its commanded
gripper values are open `3.80` and closed `2.70`. Evaluation reverses that IK
mapping for FK, but configuration confirmation is still required before a run.

## Required operator-supplied values

Provide approved GT XY positions, tolerance/warning thresholds, and
confirmation that the physical joint offsets and gripper thresholds still
match the robot. Then set
`configuration_confirmed` and, for a final run, `thresholds_locked` to true.

## Runtime layout

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
