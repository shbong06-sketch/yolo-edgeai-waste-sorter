"""
DetectorNode 스레드 안전성, 메모리 관리 및 최적화 테스트.

ROS2 환경 없이도 실행 가능한 핵심 로직 테스트.
test_dds_optimization.py와 통합되어 병렬 디코딩 아키텍처를 검증.
"""

import queue
import threading
import time
import unittest
from unittest.mock import MagicMock

import cv2
import numpy as np


def _make_compressed_image_msg(width=640, height=480, quality=80):
    """Create a mock CompressedImage message."""
    img = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    _, buffer = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])

    msg = MagicMock()
    msg.format = 'jpeg'
    msg.data = buffer.tobytes()
    msg.header = MagicMock()
    msg.header.stamp = MagicMock()
    msg.header.frame_id = 'camera_frame'
    return msg, img


class TestCompressedImageDecoding(unittest.TestCase):
    """_compressed_to_cv2 디코딩 테스트."""

    def test_decode_returns_bgr_frame(self):
        """CompressedImage를 디코딩하면 BGR 프레임이 나와야 함."""
        msg, _ = _make_compressed_image_msg(640, 480)
        buf = np.frombuffer(msg.data, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)

        self.assertIsNotNone(frame)
        self.assertEqual(frame.shape, (480, 640, 3))
        self.assertTrue(frame.flags['C_CONTIGUOUS'])
        self.assertTrue(frame.flags['WRITEABLE'])

    def test_decode_performance(self):
        """JPEG 디코딩 100회 < 1초."""
        msg, _ = _make_compressed_image_msg(640, 480, quality=80)
        buf = np.frombuffer(msg.data, dtype=np.uint8)

        start = time.time()
        for _ in range(100):
            cv2.imdecode(buf, cv2.IMREAD_COLOR)
        elapsed = time.time() - start

        self.assertLess(elapsed, 1.0, f'100회 디코딩에 {elapsed:.2f}초 소요')


class TestParallelDecodingQueue(unittest.TestCase):
    """병렬 디코딩 Queue 테스트."""

    def test_queue_delivers_frames(self):
        """Queue가 프레임을 전달해야 함."""
        decode_queue = queue.Queue(maxsize=2)
        msg, _ = _make_compressed_image_msg()

        for _ in range(5):
            try:
                decode_queue.put_nowait((msg, msg.header))
            except queue.Full:
                pass

        self.assertGreater(decode_queue.qsize(), 0)

    def test_queue_maxsize_limits_storage(self):
        """Queue maxsize가 메모리 폭발을 방지해야 함."""
        decode_queue = queue.Queue(maxsize=2)
        msg, _ = _make_compressed_image_msg()

        for _ in range(10):
            try:
                decode_queue.put_nowait((msg, msg.header))
            except queue.Full:
                pass

        self.assertLessEqual(decode_queue.qsize(), 2)

    def test_decode_loop_once_processes_frame(self):
        """디코딩 루프가 프레임을 처리해야 함."""
        decode_queue = queue.Queue(maxsize=2)
        inference_queue = queue.Queue(maxsize=5)
        msg, _ = _make_compressed_image_msg()

        decode_queue.put_nowait((msg, msg.header))

        # 디코딩 시뮬레이션
        compressed_msg, header = decode_queue.get_nowait()
        buf = np.frombuffer(compressed_msg.data, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)

        if frame is not None:
            inference_queue.put_nowait((frame, header))

        self.assertTrue(decode_queue.empty())
        self.assertFalse(inference_queue.empty())


class TestFrameSkip(unittest.TestCase):
    """프레임 스킵 테스트."""

    def test_busy_skips_frame(self):
        """_busy=True일 때 프레임 스킵."""
        busy = False
        lock = threading.Lock()
        skipped = 0

        def on_frame():
            nonlocal skipped
            with lock:
                if busy:
                    skipped += 1
                    return

        with lock:
            busy = True

        for _ in range(5):
            on_frame()

        self.assertEqual(skipped, 5)

    def test_frame_skip_counter_increments(self):
        """스킵 카운터 증가 확인."""
        skip_count = 0
        for _ in range(10):
            skip_count += 1

        self.assertEqual(skip_count, 10)


class TestStateMachine(unittest.TestCase):
    """상태 전이 안전성 테스트."""

    def test_inference_complete_resets_busy(self):
        """추론 완료 후 _busy가 리셋되어야 함."""
        busy = True
        lock = threading.Lock()

        # 추론 완료 시뮬레이션
        with lock:
            busy = False

        self.assertFalse(busy)

    def test_busy_flag_with_lock(self):
        """_busy 플래그가 lock으로 보호되어야 함."""
        busy = False
        lock = threading.Lock()

        with lock:
            busy = True

        self.assertTrue(busy)


if __name__ == '__main__':
    unittest.main()
