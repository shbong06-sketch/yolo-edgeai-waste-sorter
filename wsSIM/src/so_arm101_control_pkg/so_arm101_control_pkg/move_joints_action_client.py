#!/usr/bin/env python3

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from builtin_interfaces.msg import Duration
import numpy as np
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import JointState
from so_arm101_control_pkg.kinematics import RobotKinematics
from so_arm101_interface_pkg.action import MoveJoints
from vision_msgs.msg import Detection2DArray


ACTION_NAME = 'move_joints_action'
DETECTION_TOPIC = '/topcam/position_maker'
JOINT_STATE_TOPIC = '/so_arm101/joint_states'

IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
TABLE_X_SIZE = 0.8085078
TABLE_Y_SIZE = 1.1356210
METERS_PER_PIXEL_X = TABLE_X_SIZE / IMAGE_HEIGHT
METERS_PER_PIXEL_Y = TABLE_Y_SIZE / IMAGE_WIDTH

# 최초 시험은 현재 위치에서 축별 최대 5 cm만 이동한다.
MAX_OFFSET = 0.05
GRIPPER_JOINT = 'gripper'


def pixel_to_robot_offset(pixel_x, pixel_y):
    """픽셀 좌표를 영상 중심 기준 로봇 XY 이동량으로 변환한다."""
    robot_x = (
        IMAGE_HEIGHT / 2.0 - pixel_y
    ) * METERS_PER_PIXEL_X
    robot_y = (
        IMAGE_WIDTH / 2.0 - pixel_x
    ) * METERS_PER_PIXEL_Y
    return robot_x, robot_y


class MoveJointsActionClient(Node):
    """객체 픽셀 좌표를 관절 목표값으로 바꿔 액션 Goal을 전송한다."""

    def __init__(self):
        super().__init__('move_joints_action_client')

        self.action_client = ActionClient(
            self,
            MoveJoints,
            ACTION_NAME,
        )

        # URDF로 현재 위치와 목표 관절값을 계산한다.
        description_path = Path(
            get_package_share_directory('so_arm101_description')
        )
        self.kinematics = RobotKinematics(
            description_path / 'urdf' / 'so_arm101.urdf',
            'base_link',
            'gripper_frame_link',
        )

        self.create_subscription(
            JointState,
            JOINT_STATE_TOPIC,
            self.joint_state_callback,
            10,
        )
        self.create_subscription(
            Detection2DArray,
            DETECTION_TOPIC,
            self.detection_callback,
            10,
        )

        self.current_positions = {}
        self.moving = False



        

    def joint_state_callback(self, message):
        """Isaac Sim의 현재 관절값을 이름별로 저장한다."""
        self.current_positions.update(
            zip(message.name, message.position)
        )

    def detection_callback(self, message):
        """첫 객체의 픽셀 좌표를 변환하고 이동 Goal을 전송한다."""
        if self.moving or not message.detections:
            return

        detection = message.detections[0]
        if not detection.results:
            return

        # 현재 관절 상태와 액션 서버가 준비된 경우에만 이동한다.
        joint_names = self.kinematics.joint_names
        required_joints = joint_names + [GRIPPER_JOINT]
        if not all(
            name in self.current_positions
            for name in required_joints
        ):
            return

        if not self.action_client.server_is_ready():
            return

        # 객체 픽셀 좌표를 현재 end-effector 기준 XY 이동량으로 변환한다.
        center = detection.bbox.center.position
        offset_x, offset_y = pixel_to_robot_offset(
            center.x,
            center.y,
        )
        offset_x = float(np.clip(
            offset_x,
            -MAX_OFFSET,
            MAX_OFFSET,
        ))
        offset_y = float(np.clip(
            offset_y,
            -MAX_OFFSET,
            MAX_OFFSET,
        ))

        # 현재 관절값으로 FK를 계산하고 XY 이동량을 더한다.
        current_joints = np.array([
            self.current_positions[name]
            for name in joint_names
        ])
        target_xyz = self.kinematics.forward(
            current_joints
        )[:3, 3]
        target_xyz[0] += offset_x
        target_xyz[1] += offset_y

        # 목표 XYZ를 Isaac Sim에 보낼 관절값으로 변환한다.
        try:
            target_joints = self.kinematics.inverse_position(
                target_xyz,
                current_joints,
            )
        except ValueError as error:
            self.get_logger().error(str(error))
            return

        target_state = JointState()
        target_state.name = required_joints
        target_state.position = target_joints.tolist() + [
            self.current_positions[GRIPPER_JOINT]
        ]

        goal = MoveJoints.Goal()
        goal.target_state = target_state
        goal.duration = Duration(sec=10)

        self.moving = True
        self.get_logger().info(
            f'Move object at pixel ({center.x:.1f}, {center.y:.1f}) '
            f'by ({offset_x:.3f}, {offset_y:.3f})m'
        )

        future = self.action_client.send_goal_async(goal)
        future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        """Goal이 수락되면 완료 결과를 기다린다."""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.moving = False
            self.get_logger().error('Move goal rejected.')
            return

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.result_callback)

    def result_callback(self, future):
        """이동 완료 후 다음 Detection을 받을 수 있게 한다."""
        result = future.result().result
        self.moving = False

        if result.success:
            self.get_logger().info('Move completed.')
        else:
            self.get_logger().error(result.message)


def main(args=None):
    rclpy.init(args=args)
    node = MoveJointsActionClient()

    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
