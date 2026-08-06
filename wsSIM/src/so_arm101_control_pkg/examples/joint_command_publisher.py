#!/usr/bin/env python3

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import JointState


class JointCommandPublisher(Node):
    """Isaac Sim 관절 명령 토픽 연결을 확인하는 예제 노드."""

    def __init__(self):
        super().__init__('joint_command_publisher')

        # Publisher 생성
        self.publisher_ = self.create_publisher(
            JointState,
            '/so_arm101/joint_command',
            10
        )

        # 0.5초마다 publish
        self.timer = self.create_timer(0.5, self.publish_joint_state)

        self.get_logger().info('Joint Publisher Started.')

    def publish_joint_state(self):

        msg = JointState()

        # 움직일 Joint 이름
        msg.name = [
            'shoulder_lift'
        ]

        # 목표 위치(rad)
        msg.position = [
            0.5
        ]

        self.publisher_.publish(msg)

        self.get_logger().info(
            f'Publish : {msg.name} -> {msg.position}'
        )


def main(args=None):

    rclpy.init(args=args)

    node = JointCommandPublisher()

    rclpy.spin(node)

    node.destroy_node()

    rclpy.shutdown()


if __name__ == '__main__':
    main()
