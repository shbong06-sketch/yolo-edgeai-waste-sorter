"""실물 장비 없이 위치 오차 임계값을 검증하는 9회 일괄 평가 노드."""

import math
import random

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_srvs.srv import Trigger
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

from ..config_loader import load_config
from ..kinematics import (
    HOME_ELBOW, HOME_LIFT, JOINT_NAMES, LIFT_SCALE, LINKS_MM, OFFSETS,
)


# 테스트 케이스
def make_error_cases(warning_mm, tolerance_mm, seed=101):
    """통과/경고/불합격 오차를 3개씩 만들고 재현 가능하게 섞는다."""
    warning_mm = float(warning_mm)
    tolerance_mm = float(tolerance_mm)
    pass_limit = warning_mm if warning_mm > 0.0 else tolerance_mm * 0.5
    gap = tolerance_mm - warning_mm
    cases = [
        *[('pass', pass_limit * ratio) for ratio in (0.25, 0.50, 0.75)],
        *[('warning', warning_mm + gap * ratio) for ratio in (0.25, 0.50, 0.75)],
        *[('fail', tolerance_mm * ratio) for ratio in (1.10, 1.25, 1.50)],
    ]
    random.Random(int(seed)).shuffle(cases)
    return cases


# 로봇관절 임의 위치값 생성함수
def joints_for_xy(x_mm, y_mm, gripper):
    """평가 노드의 FK가 지정 XY를 반환하도록 6축 관절값을 역산한다."""
    radius = math.hypot(x_mm, y_mm)
    vertical = 0.0  # FK z=LINKS_MM[0]인 해를 사용한다.
    upper, forearm = LINKS_MM[1], LINKS_MM[2]
    cosine = ((radius ** 2 + vertical ** 2 - upper ** 2 - forearm ** 2) /
              (2.0 * upper * forearm))
    if not -1.0 <= cosine <= 1.0:
        raise ValueError(f'dry-run XY is outside FK workspace: ({x_mm}, {y_mm})')
    elbow = math.acos(cosine)
    shoulder = (math.atan2(vertical, radius) -
                math.atan2(forearm * math.sin(elbow),
                           upper + forearm * math.cos(elbow)))
    pan = math.atan2(y_mm, x_mm)
    return [
        OFFSETS[0] - pan,
        OFFSETS[1] + LIFT_SCALE * (shoulder - HOME_LIFT),
        OFFSETS[2] + elbow - HOME_ELBOW,
        OFFSETS[3],
        2.9805246708618007,
        float(gripper),
    ]


