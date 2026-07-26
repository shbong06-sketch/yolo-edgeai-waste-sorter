"""
YOLO 기반 객체 탐지 ROS2 노드.

프레임 스킵과 멀티스레드 아키텍처를 통해 실시간 추론을 지원
"""

import queue
import threading

import cv2
import numpy as np
import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from vision_msgs.msg import (
    Detection2D,
    Detection2DArray,
    ObjectHypothesisWithPose,
)

from .inference_engine import EngineFactory


class DetectorNode(Node):
    """
    YOLO 기반 객체 탐지 노드.

    역할:
    - /camera/image_raw 토픽에서 이미지를 수신
    - YOLO 모델로 객체 탐지 수행
    - 탐지 결과를 /detection_results 토픽으로 발행

    파라미터:
    - ~model_path: YOLO 모델 파일 경로 (.pt 또는 .onnx)
    - ~conf_threshold: 탐지 신뢰도 임계값 (0.0 ~ 1.0)
    - ~iou_threshold: NMS IoU 임계값
    - ~device: 추론 디바이스 ("cpu" 또는 "cuda")
    - ~imgsz: 추론 입력 이미지 크기 (기본값: 640)

    추론 엔진 분기 (EngineFactory):
    - .pt 파일 → YoloEngine (ultralytics YOLO 사용)
    - .onnx 파일 → OnnxEngine (onnxruntime 직접 사용, CUDAExecutionProvider 지원)

    멀티스레드 아키텍처:
    - 메인 스레드: rclpy executor spinning (기타 콜백 처리)
    - 이미지 콜백: busy 체크 → 변환 → Queue 저장 (빠른 반환)
    - 추론 스레드: Queue.get() → copy() → 추론 → 결과 발행
    - 프레임 스킵: 추론 중 새 프레임은 자동 스킵 (Queue maxsize=1)
    """

    def __init__(self):
        """노드 초기화."""
        super().__init__('detector_node')

        # ── 1. 파라미터 선언 및 설정 ──
        self.declare_parameter('model_path', 'best.onnx')
        self.declare_parameter('conf_threshold', 0.5)
        self.declare_parameter('iou_threshold', 0.45)
        self.declare_parameter('device', 'cuda')
        self.declare_parameter('imgsz', 640)

        self.model_path = self.get_parameter('model_path').value
        self.conf_threshold = self.get_parameter('conf_threshold').value
        self.iou_threshold = self.get_parameter('iou_threshold').value
        self.device = self.get_parameter('device').value
        self.imgsz = self.get_parameter('imgsz').value

        # ── 2. 추론 엔진 초기화 ──
        self.get_logger().info(f'모델 로딩: {self.model_path}')
        self.engine = EngineFactory.create(
            self.model_path, device=self.device, imgsz=self.imgsz
        )
        self.get_logger().info(f'추론 디바이스: {self.device}')

        # ── 3. 프레임 스킵 상태 ──
        # _busy: 추론 스레드가 실행 중이면 True → 새 프레임 스킵
        self._busy = False
        self._frame_lock = threading.Lock()
        # 프레임 큐: 최신 프레임 1개만 유지 (이전 프레임 자동 폐기)
        self._frame_queue = queue.Queue(maxsize=1)
        # 프레임 스킵 카운터 (로깅용)
        self._frames_received = 0
        self._frames_skipped = 0

        # ── 4. 구독자 (MutuallyExclusiveCallbackGroup) ──
        # MutuallyExclusiveCallbackGroup: 이 그룹 내 콜백은 직렬 실행
        # → image_callback이 빠르게 종료되어 executor가 다른 콜백을 처리할 수 있음
        self._sub_group = MutuallyExclusiveCallbackGroup()
        self.subscription = self.create_subscription(
            Image,
            'camera/image_raw',
            self.image_callback,
            qos_profile_sensor_data,
            callback_group=self._sub_group,
        )

        # ── 5. 발행자 ──
        self.publisher_ = self.create_publisher(
            Detection2DArray,
            'detection_results',
            10
        )

        # ── 6. 요약 로깅 타이머 (1초 간격) ──
        # 핫패스에서 매 프레임 .info() 대신, 주기적으로 요약 정보 출력
        self._log_timer = self.create_timer(
            1.0, self._log_summary, callback_group=self._sub_group
        )
        self._log_timer_start = self.get_clock().now()

        # ── 7. 추론 스레드 시작 ──
        # 추론 루프를 백그라운드 스레드로 설정
        self._inference_thread = threading.Thread(
            target=self._inference_loop, daemon=True
        )

        self._running = True    # 루프 종료 플래그(False 되면 탈출)
        self._inference_thread.start()  # inference loop 병렬 실행

        self.get_logger().info('객체 탐지 노드 시작됨 (멀티스레드)')

    #  이미지 콜백 (빠른 프레임 저장)

    def image_callback(self, msg):
        """
        이미지 수신 콜백 (빠른 반환).

        역할: 최신 프레임을 저장하고 추론 스레드에 신호 전달.
        추론은 별도 스레드에서 실행되므로, 이 콜백은 즉시 반환됨.

        프레임 스킵 로직:
        - 추론 스레드가 실행 중(_busy=True)이면 새 프레임을 스킵
        - 추론 스레드가 대기 중이면 최신 프레임으로 교체
        """
        # busy 체크: 변환 전에 수행하여 불필요한 변환 방지 (CPU 절약)
        with self._frame_lock:
            if self._busy:
                self._frames_skipped += 1
                return

        # ROS2 Image → OpenCV 변환
        frame = self._imgmsg_to_cv2(msg)
        if frame is None:
            return

        self._frames_received += 1

        # 프레임 큐에 저장 (maxsize=1, 이전 프레임 자동 폐기)
        try:
            self._frame_queue.get_nowait()
        except queue.Empty:
            pass
        self._frame_queue.put_nowait((frame, msg.header))

    #  추론 스레드 (백그라운드 실행)

    def _inference_loop(self):
        """
        추론 스레드 메인 루프.

        Queue에서 프레임을 가져와 추론을 실행하고 결과를 발행.

        스레드 안전성:
        - _busy 플래그로 콜백과 추론 스레드 간 경쟁 조건 방지
        - queue.Queue로 프레임 전달 (최신 프레임 1개 유지)
        - onnxruntime 세션은 단일 스레드에서만 호출되므로 안전
        """
        while self._running:
            try:
                # Queue에서 프레임 수신 (1초 타임아웃으로 _running 체크)
                frame, header = self._frame_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # 프레임 복사 (독립 배열 확보: C-contiguous + WRITEABLE)
            frame = frame.copy()

            with self._frame_lock:
                self._busy = True

            try:
                # 추론 실행
                detections = self.engine.predict(
                    frame, conf=self.conf_threshold, iou=self.iou_threshold
                )

                # 결과 발행
                detection_msg = self._make_detection_msg(detections, header)
                self.publisher_.publish(detection_msg)

            except Exception as e:
                self.get_logger().error(f'추론 오류: {e}')

            finally:
                # 추론 완료 → frame=None 먼저 초기화 후 busy 해제 (race condition 방지)
                with self._frame_lock:
                    self._busy = False

    #  요약 로깅 (1초 간격)

    def _log_summary(self):
        """
        1초 간격으로 프레임 처리 요약 로깅.

        핫패스에서 매 프레임 .info() 대신, 주기적으로:
        - 수신 프레임 수
        - 스킵된 프레임 수
        - 스킵 비율
        """
        now = self.get_clock().now()
        elapsed = (now - self._log_timer_start).nanoseconds / 1e9
        if elapsed < 1.0:
            return

        received = self._frames_received
        skipped = self._frames_skipped
        processed = received - skipped
        skip_ratio = (skipped / received * 100) if received > 0 else 0.0

        self.get_logger().info(
            f'[1초 요약] 수신: {received}, 처리: {processed}, '
            f'스킵: {skipped} ({skip_ratio:.0f}%)'
        )

        # 카운터 리셋
        self._frames_received = 0
        self._frames_skipped = 0
        self._log_timer_start = now

    #  이미지 변환

    def _imgmsg_to_cv2(self, msg):
        """
        ROS2 Image 메시지를 OpenCV 이미지로 변환.

        Args:
            msg: sensor_msgs/msg/Image

        Returns
        -------
        numpy 배열 (OpenCV 이미지)

        """
        # 이미지 포맷에 따라 처리
        if msg.encoding == 'bgr8':
            # OpenCV 기본 포맷
            dtype = np.uint8
            channels = 3
        elif msg.encoding == 'rgb8':
            # RGB 포맷 (채널 순서 변경 필요)
            dtype = np.uint8
            channels = 3
        elif msg.encoding == 'mono8':
            # 그레이스케일
            dtype = np.uint8
            channels = 1
        else:
            self.get_logger().warn(f'지원하지 않는 인코딩: {msg.encoding}')
            return None

        # numpy 배열로 변환 (copy로 C-contiguous + WRITEABLE 보장)
        img = np.frombuffer(msg.data, dtype=dtype).copy()
        img = img.reshape((msg.height, msg.width, channels))

        # RGB인 경우 BGR로 변환 (OpenCV는 BGR 사용)
        if msg.encoding == 'rgb8':
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        return img

    def _det_to_detection(self, det: dict) -> Detection2D:
        """
        단일 탐지 결과(dict)를 Detection2D 메시지로 변환.

        Args:
            det: {"class_name": str, "confidence": float,
                  "bbox": [x1, y1, x2, y2]}

        Returns
        -------
        vision_msgs/msg/Detection2D

        """
        detection = Detection2D()

        x1, y1, x2, y2 = det['bbox']
        detection.bbox.center.position.x = (x1 + x2) / 2.0
        detection.bbox.center.position.y = (y1 + y2) / 2.0
        detection.bbox.size_x = x2 - x1
        detection.bbox.size_y = y2 - y1

        hypothesis = ObjectHypothesisWithPose()
        hypothesis.hypothesis.class_id = det['class_name']
        hypothesis.hypothesis.score = det['confidence']
        detection.results.append(hypothesis)

        return detection

    def _make_detection_msg(self, detections: list, header) -> Detection2DArray:
        """
        추론 결과(dict list)를 Detection2DArray 메시지로 변환.

        EngineFactory를 통해 생성된 엔진(YoloEngine/OnnxEngine)은
        공통 인터페이스로 list[dict]를 반환한다:
            [{"class_name": str, "confidence": float,
              "bbox": [x1, y1, x2, y2]}, ...]

        Args:
            detections: engine.predict()가 반환한 탐지 결과 리스트
            header: 원본 이미지의 헤더 (타임스탬프 유지)

        Returns
        -------
        vision_msgs/msg/Detection2DArray

        """
        detection_msg = Detection2DArray()
        detection_msg.header = header
        detection_msg.detections = [
            self._det_to_detection(det) for det in detections
        ]

        return detection_msg


def main(args=None):
    """
    노드 실행 함수.

    MultiThreadedExecutor 사용:
    - 메인 스레드: executor spinning (기타 콜백 처리)
    - 추론 스레드: _inference_loop (백그라운드 추론)
    """
    rclpy.init(args=args)
    detector_node = DetectorNode()

    # MultiThreadedExecutor: 멀티스레드 콜백 그룹 지원
    executor = MultiThreadedExecutor()
    executor.add_node(detector_node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        # 추론 스레드 종료 대기
        detector_node._running = False
        detector_node._inference_thread.join(timeout=3.0)
        detector_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
