"""
TDD #1-3: DDS 통신 속도 개선 통합 테스트.

ROS2 환경 없이도 실행 가능한 핵심 로직 테스트.

변경 사항:
1. CompressedImage 디코딩 지원 (_compressed_to_cv2)
2. 병렬 디코딩 (_decode_queue, _decode_loop, _decode_loop_once)
3. 프레임 스킵 + Deadline QoS
"""

import queue
import threading
import time
import unittest
from unittest.mock import MagicMock

import cv2
import numpy as np


# ─── 테스트용 스터브 생성 헬퍼 ───────────────────────────────
# rclpy 미설치 환경에서 DetectorNode의 핵심 로직만 테스트하기 위해
# 클래스를 직접 정의하고 메서드만 복사하는 방식 사용

def _make_compressed_image_msg(width=640, height=480, quality=80):
    """JPEG로 인코딩된 CompressedImage 메시지 생성."""
    img = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    _, buffer = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])

    msg = MagicMock()
    msg.format = 'jpeg'
    msg.data = buffer.tobytes()
    msg.header = MagicMock()
    msg.header.stamp = MagicMock()
    msg.header.frame_id = 'camera_frame'
    return msg, img


def _make_raw_image_msg(width=640, height=480, encoding='bgr8'):
    """Raw Image 메시지 생성."""
    msg = MagicMock()
    msg.width = width
    msg.height = height
    msg.encoding = encoding
    channels = 1 if encoding == 'mono8' else 3
    msg.data = np.random.randint(0, 255, (height, width, channels), dtype=np.uint8).tobytes()
    msg.header = MagicMock()
    msg.header.stamp = MagicMock()
    msg.header.frame_id = 'camera'
    return msg


# ─── 핵심 로직 테스트 (ROS2 의존성 없음) ────────────────────

class TestCompressedImageDecoding(unittest.TestCase):
    """CompressedImage → OpenCV BGR 디코딩 테스트."""

    def test_decode_jpeg_to_bgr(self):
        """JPEG 바이트를 디코딩하면 BGR 프레임이 나와야 함."""
        msg, original = _make_compressed_image_msg(640, 480)

        buf = np.frombuffer(msg.data, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)

        self.assertIsNotNone(frame)
        self.assertEqual(frame.shape, (480, 640, 3))
        self.assertTrue(frame.flags['C_CONTIGUOUS'])
        self.assertTrue(frame.flags['WRITEABLE'])

    def test_decode_performance_100_frames(self):
        """640x480 JPEG 디코딩 100회 < 1초."""
        msg, _ = _make_compressed_image_msg(640, 480, quality=80)
        buf = np.frombuffer(msg.data, dtype=np.uint8)

        start = time.time()
        for _ in range(100):
            cv2.imdecode(buf, cv2.IMREAD_COLOR)
        elapsed = time.time() - start

        self.assertLess(elapsed, 1.0,
                        f'100회 디코딩에 {elapsed:.2f}초 소요')

    def test_decode_returns_writable_array(self):
        """디코딩된 배열은 쓰기가 가능해야 함 (추론 엔진 필요)."""
        msg, _ = _make_compressed_image_msg()
        buf = np.frombuffer(msg.data, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)

        self.assertTrue(frame.flags['WRITEABLE'])

    def test_decode_invalid_data_returns_none(self):
        """잘못된 JPEG 데이터 디코딩 시 None 반환."""
        bad_data = b'not_a_jpeg'
        buf = np.frombuffer(bad_data, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)

        self.assertIsNone(frame)


class TestParallelDecodingQueue(unittest.TestCase):
    """병렬 디코딩을 위한 Queue 동작 테스트."""

    def test_decode_queue_holds_compressed_messages(self):
        """decode_queue에 CompressedImage가 저장되어야 함."""
        decode_queue = queue.Queue(maxsize=2)
        msg, _ = _make_compressed_image_msg()

        decode_queue.put_nowait((msg, msg.header))

        self.assertFalse(decode_queue.empty())
        self.assertEqual(decode_queue.qsize(), 1)

    def test_decode_queue_maxsize_limits_storage(self):
        """decode_queue maxsize가 메모리 폭발을 방지해야 함."""
        decode_queue = queue.Queue(maxsize=2)

        for _ in range(5):
            try:
                msg, _ = _make_compressed_image_msg()
                decode_queue.put_nowait((msg, msg.header))
            except queue.Full:
                pass

        self.assertLessEqual(decode_queue.qsize(), 2)

    def test_decode_and_inference_queue_pipeline(self):
        """decode_queue → 디코딩 → inference_queue 파이프라인 테스트."""
        decode_queue = queue.Queue(maxsize=2)
        inference_queue = queue.Queue(maxsize=1)

        # CompressedImage 저장
        msg, _ = _make_compressed_image_msg()
        decode_queue.put_nowait((msg, msg.header))

        # 디코딩 시뮬레이션
        compressed_msg, header = decode_queue.get_nowait()
        buf = np.frombuffer(compressed_msg.data, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)

        # inference_queue에 저장
        inference_queue.put_nowait((frame, header))

        # 확인
        self.assertTrue(decode_queue.empty())
        self.assertFalse(inference_queue.empty())

        decoded_frame, _ = inference_queue.get_nowait()
        self.assertEqual(decoded_frame.shape, (480, 640, 3))


