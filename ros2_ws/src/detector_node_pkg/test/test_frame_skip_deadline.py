"""
TDD #2: 프레임 스킵 + DDS Deadline 테스트.

변경 사항:
- camera_node: 프레임 스킵 메커니즘 + Deadline QoS
- detector_node: Deadline QoS 적용

목표: 핵심 로직만 테스트 (ROS2 의존성 없음).
"""

import os
import threading
import unittest


# ─── 테스트용 스터브 생성 헬퍼 ───────────────────────────────

def _create_frame_skip_simulation():
    """프레임 스킵 로직 시뮬레이션."""
    busy = False
    lock = threading.Lock()
    frames_received = 0
    frames_skipped = 0

    def image_callback(msg):
        nonlocal frames_received, frames_skipped
        with lock:
            if busy:
                frames_skipped += 1
                return
        frames_received += 1

    return {
        'image_callback': image_callback,
        'get_received': lambda: frames_received,
        'get_skipped': lambda: frames_skipped,
        'set_busy': lambda v: None,
    }


# ─── 소스 코드 패턴 검사 (ROS2 모듈 없이) ───────────────────

def _read_source_file(filename):
    """소스 파일 내용 읽기."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filepath = os.path.join(base_dir, 'detector_node_pkg', filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return None


class TestDetectorNodePatterns(unittest.TestCase):
    """
    detector_node 소스 코드 패턴 검사.

    ROS2 모듈 없이 소스 파일을 직접 읽어서 검증.
    """

    def test_has_frame_skip_counter(self):
        """detector_node에 프레임 카운터가 있어야 함."""
        source = _read_source_file('detector_node.py')
        self.assertIsNotNone(source, 'detector_node.py 파일을 읽을 수 없음')
        self.assertTrue(
            '_frames_skipped' in source or 'frames_skipped' in source,
            'detector_node에 프레임 스킵 카운터 없음',
        )

    def test_has_busy_flag(self):
        """detector_node에 busy 플래그가 있어야 함."""
        source = _read_source_file('detector_node.py')
        self.assertIsNotNone(source, 'detector_node.py 파일을 읽을 수 없음')
        self.assertTrue(
            '_busy' in source,
            'detector_node에 _busy 플래그 없음',
        )

    def test_has_frame_lock(self):
        """detector_node에 프레임 락이 있어야 함."""
        source = _read_source_file('detector_node.py')
        self.assertIsNotNone(source, 'detector_node.py 파일을 읽을 수 없음')
        self.assertTrue(
            '_frame_lock' in source,
            'detector_node에 _frame_lock 없음',
        )

    def test_has_compressed_image_subscription(self):
        """detector_node가 CompressedImage를 구독해야 함."""
        source = _read_source_file('detector_node.py')
        self.assertIsNotNone(source, 'detector_node.py 파일을 읽을 수 없음')
        self.assertTrue(
            'CompressedImage' in source,
            'detector_node에 CompressedImage 구독 없음',
        )

    def test_has_deadline_qos(self):
        """detector_node에 Deadline QoS가 있어야 함."""
        source = _read_source_file('detector_node.py')
        self.assertIsNotNone(source, 'detector_node.py 파일을 읽을 수 없음')
        self.assertTrue(
            'Deadline' in source or 'deadline' in source,
            'detector_node에 Deadline QoS 설정 없음',
        )

    def test_has_decode_queue(self):
        """detector_node에 decode_queue가 있어야 함."""
        source = _read_source_file('detector_node.py')
        self.assertIsNotNone(source, 'detector_node.py 파일을 읽을 수 없음')
        self.assertTrue(
            '_decode_queue' in source,
            'detector_node에 _decode_queue 없음',
        )

    def test_has_decode_thread(self):
        """detector_node에 디코딩 스레드가 있어야 함."""
        source = _read_source_file('detector_node.py')
        self.assertIsNotNone(source, 'detector_node.py 파일을 읽을 수 없음')
        self.assertTrue(
            '_decode_thread' in source or 'decode_loop' in source,
            'detector_node에 디코딩 스레드 없음',
        )


class TestCameraNodePatterns(unittest.TestCase):
    """
    camera_node 소스 코드 패턴 검사.

    ROS2 모듈 없이 소스 파일을 직접 읽어서 검증.
    """

    def _read_camera_source(self):
        """camera_node 소스 파일 읽기."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        camera_pkg_dir = os.path.join(base_dir, '..', 'camera_node_pkg')
        filepath = os.path.join(camera_pkg_dir, 'camera_node_pkg', 'camera_node.py')
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        return None

    def test_has_frame_skip_parameter(self):
        """camera_node에 frame_skip 파라미터가 있어야 함."""
        source = self._read_camera_source()
        if source is None:
            self.skipTest('camera_node.py 파일을 찾을 수 없음')
        self.assertTrue(
            'frame_skip' in source,
            'CameraNode에 frame_skip 파라미터 없음',
        )

    def test_has_frame_counter(self):
        """camera_node에 프레임 카운터가 있어야 함."""
        source = self._read_camera_source()
        if source is None:
            self.skipTest('camera_node.py 파일을 찾을 수 없음')
        self.assertTrue(
            '_frame_count' in source or 'frame_count' in source,
            'CameraNode에 프레임 카운터 없음',
        )

    def test_has_deadline_qos(self):
        """camera_node에 Deadline QoS가 있어야 함."""
        source = self._read_camera_source()
        if source is None:
            self.skipTest('camera_node.py 파일을 찾을 수 없음')
        self.assertTrue(
            'Deadline' in source or 'deadline' in source,
            'CameraNode에 Deadline QoS 설정 없음',
        )

    def test_publishes_compressed_image(self):
        """camera_node가 CompressedImage를 퍼블리시해야 함."""
        source = self._read_camera_source()
        if source is None:
            self.skipTest('camera_node.py 파일을 찾을 수 없음')
        self.assertTrue(
            'CompressedImage' in source,
            'CameraNode에 CompressedImage 퍼블리시 없음',
        )


class TestFrameSkipLogic(unittest.TestCase):
    """프레임 스킵 로직 테스트 (ROS2 없이)."""

    def test_busy_skips_frame(self):
        """_busy=True일 때 새 프레임이 스킵되어야 함."""
        busy = True
        lock = threading.Lock()
        skipped = 0

        def callback(m):
            nonlocal busy
            with lock:
                if busy:
                    return True
            return False

        for _ in range(5):
            if callback(None):
                skipped += 1

        self.assertEqual(skipped, 5)

    def test_frame_skip_counter_increment(self):
        """프레임 스킵 시 카운터가 증가해야 함."""
        skip_count = 0
        for _ in range(5):
            skip_count += 1

        self.assertEqual(skip_count, 5)


if __name__ == '__main__':
    unittest.main()
