"""Isaac Sim 관절을 부드럽게 이동시키는 ROS 2 액션 서버."""

import math
import threading
import time

import rclpy
from rclpy.action import ActionServer, CancelResponse
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from sensor_msgs.msg import JointState

from so_arm101_interface_pkg.action import MoveJoints


ACTION_NAME = 'move_joints_action'
COMMAND_RATE_HZ = 50.0


class MoveJointsActionServer(Node):
    """관절 목표를 보간하여 Isaac Sim으로 전달한다."""

    def __init__(self):
        """액션 서버와 Isaac Sim 입출력 토픽을 생성한다."""
        super().__init__('move_joints_action_server')

        # 액션 실행과 관절 상태 수신을 서로 다른 스레드에서 처리하기 위한 콜백 그룹
        self.action_callback_group = MutuallyExclusiveCallbackGroup()
        self.state_callback_group = MutuallyExclusiveCallbackGroup()

        # 두 콜백 스레드가 함께 사용하는 현재 관절 상태를 보호하는 잠금
        self.state_lock = threading.Lock()
        self.current_joint_state = None

        # Isaac Sim의 실제 관절 상태 수신
        self.joint_state_subscriber = self.create_subscription(
            JointState,
            '/so_arm101/joint_states',
            self.joint_state_callback,
            10,
            callback_group=self.state_callback_group,
        )

        # Isaac Sim으로 보간된 관절 제어 명령 송신
        self.joint_command_publisher = self.create_publisher(
            JointState,
            '/so_arm101/joint_command',
            10,
        )

        # 클라이언트가 보낸 관절 목표를 실행하는 액션 서버
        self.action_server = ActionServer(
            self,
            MoveJoints,
            ACTION_NAME,
            execute_callback=self.execute_callback,
            cancel_callback=self.cancel_callback,
            callback_group=self.action_callback_group,
        )

        self.get_logger().info('MoveJoints Action Server started')

    def joint_state_callback(self, msg):
        """Isaac Sim에서 받은 최신 관절 상태를 저장한다."""
        with self.state_lock:
            self.current_joint_state = msg

    def cancel_callback(self, _goal_handle):
        """클라이언트의 액션 취소 요청을 허용한다."""
        return CancelResponse.ACCEPT

    def get_current_positions(self, joint_names):
        """최신 JointState를 목표 관절 순서에 맞춰 반환한다."""
        with self.state_lock:
            if self.current_joint_state is None:
                return None

            positions_by_name = dict(zip(
                self.current_joint_state.name,
                self.current_joint_state.position,
            ))

        if any(name not in positions_by_name for name in joint_names):
            return None

        return [positions_by_name[name] for name in joint_names]

    def make_current_state(self, joint_names):
        """액션 피드백과 결과에 사용할 현재 관절 상태를 만든다."""
        current_positions = self.get_current_positions(joint_names)
        state = JointState()
        state.header.stamp = self.get_clock().now().to_msg()
        state.name = list(joint_names)
        if current_positions is not None:
            state.position = current_positions
        return state

    def make_failed_result(self, goal_handle, message, joint_names):
        """목표를 중단하고 실패 결과를 만든다."""
        goal_handle.abort()
        result = MoveJoints.Result()
        result.success = False
        result.message = message
        result.final_state = self.make_current_state(joint_names)
        return result


    def execute_callback(self, goal_handle):
        """현재 관절값에서 목표값까지 모든 축을 동시에 부드럽게 이동한다."""
        target_state = goal_handle.request.target_state
        joint_names = list(target_state.name)
        target_positions = list(target_state.position)
        duration = goal_handle.request.duration
        duration_seconds = duration.sec + duration.nanosec / 1_000_000_000

        if not joint_names:
            return self.make_failed_result(
                goal_handle, 'target_state.name is empty', joint_names)

        if len(joint_names) != len(target_positions):
            return self.make_failed_result(
                goal_handle,
                'target_state.name and position must have the same length',
                joint_names,
            )

        if duration_seconds <= 0.0:
            return self.make_failed_result(
                goal_handle,
                'duration must be greater than zero',
                joint_names,
            )

        # 실제 관절 상태를 시작점으로 사용해야 첫 명령부터 급격히 튀지 않는다.
        start_positions = self.get_current_positions(joint_names)
        if start_positions is None:
            return self.make_failed_result(
                goal_handle,
                'Current joint state is unavailable or missing target joints',
                joint_names,
            )

        total_steps = max(1, math.ceil(duration_seconds * COMMAND_RATE_HZ))
        step_interval = duration_seconds / total_steps
        start_time = time.monotonic()

        self.get_logger().info(
            f'Moving {len(joint_names)} joints for {duration_seconds:.2f}s')

        for step in range(1, total_steps + 1):
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                result = MoveJoints.Result()
                result.success = False
                result.message = 'Goal canceled'
                result.final_state = self.make_current_state(joint_names)
                return result

            progress = step / total_steps

            # 5차 smoothstep: 시작과 끝의 속도·가속도가 0이 되도록 보간한다.
            alpha = (
                10.0 * progress ** 3
                - 15.0 * progress ** 4
                + 6.0 * progress ** 5
            )
            command_positions = [
                start + alpha * (target - start)
                for start, target in zip(start_positions, target_positions)
            ]

            command = JointState()
            command.header.stamp = self.get_clock().now().to_msg()
            command.name = joint_names
            command.position = command_positions
            self.joint_command_publisher.publish(command)

            feedback = MoveJoints.Feedback()
            feedback.progress = float(progress)
            feedback.current_state = self.make_current_state(joint_names)
            goal_handle.publish_feedback(feedback)

            # 각 명령의 목표 시각을 기준으로 기다려 누적 시간 오차를 줄인다.
            next_time = start_time + step * step_interval
            remaining = next_time - time.monotonic()
            if remaining > 0.0:
                time.sleep(remaining)

        goal_handle.succeed()
        result = MoveJoints.Result()
        result.success = True
        result.message = 'Goal command completed'
        result.final_state = self.make_current_state(joint_names)
        return result

    def destroy_node(self):
        """액션 서버를 정리한 뒤 노드를 종료한다."""
        self.action_server.destroy()
        super().destroy_node()


def main(args=None):
    """두 개의 실행 스레드로 액션 서버 노드를 실행한다."""
    rclpy.init(args=args)
    node = MoveJointsActionServer()

    # 액션 실행 중에도 JointState 콜백이 처리되도록 두 개의 작업 스레드를 사용한다.
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
