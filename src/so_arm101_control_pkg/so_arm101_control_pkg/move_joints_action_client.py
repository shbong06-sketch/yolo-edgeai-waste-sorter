#!/usr/bin/env python3

from builtin_interfaces.msg import Duration
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node


from sensor_msgs.msg import JointState
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesis     # YOLO 객체탐지 결과 데이터 클래스

from so_arm101_interface_pkg.action import MoveJoints



ACTION_NAME = 'move_joints_action'
JOINT_STATE_TOPIC = '/so_arm101/joint_states'

# Isaac Sim이 보내는 관절 순서에 대응하는 네 개의 목표 위치(rad)
WAYPOINTS = [
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    [0.35, -0.30, 0.45, -0.20, 0.25, 0.15],
    [-0.35, -0.15, 0.30, 0.25, -0.25, 0.45],
    [0.0, -0.40, 0.60, -0.20, 0.0, 0.0],
]


class MoveJointsActionClient(Node):
    """Isaac Sim의 관절 정보를 사용해 네 개의 목표점을 이동한다."""

    def __init__(self):
        super().__init__('move_joints_action_client')

        # 로봇 제어용 액션 클라이언트
        self.action_client = ActionClient(
            self,
            MoveJoints,
            ACTION_NAME,
        )

        # 로봇 상태체크 토픽 (현재는 축 위치만 받고있음.)
        self.joint_state_subscription = self.create_subscription(
            JointState,
            JOINT_STATE_TOPIC,
            self.joint_state_callback,
            10,
        )


        self.joint_names = []               # 축 이름 (로봇에게 받음)
        self.waypoint_index = 0


        # 객체좌표 수신용 토픽 서브스크라이버
        self.detection_subscriber = self.create_subscription(
            Detection2DArray, "topcam/position_maker",
            self.received_positions,
            10
        )

    def received_positions(self, msg):
        objects = msg

        self.get_logger().info(f"received {len(objects.detections)} object(s)")

        for obj in objects.detections:
            infoClass = obj.results[0].hypothesis
            bbox = obj.bbox

            self.get_logger().info(f"[{infoClass.class_id:<10}] - {bbox.center}")


    def start(self):
        """액션 서버와 Isaac Sim 관절 정보를 기다린다."""
        self.get_logger().info('Waiting for MoveJoints action server...')
        self.action_client.wait_for_server()
        self.get_logger().info(
            f'Waiting for joint names on {JOINT_STATE_TOPIC}...'
        )

    def joint_state_callback(self, msg):
        """Isaac Sim에서 관절 이름과 순서를 한 번 가져온다."""
        if self.joint_names or not msg.name:
            return

        if len(msg.name) != len(WAYPOINTS[0]):
            self.get_logger().error(
                f'Isaac Sim has {len(msg.name)} joints, but each waypoint '
                f'contains {len(WAYPOINTS[0])} positions.'
            )
            rclpy.shutdown()
            return

        self.joint_names = list(msg.name)
        self.get_logger().info(
            f'Using Isaac Sim joints: {self.joint_names}'
        )
        self.send_next_goal()

    def send_next_goal(self):
        """다음 목표점을 액션 서버로 전송한다."""
        if self.waypoint_index >= len(WAYPOINTS):
            self.get_logger().info('All four waypoints completed.')
            rclpy.shutdown()
            return

        target_state = JointState()
        target_state.name = self.joint_names
        target_state.position = WAYPOINTS[self.waypoint_index]

        goal = MoveJoints.Goal()
        goal.target_state = target_state
        goal.duration = Duration(sec=3)

        point_number = self.waypoint_index + 1
        self.get_logger().info(
            f'Sending waypoint {point_number}/{len(WAYPOINTS)}: '
            f'{target_state.position}'
        )

        future = self.action_client.send_goal_async(
            goal,
            feedback_callback=self.feedback_callback,
        )
        future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        """Goal 수락 여부를 확인한다."""
        goal_handle = future.result()

        if not goal_handle.accepted:
            self.get_logger().error(
                f'Waypoint {self.waypoint_index + 1} was rejected.'
            )
            rclpy.shutdown()
            return

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.result_callback)

    def feedback_callback(self, feedback_msg):
        """현재 목표점의 진행률을 출력한다."""
        progress = feedback_msg.feedback.progress * 100.0
        self.get_logger().info(
            f'Waypoint {self.waypoint_index + 1}: {progress:.1f}%'
        )

    def result_callback(self, future):
        """성공하면 다음 목표점으로 이동한다."""
        result = future.result().result

        if not result.success:
            self.get_logger().error(result.message)
            rclpy.shutdown()
            return

        self.waypoint_index += 1
        self.send_next_goal()


def main(args=None):
    rclpy.init(args=args)
    node = MoveJointsActionClient()

    try:

        #node.start()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
