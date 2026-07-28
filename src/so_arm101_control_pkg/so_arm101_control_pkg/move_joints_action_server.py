import time

import rclpy
from rclpy.action import ActionServer
from rclpy.node import Node

from so_arm101_interface_pkg.action import MoveJoints
from sensor_msgs.msg import JointState


ACTION_NAME = "move_joints_action"



class MoveJointsActionServer(Node):

    def __init__(self):
        super().__init__('move_joints_action_server')


        # 이동명령 액션 서버
        self._action_server = ActionServer(
            self,
            MoveJoints,
            ACTION_NAME,
            self.execute_callback,
        )

        self.get_logger().info('MoveJoints Action Server started')


        # Isaac SIM - Joint State 수신 노드
        self.joint_state_subscriber = self.create_subscription(
            JointState,
            "/so_arm101/joint_states",
            self.joint_state_callback,
            10,
        )

        # Isaac SIM - 축 제어명령 송신 노드
        self.joint_command_publisher = self.create_publisher(
            JointState,
            "/so_arm101/joint_command",
            10,
        )


    def execute_callback(self, goal_handle):
        self.get_logger().info('MoveJoints goal received')

        target_state = goal_handle.request.target_state
        duration = goal_handle.request.duration

        # 축 내용이 비어있으면
        if len(target_state.name) == 0:
            goal_handle.abort()

            result = MoveJoints.Result()
            result.success = False
            result.message = 'target_state.name is empty'
            return result


        # 축과 위치 개수 안맞으면 이상처리
        if len(target_state.name) != len(target_state.position):
            goal_handle.abort()

            result = MoveJoints.Result()
            result.success = False
            result.message = (
                'target_state.name and target_state.position '
                'must have the same length'
            )
            return result

        duration_seconds = duration.sec + duration.nanosec / 1_000_000_000

        # 이동시간 이상처리
        if duration_seconds <= 0.0:
            goal_handle.abort()

            result = MoveJoints.Result()
            result.success = False
            result.message = 'duration must be greater than zero'
            return result




        feedback = MoveJoints.Feedback()

        steps = 20
        sleep_time = duration_seconds / steps

        for step in range(steps):
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()

                result = MoveJoints.Result()
                result.success = False
                result.message = 'Goal canceled'
                result.final_state = target_state
                return result

            feedback.progress = float(step + 1) / steps
            feedback.current_state = target_state

            goal_handle.publish_feedback(feedback)

            command = JointState()
            command.header.stamp = self.get_clock().now().to_msg()
            command.name = list(target_state.name)
            command.position = list(target_state.position)

            self.joint_command_publisher.publish(command)

            self.get_logger().info(
                f'Published command: {list(command.position)}'
            )

            self.get_logger().info(
                f'Progress: {feedback.progress * 100:.1f}%'
            )

            time.sleep(sleep_time)



        goal_handle.succeed()

        result = MoveJoints.Result()
        result.success = True
        result.message = 'Goal completed'
        result.final_state = target_state

        return result



    def joint_state_callback(self, msg):
        self.current_joint_state = msg
        self.get_logger().info(f"Received {len(msg.name)} joints")

def main(args=None):
    rclpy.init(args=args)

    node = MoveJointsActionServer()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()