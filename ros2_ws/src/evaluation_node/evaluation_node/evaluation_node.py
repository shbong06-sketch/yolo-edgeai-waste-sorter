"""평가 로직(EvaluationRun)을 ROS 2 토픽/서비스에 연결하는 노드."""

import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile

import rclpy
from action_msgs.msg import GoalStatus, GoalStatusArray
from control_msgs.action import FollowJointTrajectory
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_srvs.srv import Trigger
from vision_msgs.msg import Detection2DArray

from .config_loader import load_config
from .core import EvaluationRun
from .kinematics import forward_kinematics, ordered_positions
from .visualization import generate_visualizations


class EvaluationNode(Node):
    """로봇 명령을 발행하지 않고 탐지와 로봇 피드백만 관찰한다."""

    def __init__(self):
        super().__init__('evaluation_node')
        # 인자를 생략하면 사용자 설정 또는 설치된 기본 설정을 자동으로 찾는다.
        self.declare_parameter('config_path', '')
        self.declare_parameter('output_directory', '')
        self.config, config_path = load_config(self.get_parameter('config_path').value)

        # launch 실행용 evaluation.yaml 경로 지정.
        output_override = str(self.get_parameter('output_directory').value).strip()
        if output_override:
            self.config['output_directory'] = output_override


        EvaluationRun.validate_config(self.config)
        run_root = Path(
            self.config.get('output_directory') or tempfile.gettempdir()
        ).expanduser()
        # 기존 평가 결과를 덮어쓰지 않도록 실행할 때마다 고유 폴더를 만든다.
        run_name = datetime.now(timezone.utc).strftime('evaluation_%Y%m%dT%H%M%S_%fZ')
        self.run = EvaluationRun(self.config, run_root / run_name)
        self.latest_joints = None
        self.gripper_open = False
        self.exiting = False

        self.create_subscription(Detection2DArray, '/detection_results',
                                 self._detection, 10)
        self.create_subscription(JointState, '/follower/joint_states',
                                 self._joints, 10)
        # 액션 상태와 피드백을 구독만 하며 ActionClient는 만들지 않는다.
        self.create_subscription(
            GoalStatusArray,
            '/follower/joint_trajectory_controller/follow_joint_trajectory/_action/status',
            self._action_status, 10)
        self.create_subscription(
            FollowJointTrajectory.Impl.FeedbackMessage,
            '/follower/joint_trajectory_controller/follow_joint_trajectory/_action/feedback',
            self._action_feedback, 10)
        for name, callback in (
                ('start_next_trial', self._start_service),
                ('end_trial', self._end_service),
                ('abort_trial', self._abort_service),
                ('stop_run', self._stop_service),
                ('status', self._status_service),
                ('preflight', self._preflight_service),
                ('record_grasp', self._grasp_service),
                ('record_sort', self._sort_service),
                ('analyze', self._analyze_service)):
            self.create_service(Trigger, f'/evaluation/{name}', callback)
        self.create_timer(.25, self._watchdog)
        self.get_logger().info(f'평가 설정: {config_path}')
        self.get_logger().info(f'평가 결과 경로: {self.run.run_dir}')
        self.get_logger().info('평가 노드 준비 완료: 키보드 제어 노드를 실행하세요.')
        self._announce_next()

    def _publisher_presence(self):
        return {topic: self.count_publishers(topic) > 0 for topic in
                ('/detection_results', '/follower/joint_states')}

    def _preflight(self):
        return self.run.preflight(self._publisher_presence(), self.latest_joints is not None,
                                  self.gripper_open)

    def start_trial(self, source):
        result = self.run.start_trial(source, self._preflight())
        if result[0]:
            trial = self.run.active
            self.get_logger().info(
                f"{trial['trial_id']} | class={trial['target_class']} | "
                f"sample={trial['sample_id']} | position={trial['position_id']} | "
                f"GT=({trial['target_x_mm']:.1f}, {trial['target_y_mm']:.1f}) mm | "
                f"started={self.run.started}")
        return result

    def end_trial(self, source):
        result = self.run.end_trial(source)
        if result[0]:
            self._announce_next()
        return result

    def abort_trial(self, reason):
        result = self.run.abort_trial(reason)
        if result[0]:
            self._announce_next()
        return result

    def stop_run(self, reason, discard_active):
        # 중지는 기록만 마감하고, 그래프 생성은 analyze 요청에서 수행한다.
        return self.run.stop_run(reason, discard_active)

    def finalize_run(self, status, reason):
        if self.run.finalized:
            return self.run.visualization['status'] != 'failed'
        self.run.finalized = True
        self.run.status, self.run.reason = status, reason
        self.run._write_summary()
        self.run.visualization['status'] = 'generating'
        self.run.write_state()
        okay = True
        try:
            manifest = generate_visualizations(
                self.run.csv_path, self.run.state(),
                float(self.config['position_tolerance_mm']),
                float(self.config['position_warning_mm']),
                int(self.config['visualization_dpi']),
                bool(self.config['visualization_enabled']))
            self.run.visualization.update(
                status='complete', generated_at=manifest.get('generated_at'),
                files=manifest.get('files', []),
                warnings=manifest.get('warnings', []), error=None)
        except Exception as error:  # 마무리 단계에서 오류가 나도 CSV와 터미널 상태는 보존해야 한다.
            okay = False
            self.run.visualization.update(status='failed', error=str(error))
            self.get_logger().error(f'visualization failed: {error}')
        finally:
            self.run.write_state()
            self.exiting = True
        return okay

    def _detection(self, message):
        if self.run.active is None or not message.detections:
            return
        hypotheses = [
            result.hypothesis
            for detection in message.detections
            for result in detection.results
        ]
        if hypotheses:
            best = max(hypotheses, key=lambda hypothesis: hypothesis.score)
            self.run.record_detection(best.class_id)

    def _joints(self, message):
        self._record_joint_positions(message.name, message.position)

    def _record_joint_positions(self, names, positions):
        """관절 상태와 액션 피드백이 공유하는 관절/FK 기록 경로."""
        try:
            self.latest_joints = ordered_positions(names, positions)
        except (KeyError, ValueError):
            self.latest_joints = None
            return
        threshold = float(self.config['gripper_open_threshold'])
        self.gripper_open = self.latest_joints[5] >= threshold
        if self.run.active and self.latest_joints[5] <= float(self.config['gripper_closed_threshold']) and not self.run.active['grasp_pose_captured']:
            self.run.record_fk(forward_kinematics(self.latest_joints))

    def _action_feedback(self, message):
        # 피드백도 실제 관절값 캡처에만 사용하며 회차를 자동 종료하지 않는다.
        self._record_joint_positions(
            message.feedback.joint_names,
            message.feedback.actual.positions)

    def _action_status(self, message):
        # 그립 자세를 확보한 뒤 성공 상태를 관찰하면 작업 결과가 기록된 것으로 본다.
        # 상태를 관찰할 뿐 Action Goal이나 Cancel 요청은 보내지 않는다.
        if (self.run.active is not None and
                self.run.active['grasp_pose_captured'] and
                any(status.status == GoalStatus.STATUS_SUCCEEDED
                    for status in message.status_list)):
            self.run.record_outcome()

    def _watchdog(self):
        # 분리된 키보드 노드의 발견 상태를 run_state.json에 반영한다.
        keyboard_available = 'evaluation_keyboard_node' in self.get_node_names()
        if self.run.config.get('keyboard_available') != keyboard_available:
            self.run.config['keyboard_available'] = keyboard_available
            self.run.write_state()
        self.run.watchdog()
        if self.exiting:
            rclpy.shutdown()

    def _announce_next(self):
        item = self.run.next_template()
        if item is not None:
            self.get_logger().info(
                f"NEXT: class={item['target_class']}, position={item['position_id']}, "
                f"GT=({item['target_x_mm']:.1f}, {item['target_y_mm']:.1f}) mm")
        else:
            self.get_logger().warning('평가 대상과 GT 위치 설정이 필요합니다.')

    @staticmethod
    def _response(response, success, message):
        response.success = bool(success)
        response.message = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)
        return response

    def _start_service(self, request, response):
        del request
        return self._response(response, *self.start_trial('service'))

    def _end_service(self, request, response):
        del request
        # 키보드 노드의 e 입력도 이 서비스를 통하므로 동일한 완료 모드로 기록한다.
        success, value = self.end_trial('keyboard')
        return self._response(response, success, value if isinstance(value, str) else value['trial_id'])

    def _abort_service(self, request, response):
        del request
        success, value = self.abort_trial('operator_aborted')
        return self._response(response, success, value if isinstance(value, str) else value['trial_id'])

    def _stop_service(self, request, response):
        del request
        # 키보드 노드의 q 입력과 Ctrl+C가 공통으로 사용하는 종료 경로다.
        return self._response(response, self.stop_run('keyboard_quit', True), 'run stopped')

    def _status_service(self, request, response):
        del request
        return self._response(response, True, self.run.state())

    def _preflight_service(self, request, response):
        del request
        failures = self._preflight()
        return self._response(response, not failures, 'ready' if not failures else ';'.join(failures))

    def _grasp_service(self, request, response):
        del request
        if self.run.active is None or self.latest_joints is None:
            return self._response(response, False, 'active trial and valid joints required')
        self.run.record_fk(forward_kinematics(self.latest_joints))
        return self._response(response, True, 'grasp pose recorded')

    def _sort_service(self, request, response):
        del request
        if self.run.active is None:
            return self._response(response, False, 'no active trial')
        self.run.record_outcome()
        return self._response(response, True, 'sort outcome observed')

    def _analyze_service(self, request, response):
        del request
        if self.run.active is not None:
            return self._response(response, False, 'end or stop the active trial first')
        status = self.run.status if self.run.status != 'running' else 'completed'
        success = self.finalize_run(status, 'operator_analysis_requested')
        return self._response(response, success, 'analysis complete' if success else 'analysis failed')


def main(args=None):
    rclpy.init(args=args)
    node = EvaluationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.stop_run('keyboard_quit', True)
        node.finalize_run('stopped', 'keyboard_quit')
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
