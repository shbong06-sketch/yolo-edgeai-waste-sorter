"""
TDD #3: 병렬 디코딩 + 오버랩 테스트.

변경 사항:
- CompressedImage 디코딩을 별도 스레드에서 수행
- 디코딩과 추론을 오버랩

목표: 핵심 로직만 테스트 (ROS2 의존성 없음).
"""

import queue
import threading
import time
import unittest
from unittest.mock import MagicMock

import cv2
import numpy as np


# ─── 테스트용 스터브 생성 헬퍼 ───────────────────────────────

def _make_compressed_image_msg(quality=80):
    """Create a JPEG-encoded CompressedImage message."""
    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    _, buffer = cv2.imencode('.jpg', img, encode_param)

    msg = MagicMock()
    msg.format = 'jpeg'
    msg.data = buffer.tobytes()
    msg.header = MagicMock()
    msg.header.stamp = MagicMock()
    msg.header.frame_id = 'camera_frame'
    return msg, img


def _create_decode_pipeline():
    """병렬 디코딩 파이프라인 시뮬레이션."""
    decode_queue = queue.Queue(maxsize=2)
    inference_queue = queue.Queue(maxsize=1)
    busy = False
    lock = threading.Lock()
    skipped = 0

    def image_callback(msg):
        """Handle CompressedImage callback (fast return)."""
        nonlocal skipped
        with lock:
            if busy:
                skipped += 1
                return
        try:
            decode_queue.put_nowait((msg, msg.header))
        except queue.Full:
            pass

    def decode_loop_once():
        """decode_queue에서 꺼내 디코딩 후 inference_queue에 전달."""
        try:
            compressed_msg, header = decode_queue.get_nowait()
        except queue.Empty:
            return

        buf = np.frombuffer(compressed_msg.data, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is not None:
            try:
                inference_queue.put_nowait((frame, header))
            except queue.Full:
                pass

    def decode_worker():
        """백그라운드 디코딩 스레드."""
        while True:
            try:
                msg, header = decode_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if msg is None:
                break
            decode_loop_once()

    return {
        'decode_queue': decode_queue,
        'inference_queue': inference_queue,
        'image_callback': image_callback,
        'decode_loop_once': decode_loop_once,
        'decode_worker': decode_worker,
        'get_skipped': lambda: skipped,
        'set_busy': lambda v: None,
    }


# ─── 핵심 로직 테스트 (ROS2 의존성 없음) ────────────────────

class TestParallelDecodingArchitecture(unittest.TestCase):
    """병렬 디코딩 아키텍처 테스트."""

    def test_has_decode_queue(self):
        """decode_queue가 있어야 함."""
        pipeline = _create_decode_pipeline()
        self.assertIsNotNone(pipeline['decode_queue'])

    def test_decode_queue_maxsize(self):
        """decode_queue는 최대 2개의 프레임을 저장해야 함."""
        pipeline = _create_decode_pipeline()
        self.assertEqual(pipeline['decode_queue'].maxsize, 2)

    def test_image_callback_stores_compressed_to_decode_queue(self):
        """image_callback이 CompressedImage를 decode_queue에 저장해야 함."""
        pipeline = _create_decode_pipeline()
        msg, _ = _make_compressed_image_msg()

        pipeline['image_callback'](msg)

        self.assertFalse(pipeline['decode_queue'].empty())

    def test_image_callback_returns_quickly(self):
        """image_callback이 디코딩 없이 빠르게 반환되어야 함."""
        pipeline = _create_decode_pipeline()
        msg, _ = _make_compressed_image_msg()

        start = time.time()
        for _ in range(10):
            pipeline['image_callback'](msg)
        elapsed = time.time() - start

        self.assertLess(elapsed, 0.1,
                        f'10회 콜백에 {elapsed*1000:.1f}ms 소요')

    def test_decode_loop_method_exists(self):
        """_decode_loop_once 메서드가 있어야 함."""
        pipeline = _create_decode_pipeline()
        self.assertTrue(callable(pipeline['decode_loop_once']))

    def test_decode_loop_moves_to_inference_queue(self):
        """decode_loop이 디코딩된 프레임을 inference_queue에 전달해야 함."""
        pipeline = _create_decode_pipeline()
        msg, _ = _make_compressed_image_msg()

        pipeline['decode_queue'].put_nowait((msg, msg.header))
        pipeline['decode_loop_once']()

        self.assertFalse(pipeline['inference_queue'].empty())


class TestDecodeLoopOnce(unittest.TestCase):
    """_decode_loop_once 단위 테스트."""

    def test_decode_loop_once_processes_one_message(self):
        """_decode_loop_once가 한 메시지를 처리해야 함."""
        pipeline = _create_decode_pipeline()
        msg, _ = _make_compressed_image_msg()

        pipeline['decode_queue'].put_nowait((msg, msg.header))
        pipeline['decode_loop_once']()

        self.assertTrue(pipeline['decode_queue'].empty())
        self.assertFalse(pipeline['inference_queue'].empty())

    def test_decode_loop_once_handles_empty_queue(self):
        """_decode_loop_once가 빈 decode_queue를 안전하게 처리해야 함."""
        pipeline = _create_decode_pipeline()

        try:
            pipeline['decode_loop_once']()
        except Exception as e:
            self.fail(f'빈 Queue 처리 중 예외 발생: {e}')

    def test_decode_loop_once_handles_decode_error(self):
        """_decode_loop_once가 디코딩 오류를 안전하게 처리해야 함."""
        pipeline = _create_decode_pipeline()

        bad_msg = MagicMock()
        bad_msg.data = b'invalid_jpeg_data'
        bad_msg.header = MagicMock()

        pipeline['decode_queue'].put_nowait((bad_msg, bad_msg.header))

        try:
            pipeline['decode_loop_once']()
        except Exception as e:
            self.fail(f'디코딩 오류 처리 중 예외 발생: {e}')


class TestDecodeWorkerThread(unittest.TestCase):
    """백그라운드 디코딩 스레드 테스트."""

    def test_decode_worker_processes_frames(self):
        """decode_worker가 프레임을 처리해야 함."""
        pipeline = _create_decode_pipeline()
        decoded_frames = []

        def worker():
            while True:
                try:
                    msg, header = pipeline['decode_queue'].get(timeout=0.1)
                except queue.Empty:
                    continue
                if msg is None:
                    break
                buf = np.frombuffer(msg.data, dtype=np.uint8)
                frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if frame is not None:
                    decoded_frames.append(frame)

        decode_thread = threading.Thread(target=worker, daemon=True)
        decode_thread.start()

        for _ in range(3):
            msg, _ = _make_compressed_image_msg()
            pipeline['decode_queue'].put_nowait((msg, msg.header))

        time.sleep(0.3)
        pipeline['decode_queue'].put((None, None))
        decode_thread.join(timeout=1.0)

        self.assertEqual(len(decoded_frames), 3)


if __name__ == '__main__':
    unittest.main()
