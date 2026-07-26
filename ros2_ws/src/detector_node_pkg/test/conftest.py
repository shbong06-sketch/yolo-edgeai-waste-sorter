"""
ROS2 의존성 모킹 설정.

이 테스트 환경에는 rclpy가 설치되어 있지 않으므로,
ROS2 관련 모듈을 사전에 모킹하여 테스트를 실행할 수 있도록 한다.
"""

import sys
from unittest.mock import MagicMock

# rclpy 관련 모듈 모킹
mock_modules = [
    'rclpy',
    'rclpy.node',
    'rclpy.callback_groups',
    'rclpy.executors',
    'rclpy.qos',
    'sensor_msgs',
    'sensor_msgs.msg',
    'vision_msgs',
    'vision_msgs.msg',
]

for mod in mock_modules:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()
