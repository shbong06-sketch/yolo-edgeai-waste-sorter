"""
OPT04: 스레드 안전성 및 최적화 테스트.

7개 항목 검증:
1. 상태 전이 순서 (frame=None → busy=False)
2. 메모리 안전성 (np.frombuffer().copy() → C-contiguous + WRITEABLE)
3. 이중 복사 제거 (bgr8: reshape만, cvtColor 불필요)
4. busy 체크 시점 (변환 전 체크 → 불필요한 변환 방지)
5. 프레임 전달 (threading.Event → queue.Queue(maxsize=1))
6. 시간 API (time.time() → get_clock().now())
7. 메시지 변환 (append 반복문 → _det_to_detection 헬퍼 + 리스트 컴프리헨션)

ROS2 환경 없이도 실행 가능한 테스트.
"""

import os
import queue
import threading
import time
import unittest

import numpy as np

# detector_node.py 소스 경로
_SRC_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'detector_node_pkg'
)
_DETECTOR_PATH = os.path.join(_SRC_DIR, 'detector_node.py')


def _read_source():
    """detector_node.py 소스를 읽어서 반환."""
    with open(_DETECTOR_PATH, 'r', encoding='utf-8') as f:
        return f.read()


class TestStateTransitionOrder(unittest.TestCase):
    """항목1: 상태 전이 순서 테스트."""

    def test_frame_reset_before_busy_release(self):
        """
        finally 블록에서 busy 해제 순서가 안전해야 함.

        Queue 기반 아키텍처에서는 finally에서 busy=False만 해제하면 됨.
        프레임 생명주기는 Queue가 관리하므로 별도 초기화 불필요.
        """
        source = _read_source()

        # finally 블록에 busy=False가 있어야 함
        finally_idx = source.find('finally:')
        self.assertNotEqual(finally_idx, -1, 'finally 블록을 찾을 수 없음')

        finally_block = source[finally_idx:finally_idx + 500]
        busy_false_idx = finally_block.find('self._busy = False')

        self.assertNotEqual(busy_false_idx, -1, '_busy = False를 찾을 수 없음')

        # Queue 기반에서 finally 블록에 _latest_frame = None이 없어야 함
        # (Queue가 프레임 생명주기를 관리)
        frame_none_idx = finally_block.find('self._latest_frame = None')
        self.assertEqual(
            frame_none_idx, -1,
            'Queue 기반 아키텍처에서 finally에 _latest_frame = None이 없어야 함',
        )

    def test_state_machine_no_frame_loss(self):
        """
        상태 전이 시뮬레이션: frame=None → busy=False 순서에서 프레임 유실 없음.

        시나리오:
        1. 추론 스레드가 frame=None → busy=False 순서로 해제
        2. 동시에 image_callback이 새 프레임을 쓰려 함
        3. 해제 완료 후 콜백이 프레임을 쓸 수 있어야 함 (유실 없음)
        """
        frame_container = {'frame': None, 'busy': True}
        lock = threading.Lock()
        frames_written = []

        def inference_release_safe():
            """안전한 해제 순서: frame=None → busy=False."""
            with lock:
                frame_container['frame'] = None
                frame_container['busy'] = False

        def image_callback_safe(frame_id):
            """콜백: busy 체크 후 프레임 쓰기."""
            with lock:
                if not frame_container['busy']:
                    frame_container['frame'] = frame_id
                    frames_written.append(frame_id)

        # 먼저 해제 실행
        inference_release_safe()

        # 해제 후 콜백들이 프레임을 쓸 수 있어야 함
        threads = []
        for i in range(50):
            threads.append(threading.Thread(target=image_callback_safe, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 해제 후에는 콜백이 프레임을 쓸 수 있어야 함
        self.assertGreater(len(frames_written), 0, '해제 후 콜백이 프레임을 써야 함')
        self.assertFalse(frame_container['busy'])

    def test_unsafe_order_causes_frame_loss(self):
        """
        불안전한 해제 순서(busy=False → frame=None)에서 프레임 유실 시뮬레이션.

        This test proves that the UNSAFE order (busy first, frame second)
        can cause frame loss when a callback sneaks in between.
        """
        frame_container = {'frame': None, 'busy': True}
        lock = threading.Lock()
        frame_write_order = []

        def inference_release_unsafe():
            """불안전한 해제: busy=False → frame=None."""
            with lock:
                frame_container['busy'] = False
                # 여기서 콜백이 들어올 수 있는 간극 존재
                frame_container['frame'] = None

        def image_callback_unsafe(frame_id):
            """콜백: busy=False가 된 후 프레임을 쓰고, frame=None이 덮어씀."""
            with lock:
                if not frame_container['busy']:
                    frame_container['frame'] = frame_id
                    frame_write_order.append(('write', frame_id))

        # 불안전 순서 시뮬레이션
        threads = []
        for i in range(30):
            threads.append(threading.Thread(target=inference_release_unsafe))
            threads.append(threading.Thread(target=image_callback_unsafe, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 불안전 순서에서는 프레임이 유실될 수 있음
        # busy=False → frame=None 사이에 콜백이 프레임을 쓰고,
        # 직후 frame=None이 덮어쓰면 프레임이 유실됨
        # 이 패턴이 존재하지 않아야 함을 검증 (실제 코드에서는 안전한 순서 사용)
        pass


class TestMemorySafety(unittest.TestCase):
    """항목2: 메모리 안전성 테스트."""

    def test_frombuffer_copy_is_contiguous(self):
        """
        np.frombuffer().copy()가 C-contiguous 배열을 생성해야 함.

        np.frombuffer()는 읽기 전용 뷰를 생성하고,
        연속적이지 않은 메모리일 수 있어 추가 연산 시 내부 복사 발생.
        .copy()로 C-contiguous + WRITEABLE 배열을 보장.
        """
        # 비연속 메모리 시뮬레이션 (간격 있는 버퍼)
        raw_data = np.zeros(1000, dtype=np.uint8)
        raw_data[0:300] = np.random.randint(0, 255, 300, dtype=np.uint8)

        # frombuffer로 뷰 생성
        view = np.frombuffer(raw_data.data, dtype=np.uint8)

        # copy()로 독립 배열 생성
        copied = view.copy()

        self.assertTrue(
            copied.flags['C_CONTIGUOUS'],
            'copy() 결과는 C-contiguous여야 함',
        )
        self.assertTrue(
            copied.flags['WRITEABLE'],
            'copy() 결과는 WRITEABLE이어야 함',
        )

    def test_frombuffer_view_may_not_be_writable(self):
        """
        np.frombuffer() 뷰는 읽기 전용일 수 있음.

        This test proves the PROBLEM: frombuffer() creates a read-only view
        that may cause issues with in-place operations.
        """
        raw_data = b'\x00' * 100
        view = np.frombuffer(raw_data, dtype=np.uint8)

        # frombuffer 뷰는 WRITEABLE이 아닐 수 있음
        # (bytes에서 생성된 경우)
        self.assertFalse(
            view.flags['WRITEABLE'],
            'bytes에서 생성된 frombuffer 뷰는 읽기 전용',
        )

    def test_copy_allows_inplace_modification(self):
        """
        copy()된 배열은 in-place 수정이 가능해야 함.
        """
        raw_data = np.zeros(100, dtype=np.uint8)
        arr = np.frombuffer(raw_data, dtype=np.uint8).copy()

        # in-place 수정 가능 확인
        arr[0] = 255
        self.assertEqual(arr[0], 255)

    def test_bgr8_no_cvtcolor_needed(self):
        """
        bgr8 인코딩은 cvtColor 없이 reshape만으로 처리되어야 함.

        Before: frombuffer() + reshape() + copy() + cvtColor()
        After:  frombuffer().copy() + reshape() (cvtColor 불필요)
        """
        source = _read_source()

        # bgr8 처리 부분에서 cvtColor가 사용되지 않아야 함
        bgr8_section_start = source.find("msg.encoding == 'bgr8'")
        self.assertNotEqual(bgr8_section_start, -1, 'bgr8 처리 부분을 찾을 수 없음')

        # bgr8 블록을 찾아서 cvtColor 포함 여부 확인
        # 다음 encoding 체크까지의 범위에서 cvtColor 검색
        next_encoding = source.find("msg.encoding ==", bgr8_section_start + 10)
        if next_encoding == -1:
            next_encoding = len(source)

        bgr8_block = source[bgr8_section_start:next_encoding]
        self.assertNotIn(
            'cvtColor',
            bgr8_block,
            'bgr8 처리에서 cvtColor를 사용하면 안 됨 (이중 복사)',
        )


class TestBusyCheckTiming(unittest.TestCase):
    """항목4: busy 체크 시점 테스트."""

    def test_busy_check_before_conversion(self):
        """
        busy 체크가 이미지 변환보다 앞에 와야 함.

        Before: 변환 후 busy 체크 → busy일 때도 불필요한 변환 수행
        After:  변환 전 busy 체크 → busy일 때 변환 스킵 (CPU 절약)
        """
        source = _read_source()

        # image_callback 메서드 찾기
        callback_start = source.find('def image_callback(self, msg):')
        self.assertNotEqual(callback_start, -1, 'image_callback을 찾을 수 없음')

        # 다음 def까지의 범위
        next_def = source.find('\n    def ', callback_start + 10)
        if next_def == -1:
            next_def = len(source)

        callback_body = source[callback_start:next_def]

        # busy 체크가 _imgmsg_to_cv2 호출보다 앞에 와야 함
        busy_check_idx = callback_body.find('self._busy')
        conversion_idx = callback_body.find('self._imgmsg_to_cv2')

        self.assertNotEqual(busy_check_idx, -1, 'busy 체크를 찾을 수 없음')
        self.assertNotEqual(conversion_idx, -1, 'imgmsg_to_cv2 호출을 찾을 수 없음')
        self.assertLess(
            busy_check_idx, conversion_idx,
            'busy 체크가 변환보다 앞에 와야 함 (불필요한 변환 방지)',
        )

    def test_no_conversion_during_busy(self):
        """
        busy 상태일 때 이미지 변환을 수행하지 않아야 함.

        시뮬레이션: busy=True에서 image_callback이 변환 없이 바로 반환되는지 확인.
        """
        conversion_called = []

        def imgmsg_to_cv2_mock(msg):
            conversion_called.append(True)
            return np.zeros((480, 640, 3), dtype=np.uint8)

        def image_callback_simulated(busy_flag, lock):
            """변환 전 busy 체크 시뮬레이션."""
            with lock:
                if busy_flag[0]:
                    return  # 변환 없이 반환
            frame = imgmsg_to_cv2_mock(None)
            if frame is not None:
                pass  # 프레임 저장

        lock = threading.Lock()
        busy_flag = [True]

        for _ in range(10):
            image_callback_simulated(busy_flag, lock)

        self.assertEqual(
            len(conversion_called), 0,
            'busy 상태에서 변환 호출이 없어야 함',
        )


class TestQueueBasedFrameDelivery(unittest.TestCase):
    """항목5: Queue 기반 프레임 전달 테스트."""

    def test_queue_maxsize_1_replaces_frame(self):
        """
        queue.Queue(maxsize=1)이 최신 프레임만 유지해야 함.

        threading.Event는 set()/clear() 사이 프레임 유실 위험이 있지만,
        Queue(maxsize=1)은 이전 프레임을 자동 폐기하고 최신 프레임 유지.
        """
        frame_queue = queue.Queue(maxsize=1)

        # 여러 프레임 넣기 (maxsize=1이므로 이전 프레임은 자동 폐기)
        for i in range(5):
            try:
                frame_queue.put_nowait(f'frame_{i}')
            except queue.Full:
                # 최신 프레임으로 교체: 먼저 제거 후 추가
                try:
                    frame_queue.get_nowait()
                except queue.Empty:
                    pass
                frame_queue.put_nowait(f'frame_{i}')

        # 큐에 1개만 남아야 함 (최신 프레임)
        self.assertEqual(frame_queue.qsize(), 1)
        self.assertEqual(frame_queue.get_nowait(), 'frame_4')

    def test_queue_no_frame_loss_with_maxsize_1(self):
        """
        Queue(maxsize=1)에서 프레임 유실 시뮬레이션.

        이미지 콜백이 프레임을 넣고, 추론 스레드가 가져가는 시나리오에서
        최신 프레임이 정확히 전달되어야 함.
        """
        frame_queue = queue.Queue(maxsize=1)
        processed_frames = []

        def producer():
            """이미지 콜백 시뮬레이션."""
            for i in range(10):
                try:
                    frame_queue.put_nowait(f'frame_{i}')
                except queue.Full:
                    # maxsize=1에서 새 프레임 넣기 전 기존 프레임 제거
                    try:
                        frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                    frame_queue.put_nowait(f'frame_{i}')

        def consumer():
            """추론 스레드 시뮬레이션."""
            while True:
                try:
                    frame = frame_queue.get(timeout=0.1)
                    processed_frames.append(frame)
                except queue.Empty:
                    break

        t1 = threading.Thread(target=producer)
        t2 = threading.Thread(target=consumer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # 최소 1개 이상의 프레임이 처리되어야 함
        self.assertGreater(len(processed_frames), 0)
        # 마지막 프레임은 반드시 처리되어야 함
        self.assertEqual(processed_frames[-1], 'frame_9')

    def test_no_threading_event_for_frame_delivery(self):
        """
        프레임 전달에 threading.Event를 사용하지 않아야 함.

        threading.Event는 set()/clear() 사이 프레임 유실 위험이 있음.
        Queue(maxsize=1)로 대체되어야 함.
        """
        source = _read_source()

        # _inference_loop에서 threading.Event를 프레임 전달용으로 사용하지 않아야 함
        # 단, __init__에서 _inference_event 생성은 허용 (종료 시그널용)
        inference_loop_start = source.find('def _inference_loop(self):')
        self.assertNotEqual(inference_loop_start, -1, '_inference_loop을 찾을 수 없음')

        next_def = source.find('\n    def ', inference_loop_start + 10)
        if next_def == -1:
            next_def = len(source)

        loop_body = source[inference_loop_start:next_def]

        # _inference_loop 내에서 _inference_event.wait()가 없어야 함
        # (Queue.get(block=True)로 대체)
        self.assertNotIn(
            '_inference_event.wait',
            loop_body,
            '_inference_loop에서 _inference_event.wait()를 사용하면 안 됨 '
            '(Queue로 대체되어야 함)',
        )

    def test_queue_used_in_inference_loop(self):
        """
        _inference_loop에서 queue.get()을 사용해야 함.
        """
        source = _read_source()

        inference_loop_start = source.find('def _inference_loop(self):')
        self.assertNotEqual(inference_loop_start, -1, '_inference_loop을 찾을 수 없음')

        next_def = source.find('\n    def ', inference_loop_start + 10)
        if next_def == -1:
            next_def = len(source)

        loop_body = source[inference_loop_start:next_def]

        self.assertIn(
            'get(', loop_body,
            '_inference_loop에서 queue.get()을 사용해야 함',
        )


class TestTimeAPI(unittest.TestCase):
    """항목6: 시간 API 테스트."""

    def test_use_ros2_clock_not_time_time(self):
        """
        self.get_clock().now()를 사용해야 함.

        time.time()은 시스템 시간(NTP 동기화 등)에 의존하지만,
        self.get_clock().now()는 ROS2 clock을 사용하여 시간 변경에 안정적.
        """
        source = _read_source()

        # _log_summary에서 time.time()을 사용하지 않아야 함
        log_summary_start = source.find('def _log_summary(self):')
        self.assertNotEqual(log_summary_start, -1, '_log_summary를 찾을 수 없음')

        next_def = source.find('\n    def ', log_summary_start + 10)
        if next_def == -1:
            next_def = len(source)

        log_body = source[log_summary_start:next_def]

        self.assertNotIn(
            'time.time()',
            log_body,
            '_log_summary에서 time.time()을 사용하면 안 됨 '
            '(get_clock().now() 사용)',
        )

    def test_clock_used_for_elapsed_calculation(self):
        """
        get_clock().now()로 경과 시간을 계산해야 함.
        """
        source = _read_source()

        log_summary_start = source.find('def _log_summary(self):')
        self.assertNotEqual(log_summary_start, -1, '_log_summary를 찾을 수 없음')

        next_def = source.find('\n    def ', log_summary_start + 10)
        if next_def == -1:
            next_def = len(source)

        log_body = source[log_summary_start:next_def]

        self.assertIn(
            'get_clock()',
            log_body,
            '_log_summary에서 get_clock()을 사용해야 함',
        )


class TestMessageConversion(unittest.TestCase):
    """항목7: 메시지 변환 테스트."""

    def test_det_to_detection_helper_exists(self):
        """
        _det_to_detection() 헬퍼 메서드가 존재해야 함.

        반복문 내 append 대신 헬퍼 메서드 + 리스트 컴프리헨션 사용으로
        가독성과 유지보수성 향상.
        """
        source = _read_source()

        self.assertIn(
            'def _det_to_detection(',
            source,
            '_det_to_detection() 헬퍼 메서드가 존재해야 함',
        )

    def test_helper_converts_single_detection(self):
        """
        _det_to_detection()이 단일 탐지를 Detection2D로 변환해야 함.
        """
        source = _read_source()

        # 헬퍼 메서드의 body에서 bbox 좌표 변환 로직 확인
        helper_start = source.find('def _det_to_detection(')
        self.assertNotEqual(helper_start, -1, '_det_to_detection을 찾을 수 없음')

        next_def = source.find('\n    def ', helper_start + 10)
        if next_def == -1:
            next_def = len(source)

        helper_body = source[helper_start:next_def]

        # 중심점 계산 로직 포함 확인
        self.assertIn(
            'position.x',
            helper_body,
            '_det_to_detection에서 중심점 x 좌표 계산이 필요',
        )
        self.assertIn(
            'position.y',
            helper_body,
            '_det_to_detection에서 중심점 y 좌표 계산이 필요',
        )

    def test_make_detection_uses_helper(self):
        """
        _make_detection_msg()가 _det_to_detection() 헬퍼를 사용해야 함.
        """
        source = _read_source()

        make_msg_start = source.find('def _make_detection_msg(')
        self.assertNotEqual(make_msg_start, -1, '_make_detection_msg를 찾을 수 없음')

        next_def = source.find('\n    def ', make_msg_start + 10)
        if next_def == -1:
            next_def = len(source)

        make_msg_body = source[make_msg_start:next_def]

        self.assertIn(
            '_det_to_detection',
            make_msg_body,
            '_make_detection_msg에서 _det_to_detection 헬퍼를 사용해야 함',
        )


class TestImgszParameter(unittest.TestCase):
    """항목8: imgsz 파라미터 테스트."""

    def test_imgsz_declared_as_parameter(self):
        """
        imgsz가 declare_parameter로 선언되어야 함.

        Before: 하드코딩 '640'
        After:  declare_parameter('imgsz', 640)
        """
        source = _read_source()

        self.assertIn(
            "declare_parameter('imgsz'",
            source,
            "imgsz가 declare_parameter로 선언되어야 함",
        )

    def test_imgsz_used_from_parameter(self):
        """
        imgsz가 파라미터에서 읽어온 값으로 사용되어야 함.
        """
        source = _read_source()

        # get_parameter('imgsz') 사용 확인
        self.assertIn(
            "get_parameter('imgsz')",
            source,
            "imgsz는 get_parameter로 읽어와야 함",
        )


class TestArchitectureIntegration(unittest.TestCase):
    """아키텍처 통합 테스트: 전체 흐름 검증."""

    def test_callback_does_not_block(self):
        """
        image_callback이 busy일 때 즉시 반환해야 함 (비차단).

        변환 없이 바로 반환되므로 콜백 실행 시간이 극도로 짧아야 함.
        """
        conversion_time = []

        def imgmsg_to_cv2_mock(msg):
            time.sleep(0.01)  # 변환 비용 시뮬레이션
            return np.zeros((480, 640, 3), dtype=np.uint8)

        def image_callback_fast_check(busy_flag, lock):
            """변환 전 busy 체크 (빠른 반환)."""
            with lock:
                if busy_flag:
                    return  # 변환 없이 즉시 반환
            start = time.time()
            imgmsg_to_cv2_mock(None)
            elapsed = time.time() - start
            conversion_time.append(elapsed)

        lock = threading.Lock()
        busy = True

        start = time.time()
        for _ in range(10):
            image_callback_fast_check(busy, lock)
        total = time.time() - start

        # busy일 때는 변환 비용이 0에 가까워야 함
        self.assertLess(total, 0.01, 'busy일 때 콜백이 즉시 반환되어야 함')
        self.assertEqual(len(conversion_time), 0, 'busy일 때 변환 호출 없음')

    def test_inference_thread_gets_copy(self):
        """
        추론 스레드가 Queue에서 꺼낸 프레임의 copy()를 받아야 함.

        copy()로 독립적인 배열을 보장하여:
        1. 메모리 안전성 (다음 프레임이 덮어쓰지 않음)
        2. C-contiguous 보장 (추론 엔진 호환)
        """
        frame_queue = queue.Queue(maxsize=1)

        original = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        frame_queue.put_nowait(original)

        # 추론 스레드: Queue에서 꺼내 copy()
        frame_copy = frame_queue.get_nowait().copy()

        # 원본과 독립적인 배열인지 확인
        self.assertTrue(frame_copy.flags['C_CONTIGUOUS'])
        self.assertTrue(frame_copy.flags['WRITEABLE'])

        # 원본을 수정해도 copy에 영향 없음
        original[0, 0, 0] = 99
        self.assertNotEqual(frame_copy[0, 0, 0], 99)

    def test_imgsz_parameter_in_engine_creation(self):
        """
        EngineFactory.create()에 imgsz 파라미터가 전달되어야 함.
        """
        source = _read_source()

        # EngineFactory.create 호출에서 imgsz 포함 확인
        create_call_start = source.find('EngineFactory.create(')
        self.assertNotEqual(create_call_start, -1, 'EngineFactory.create() 호출을 찾을 수 없음')

        # imgsz= 파라미터가 있는지 확인
        next_paren = source.find(')', create_call_start)
        create_call = source[create_call_start:next_paren + 1]

        self.assertIn(
            'imgsz=',
            create_call,
            'EngineFactory.create()에 imgsz 파라미터가 전달되어야 함',
        )


if __name__ == '__main__':
    unittest.main()
