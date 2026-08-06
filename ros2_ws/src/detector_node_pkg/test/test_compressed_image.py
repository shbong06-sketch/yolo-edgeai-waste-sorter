"""
TDD #1: CompressedImage 지원 테스트.

변경 사항:
- camera_node: Image -> CompressedImage 발행
- detector_node: CompressedImage 구독 -> OpenCV 디코딩

목표: 핵심 로직만 테스트 (ROS2 의존성 없음).
"""

import os
import time
import unittest

import cv2
import numpy as np


# ─── 테스트용 스터브 생성 헬퍼 ───────────────────────────────

def _make_compressed_image_msg(quality=80):
    """JPEG로 인코딩된 CompressedImage 메시지 생성."""
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    _, buffer = cv2.imencode('.jpg', img, encode_param)

    class MockHeader:
        def __init__(self):
            self.stamp = type('obj', (object,), {'sec': 0, 'nanosec': 0})()
            self.frame_id = 'camera_frame'

    class MockMsg:
        def __init__(self, data, header):
            self.format = 'jpeg'
            self.data = data
            self.header = header

    return MockMsg(buffer.tobytes(), MockHeader()), img


def _compressed_to_cv2(msg):
    """CompressedImage를 OpenCV BGR 프레임으로 디코딩."""
    buf = np.frombuffer(msg.data, dtype=np.uint8)
    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return frame


# ─── 소스 코드 패턴 검사 (ROS2 모듈 없이) ───────────────────

def _read_source_file(filename):
    """소스 파일 내용 읽기."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    filepath = os.path.join(base_dir, 'detector_node_pkg', filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    return None


class TestDetectorNodeCompressedImagePatterns(unittest.TestCase):
    """
    detector_node 소스 코드 패턴 검사.

    ROS2 모듈 없이 소스 파일을 직접 읽어서 검증.
    """

    def test_has_compressed_to_cv2_method(self):
        """detector_node에 _compressed_to_cv2 메서드가 있어야 함."""
        source = _read_source_file('detector_node.py')
        self.assertIsNotNone(source, 'detector_node.py 파일을 읽을 수 없음')
        self.assertTrue(
            '_compressed_to_cv2' in source,
            'detector_node에 _compressed_to_cv2 메서드 없음',
        )

    def test_has_compressed_image_subscription(self):
        """detector_node가 CompressedImage를 구독해야 함."""
        source = _read_source_file('detector_node.py')
        self.assertIsNotNone(source, 'detector_node.py 파일을 읽을 수 없음')
        self.assertTrue(
            'CompressedImage' in source,
            'detector_node에 CompressedImage 구독 없음',
        )

    def test_has_decode_queue(self):
        """detector_node에 decode_queue가 있어야 함."""
        source = _read_source_file('detector_node.py')
        self.assertIsNotNone(source, 'detector_node.py 파일을 읽을 수 없음')
        self.assertTrue(
            '_decode_queue' in source,
            'detector_node에 _decode_queue 없음',
        )


class TestCameraNodeCompressedImagePatterns(unittest.TestCase):
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

    def test_has_compressed_image_publish(self):
        """camera_node가 CompressedImage를 퍼블리시해야 함."""
        source = self._read_camera_source()
        if source is None:
            self.skipTest('camera_node.py 파일을 찾을 수 없음')
        self.assertTrue(
            'CompressedImage' in source,
            'CameraNode에 CompressedImage 퍼블리시 없음',
        )

    def test_has_jpeg_encoding(self):
        """camera_node가 JPEG 인코딩을 사용해야 함."""
        source = self._read_camera_source()
        if source is None:
            self.skipTest('camera_node.py 파일을 찾을 수 없음')
        self.assertTrue(
            'imencode' in source or 'jpeg' in source.lower(),
            'CameraNode에 JPEG 인코딩 없음',
        )


class TestCompressedImageDecoding(unittest.TestCase):
    """CompressedImage -> OpenCV BGR 디코딩 테스트."""

    def test_decode_jpeg_to_bgr(self):
        """JPEG 바이트를 디코딩하면 BGR 프레임이 나와야 함."""
        msg, original = _make_compressed_image_msg()
        frame = _compressed_to_cv2(msg)

        self.assertIsNotNone(frame)
        self.assertEqual(frame.shape, (480, 640, 3))
        self.assertTrue(frame.flags['C_CONTIGUOUS'])
        self.assertTrue(frame.flags['WRITEABLE'])

    def test_decode_performance_100_frames(self):
        """640x480 JPEG 디코딩 100회 < 1초."""
        msg, _ = _make_compressed_image_msg(quality=80)

        start = time.time()
        for _ in range(100):
            _compressed_to_cv2(msg)
        elapsed = time.time() - start

        self.assertLess(elapsed, 1.0,
                        f'100회 디코딩에 {elapsed:.2f}초 소요')

    def test_decode_returns_writable_array(self):
        """디코딩된 배열은 쓰기가 가능해야 함 (추론 엔진 필요)."""
        msg, _ = _make_compressed_image_msg()
        frame = _compressed_to_cv2(msg)

        self.assertTrue(frame.flags['WRITEABLE'])

    def test_decode_invalid_data_returns_none(self):
        """잘못된 JPEG 데이터 디코딩 시 None 반환."""
        class BadMsg:
            data = b'not_a_jpeg'

        frame = _compressed_to_cv2(BadMsg())
        self.assertIsNone(frame)


if __name__ == '__main__':
    unittest.main()
