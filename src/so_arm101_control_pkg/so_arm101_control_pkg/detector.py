#!/usr/bin/env python3

import random

from rcl_interfaces.msg import SetParametersResult
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from vision_msgs.msg import (
    Detection2D,
    Detection2DArray,
    ObjectHypothesisWithPose,
)


# Mock 카메라와 객체 검출 데이터 생성에 사용하는 고정 설정값
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
IMAGE_MARGIN = 100
DETECTION_TOPIC = '/topcam/position_maker'
CLASS_NAMES = ['CAN', 'PET', 'STYROFOAM']


class MockDetector(Node):
    """임의의 YOLO 형식 객체 검출 정보를 주기적으로 발행한다."""

    def __init__(self):
        super().__init__('mock_detector')

        # 실행 중에도 발행 주기를 바꿀 수 있도록 ROS 파라미터로 관리한다.
        self.declare_parameter('interval', 10.0)
        self.publish_interval = self.get_parameter('interval').value

        # 실제 YOLO 노드를 대신해 Detection2DArray를 발행한다.
        self.detection_publisher = self.create_publisher(
            Detection2DArray,
            DETECTION_TOPIC,
            10,
        )

        # 지정한 주기마다 새로운 객체 목록을 생성한다.
        self.publish_timer = self.create_timer(
            self.publish_interval,
            # self.publish_detections,
            self.pub_once
        )

        self.add_on_set_parameters_callback(self.parameters_callback)

        self.get_logger().info(
            f'Publishing mock detections on {DETECTION_TOPIC} every '
            f'{self.publish_interval:.1f}s.'
        )

    def parameters_callback(self, parameters):
        """발행 주기 파라미터 변경을 적용한다."""
        for parameter in parameters:
            if parameter.name != 'interval':
                continue

            if not 0.0 < parameter.value <= 30.0:
                return SetParametersResult(
                    successful=False,
                    reason='interval must be greater than 0 and at most 30',
                )

            self.publish_interval = float(parameter.value)
            self.publish_timer.timer_period_ns = int(
                self.publish_interval * 1_000_000_000
            )
            self.publish_timer.reset()
            self.get_logger().info(
                f'Publish interval changed to {self.publish_interval:.1f}s.'
            )

        return SetParametersResult(successful=True)

    def generate_detection(self, detection_id):
        """유효한 객체 검출 정보 하나를 생성한다."""
        detection = Detection2D()
        detection.id = str(detection_id)

        # 이미지 가장자리를 피한 범위에서 bbox 중심 픽셀을 생성한다.
        detection.bbox.center.position.x = float(
            random.randint(
                IMAGE_MARGIN,
                IMAGE_WIDTH - IMAGE_MARGIN,
            )
        )
        detection.bbox.center.position.y = float(
            random.randint(
                IMAGE_MARGIN,
                IMAGE_HEIGHT - IMAGE_MARGIN,
            )
        )
        detection.bbox.size_x = 80.0
        detection.bbox.size_y = 80.0

        # vision_msgs의 score 범위에 맞춰 0.85~1.0 값을 사용한다.
        result = ObjectHypothesisWithPose()
        result.hypothesis.class_id = random.choice(CLASS_NAMES)
        result.hypothesis.score = random.uniform(0.85, 1.0)
        detection.results.append(result)

        return detection

    def publish_detections(self):
        """한 주기의 임의 객체 목록을 발행한다."""
        message = Detection2DArray()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = 'isaac_sim_topcam'

        # 한 번 발행할 때 1~3개의 객체가 탐지된 상황을 가정한다.
        object_count = random.randint(1, 3)
        for index in range(object_count):
            detection = self.generate_detection(index)
            detection.header = message.header
            message.detections.append(detection)

            hypothesis = detection.results[0].hypothesis
            center = detection.bbox.center.position
            self.get_logger().info(
                f'Generated #{index + 1}: class={hypothesis.class_id}, '
                f'score={hypothesis.score:.3f}, '
                f'center=({center.x:.1f}, {center.y:.1f})'
            )

        self.detection_publisher.publish(message)


    # 테스트용 객체 1개 좌표 데이터 생성 후 발행
    def pub_once(self):

        self.get_logger().info(
                    f'Publishing mock detections on {DETECTION_TOPIC} once '
                    f'{self.publish_interval:.1f}s.'
                )
        
        cntObject = 1

        message = Detection2DArray()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = 'isaac_sim_topcam'
        
        detection = self.generate_detection(cntObject)
        detection.header = message.header
        message.detections.append(detection)

        hypothesis = detection.results[0].hypothesis
        center = detection.bbox.center.position
        self.get_logger().info(
            f'Generated #{cntObject + 1}: class={hypothesis.class_id}, '
            f'score={hypothesis.score:.3f}, '
            f'center=({center.x:.1f}, {center.y:.1f})'
        )

        self.detection_publisher.publish(message)

def main(args=None):
    rclpy.init(args=args)
    node = MockDetector()

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
