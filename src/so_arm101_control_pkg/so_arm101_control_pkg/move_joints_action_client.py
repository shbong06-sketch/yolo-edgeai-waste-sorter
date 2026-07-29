#!/usr/bin/env python3

import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import JointState
from so_arm101_interface_pkg.action import MoveJoints
from vision_msgs.msg import Detection2DArray


# detector 및 Isaac Sim과 연결할 ROS 인터페이스 이름
ACTION_NAME = 'move_joints_action'
DETECTION_TOPIC = '/topcam/position_maker'
JOINT_STATE_TOPIC = '/so_arm101/joint_states'

# 설계에서 정한 객체 처리 최소 신뢰도
CONFIDENCE_THRESHOLD = 0.85

# TopViewCam 영상과 실제 shopTable 크기
IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480
TABLE_X_SIZE = 0.8085078
TABLE_Y_SIZE = 1.1356210

# 화면 세로 방향은 World X, 화면 가로 방향은 World Y에 대응한다.
METERS_PER_PIXEL_X = TABLE_X_SIZE / IMAGE_HEIGHT
METERS_PER_PIXEL_Y = TABLE_Y_SIZE / IMAGE_WIDTH


def pixel_to_robot_offset(pixel_x, pixel_y):
    """영상 중심에서 객체까지의 픽셀 거리를 로봇 XY 이동량으로 바꾼다."""
    image_center_x = IMAGE_WIDTH / 2.0
    image_center_y = IMAGE_HEIGHT / 2.0

    # World +X는 화면 위쪽, World +Y는 화면 왼쪽 방향이다.
    robot_x = (image_center_y - pixel_y) * METERS_PER_PIXEL_X
    robot_y = (image_center_x - pixel_x) * METERS_PER_PIXEL_Y
    return robot_x, robot_y


def is_valid_detection(detection):
    """객체 검출 정보가 현재 처리 조건을 만족하는지 확인한다."""
    # 분류 결과가 없으면 class와 confidence를 확인할 수 없다.
    if not detection.results:
        return False

    # 첫 번째 분류 결과를 대표 결과로 사용한다.
    if detection.results[0].hypothesis.score < CONFIDENCE_THRESHOLD:
        return False

    # 크기가 없는 bbox는 좌표 매핑과 허용 반경 계산에 사용할 수 없다.
    if detection.bbox.size_x <= 0.0 or detection.bbox.size_y <= 0.0:
        return False

    return True


class MoveJointsActionClient(Node):
    """객체 정보를 받아 좌표 변환과 이동을 준비하는 액션 클라이언트."""

    def __init__(self):
        super().__init__('move_joints_action_client')

        # 다음 단계에서 변환된 관절 목표값을 전송할 액션 클라이언트
        self.action_client = ActionClient(
            self,
            MoveJoints,
            ACTION_NAME,
        )

        # Isaac Sim의 실제 관절 이름과 순서를 가져온다.
        self.joint_state_subscription = self.create_subscription(
            JointState,
            JOINT_STATE_TOPIC,
            self.joint_state_callback,
            10,
        )

        # detector가 발행한 객체 검출 목록을 받는다.
        self.detection_subscription = self.create_subscription(
            Detection2DArray,
            DETECTION_TOPIC,
            self.detection_callback,
            10,
        )

        self.joint_names = []

        # 현재 수신 주기에서 검증을 통과한 객체를 입력 순서대로 보관한다.
        # 다음 단계에서 이 목록을 좌표 변환 및 IK 입력으로 사용할 예정이다.
        self.pending_detections = []

        self.get_logger().info(
            f'Waiting for detections on {DETECTION_TOPIC}.'
        )

    def joint_state_callback(self, message):
        """Isaac Sim의 관절 이름과 순서를 저장한다."""
        if not self.joint_names and message.name:
            self.joint_names = list(message.name)
            self.get_logger().info(
                f'Received Isaac Sim joints: {self.joint_names}'
            )

    def detection_callback(self, message):
        """유효한 객체를 입력 순서대로 저장한다."""
        self.get_logger().info(
            f'Received {len(message.detections)} detection(s).'
        )

        # 새 Detection2DArray가 오면 이전 주기 목록을 교체한다.
        # 리스트 컴프리헨션을 사용하므로 원본 메시지의 객체 순서가 유지된다.
        self.pending_detections = [
            detection
            for detection in message.detections
            if is_valid_detection(detection)
        ]

        for index, detection in enumerate(self.pending_detections, start=1):
            hypothesis = detection.results[0].hypothesis
            center = detection.bbox.center.position
            robot_x, robot_y = pixel_to_robot_offset(
                center.x,
                center.y,
            )
            self.get_logger().info(
                f'Accepted #{index}: class={hypothesis.class_id}, '
                f'score={hypothesis.score:.3f}, '
                f'center=({center.x:.1f}, {center.y:.1f}), '
                f'bbox=({detection.bbox.size_x:.1f}, '
                f'{detection.bbox.size_y:.1f}), '
                f'robot_offset=({robot_x:.4f}, {robot_y:.4f})m'
            )

        # 입력 개수와 통과 개수의 차이로 제외된 객체 수를 기록한다.
        rejected_count = (
            len(message.detections) - len(self.pending_detections)
        )
        if rejected_count:
            self.get_logger().warning(
                f'Rejected {rejected_count} invalid detection(s).'
            )

        if not self.pending_detections:
            self.get_logger().warning(
                'No valid detections to process in this cycle.'
            )


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