class DryRunNode(Node):
    """기존 토픽과 서비스를 통해 무작위 순서의 9회 평가를 자동 수행한다."""

    def __init__(self):
        super().__init__('evaluation_dry_run_node')

        # 외부 파라미터 초기화.
        self.declare_parameter('config_path', '')           # evaluation.yaml 파일 경로
        self.declare_parameter('publish_rate_hz', 10.0)     # 임의 메시지를 초당 몇 번 발행할지 결정 (10.0 = 초당 10번)
        self.declare_parameter('random_seed', 101)          # 9개 테스트 케이스를 섞을 때 사용하는 난수 seed
        self.declare_parameter('settle_sec', 0.6)           # 한 회차를 시작한 후 관절값과 탐지 결과를 발행하면서 기다리는 시간

        self.declare_parameter('gripper_open', 4.0)         # 회차 대기 중에 발행할 그리퍼 관절값. evaluation.yaml - gripper_open_threshold 보다 크면 열려있음.
        self.declare_parameter('gripper_closed', 2.7)       # 평가 회차 중에 발행할 그리퍼 관절값. evaluation.yaml - gripper_closed_threshold 보다 작으면 닫혀있음.
        """ 그리퍼 상태전환 과정.
            회차 시작 전: gripper_open=4.0
                ↓ preflight 통과
            회차 시작
                ↓
            회차 진행 중: gripper_closed=2.7
                ↓ FK 위치 캡처
            회차 종료
                ↓
            다음 회차 대기: gripper_open=4.0
        """

        # evaluation.yaml 파일 경로
        self.config, config_path = load_config(
            self.get_parameter('config_path').value)


        # 토픽 발행주기 계산
        self.rate = float(self.get_parameter('publish_rate_hz').value)
        if self.rate <= 0.0:
            raise ValueError('publish_rate_hz must be positive')

        # 제어 파라미터 반영.
        self.settle_sec = float(self.get_parameter('settle_sec').value)
        self.open_value = float(self.get_parameter('gripper_open').value)
        self.closed_value = float(self.get_parameter('gripper_closed').value)

        # 로봇 위치오차 평가 테스트 케이스 (self.templates)
        # 합격 / 경고 / 불합격 기준데이터와 랜덤시드값
        self.cases = make_error_cases(
            self.config['position_warning_mm'],
            self.config['position_tolerance_mm'],
            self.get_parameter('random_seed').value)

        # 
        self.templates = [
            (target, position_id, point)
            for target in self.config['target_classes']
            for position_id, point in self.config['positions'].items()
        ]
        if not self.templates:
            raise ValueError('dry run requires at least one target template')




        # 토픽 퍼블리셔 생성
        self.detection_publisher = self.create_publisher(
            Detection2DArray, '/detection_results', 10)
        self.joint_publisher = self.create_publisher(
            JointState, '/follower/joint_states', 10)


        # evaluation_node와 연결된 서비스 클라이언트
        self.service_clients = {
            name: self.create_client(Trigger, f'/evaluation/{name}')
            for name in ('start_next_trial', 'end_trial', 'stop_run', 'analyze')
        }
        self.index = 0
        self.phase = 'warmup'                                   # 자동평가 절차에서 어떤 상태인지 나타내는 변수
        self.phase_started = self.get_clock().now()
        self.pending = None                                     # 호출 서비스로부터 반환되는 결과데이터 저장

        """ phase 상태전환 과정
          warmup
            │ 열린 그리퍼와 토픽을 1초간 발행
            ▼
          capturing
            │ 탐지 결과와 닫힌 그리퍼 관절값 발행
            │ settle_sec 후 end_trial
            ▼
          cooldown
            │ 열린 그리퍼 발행
            │ cooldown_sec만큼 대기
            ├─ 남은 데이터 있음 ──→ capturing
            │
            └─ 9개 완료
                    ▼
                stopped
                    │ analyze 호출
                    ▼
                done
        """


        # 토픽 발행 타이머 생성
        self.create_timer(1.0 / self.rate, self._tick)


        # 실행로그
        order = ', '.join(
            f'{number + 1}:{label}({error:.2f}mm)'
            for number, (label, error) in enumerate(self.cases))
        self.get_logger().warning('DRY RUN: 임의 데이터로 9회 평가를 자동 수행합니다.')
        self.get_logger().info(f'평가 설정: {config_path}')
        self.get_logger().info(f'무작위 배치: {order}')


    # phase 경과시간 계산
    def _elapsed(self):
        return (self.get_clock().now() - self.phase_started).nanoseconds / 1e9

    def _set_phase(self, phase):
        self.phase = phase
        self.phase_started = self.get_clock().now()

    # 현재 phase 상태
    def _current(self):
        label, error = self.cases[min(self.index, len(self.cases) - 1)]
        target, position_id, point = self.templates[self.index % len(self.templates)]
        # GT의 +X 방향으로 정확히 error mm만큼 이동시킨다.
        return label, error, target, position_id, point, (
            float(point['x_mm']) + error, float(point['y_mm']))



    # 타이머 콜백함수 : 파라미터로 설정된 주기만큼 실행
    def _tick(self):
        if self.phase == 'done':
            return

        # 더미 데이터 발생
        self._publish_inputs()

        # 실행 중이면 대기
        if self.pending is not None:
            return


        # 평가 절차상태에 따라 다음단계(next phase) 서비스 요청.
        if self.phase == 'warmup' and self._elapsed() >= 1.0:
            self._request('start_next_trial', 'capturing')

        elif self.phase == 'capturing' and self._elapsed() >= self.settle_sec:
            self._request('end_trial', 'cooldown')

        elif self.phase == 'cooldown':
            cooldown = float(self.config.get('cooldown_sec', 0.0))
            if self._elapsed() >= cooldown + 0.2:
                self.index += 1
                if self.index < len(self.cases):
                    self._request('start_next_trial', 'capturing')
                else:
                    self._request('stop_run', 'stopped')

        elif self.phase == 'stopped':
            self._request('analyze', 'done')



    # 서비스 요청 함수
    def _request(self, service, next_phase):
        client = self.service_clients[service]
        if not client.service_is_ready():
            return
        self.pending = client.call_async(Trigger.Request())
        self.pending.add_done_callback(
            lambda future: self._response(service, next_phase, future))

    # 서비스 응답처리 함수
    def _response(self, service, next_phase, future):
        self.pending = None

        # 이상처리
        try:
            response = future.result()
        except Exception as error:
            self.get_logger().error(f'[{service}] 요청 실패: {error}')
            return
        if not response.success:
            self.get_logger().error(f'[{service}] {response.message}')
            return


        # 종료처리
        if service == 'end_trial':
            label, error, _, _, _, _ = self._current()
            self.get_logger().info(
                f'{self.index + 1}/9 저장: {label}, 목표 오차={error:.2f} mm')
        # 분석 중이면
        elif service == 'analyze':
            self.get_logger().info('9회 일괄 평가와 그래프 생성이 완료되었습니다.')
        self._set_phase(next_phase)


    # 더미 데이터 생성
    def _publish_inputs(self):
        stamp = self.get_clock().now().to_msg()
        label, error, target, _, _, xy = self._current()

        # 객체 위치검출 결과 데이터
        detection_message = Detection2DArray()
        detection_message.header.stamp = stamp
        detection_message.header.frame_id = 'dry_run_camera'
        detection = Detection2D()
        detection.bbox.center.position.x = 320.0
        detection.bbox.center.position.y = 240.0
        detection.bbox.size_x = detection.bbox.size_y = 100.0

        # 객체 분류 결과 데이터
        result = ObjectHypothesisWithPose()
        result.hypothesis.class_id = target
        result.hypothesis.score = 0.95
        detection.results.append(result)
        detection_message.detections.append(detection)
        self.detection_publisher.publish(detection_message)

        # 로봇 위치 데이터
        gripper = self.open_value if self.phase in ('warmup', 'cooldown') else self.closed_value
        joint_message = JointState()
        joint_message.header.stamp = stamp
        joint_message.name = list(JOINT_NAMES)
        joint_message.position = joints_for_xy(*xy, gripper)
        self.joint_publisher.publish(joint_message)



def main(args=None):
    rclpy.init(args=args)
    node = DryRunNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()



if __name__ == '__main__':
    main()