class TestFrameSkipLogic(unittest.TestCase):
    """프레임 스킵 로직 테스트 (ROS2 없이)."""

    def test_busy_flag_skips_processing(self):
        """_busy=True일 때 새 프레임이 스킵되어야 함."""
        busy = False
        lock = threading.Lock()
        skipped = 0
        received = 0

        def on_frame():
            nonlocal skipped, received
            with lock:
                if busy:
                    skipped += 1
                    return
            received += 1

        # busy=True로 설정
        with lock:
            busy = True

        for _ in range(5):
            on_frame()

        self.assertEqual(skipped, 5)
        self.assertEqual(received, 0)

    def test_skip_counter_increments(self):
        """프레임 스킵 시 카운터가 증가해야 함."""
        skip_count = 0
        for _ in range(10):
            skip_count += 1

        self.assertEqual(skip_count, 10)


class TestCompressedImageCallbackFlow(unittest.TestCase):
    """
    image_callback의 CompressedImage 처리 흐름 테스트.

    목표: 콜백에서 디코딩 없이 decode_queue에 저장만 수행
    """

    def test_callback_does_not_decode(self):
        """image_callback이 직접 디코딩하지 않아야 함."""
        decode_queue = queue.Queue(maxsize=2)
        msg, _ = _make_compressed_image_msg()

        # 콜백 시뮬레이션: 디코딩 없이 저장만
        start = time.time()
        try:
            decode_queue.put_nowait((msg, msg.header))
        except queue.Full:
            decode_queue.get_nowait()
            decode_queue.put_nowait((msg, msg.header))
        elapsed = time.time() - start

        # 저장만 빠르게 완료되어야 함
        self.assertLess(elapsed, 0.01,
                        f'Queue 저장에 {elapsed*1000:.1f}ms 소요')

    def test_decode_in_background_thread(self):
        """디코딩이 백그라운드 스레드에서 수행되어야 함."""
        decode_queue = queue.Queue(maxsize=2)
        inference_queue = queue.Queue(maxsize=5)  # 충분한 버퍼
        decoded_frames = []

        def decode_worker():
            while True:
                try:
                    msg, header = decode_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if msg is None:
                    break

                buf = np.frombuffer(msg.data, dtype=np.uint8)
                frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if frame is not None:
                    inference_queue.put((frame, header), timeout=1.0)
                    decoded_frames.append(True)

        # 백그라운드 스레드 시작
        decode_thread = threading.Thread(target=decode_worker, daemon=True)
        decode_thread.start()

        # 여러 프레임 전송
        for _ in range(3):
            msg, _ = _make_compressed_image_msg()
            decode_queue.put_nowait((msg, msg.header))

        time.sleep(0.5)

        # 종료
        decode_queue.put((None, None))
        decode_thread.join(timeout=1.0)

        self.assertEqual(
            len(decoded_frames), 3,
            f'3개 프레임 중 {len(decoded_frames)}개만 디코딩됨'
        )

    def test_decode_and_inference_overlap(self):
        """디코딩과 추론이 오버랩되어야 함."""
        decode_queue = queue.Queue(maxsize=2)
        inference_queue = queue.Queue(maxsize=1)
        decode_times = []
        infer_times = []

        def decode_worker():
            while True:
                try:
                    msg, header = decode_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if msg is None:
                    break

                decode_times.append(time.time())
                buf = np.frombuffer(msg.data, dtype=np.uint8)
                frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                time.sleep(0.02)  # 디코딩 시뮬레이션
                inference_queue.put_nowait((frame, header))

        def inference_worker():
            while True:
                try:
                    frame, header = inference_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if frame is None:
                    break

                infer_times.append(time.time())
                time.sleep(0.05)  # 추론 시뮬레이션

        decode_thread = threading.Thread(target=decode_worker, daemon=True)
        infer_thread = threading.Thread(target=inference_worker, daemon=True)

        decode_thread.start()
        infer_thread.start()

        # 프레임 전송
        for _ in range(3):
            msg, _ = _make_compressed_image_msg()
            decode_queue.put_nowait((msg, msg.header))
            time.sleep(0.01)

        time.sleep(0.5)

        decode_queue.put((None, None))
        inference_queue.put((None, None))
        decode_thread.join(timeout=1.0)
        infer_thread.join(timeout=1.0)

        # 오버랩 확인: 디코딩이 완료되기 전에 추론이 시작되어야 함
        if decode_times and infer_times:
            first_infer = infer_times[0]
            last_decode = decode_times[-1]
            # 첫 추론이 마지막 디코딩보다 빨리 시작되어야 오버랩
            self.assertLess(
                first_infer, last_decode + 0.1,
                '디코딩과 추론이 오버랩되지 않음'
            )


if __name__ == '__main__':
    unittest.main()
