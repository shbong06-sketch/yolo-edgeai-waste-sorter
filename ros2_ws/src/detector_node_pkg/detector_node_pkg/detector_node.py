import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray, Detection2D, ObjectHypothesisWithPose, ObjectHypothesis
from std_msgs.msg import Header
import cv2
import numpy as np
from ultralytics import YOLO
import torch


class DetectorNode(Node):
    """
    YOLO 기반 객체 탐지 노드
    
    역할:
    - /camera/image_raw 토픽에서 이미지를 수신
    - YOLO 모델로 객체 탐지 수행
    - 탐지 결과를 /detection_results 토픽으로 발행
    
    파라미터:
    - ~model_path: YOLO 모델 파일 경로 (.pt)
    - ~conf_threshold: 탐지 신뢰도 임계값 (0.0 ~ 1.0)
    - ~iou_threshold: NMS IoU 임계값
    - ~device: 추론 디바이스 ("cpu" 또는 "cuda")
    """

    def __init__(self):
        super().__init__('detector_node')
        
        # 1. 파라미터 선언 및 설정
        self.declare_parameter('model_path', 'best.pt')
        self.declare_parameter('conf_threshold', 0.5)
        self.declare_parameter('iou_threshold', 0.45)
        self.declare_parameter('device', 'cpu')
        
        # 파라미터 값 가져오기
        self.model_path = self.get_parameter('model_path').value
        self.conf_threshold = self.get_parameter('conf_threshold').value
        self.iou_threshold = self.get_parameter('iou_threshold').value
        self.device = self.get_parameter('device').value
        
        # 2. YOLO 모델 로드
        self.get_logger().info(f'모델 로딩: {self.model_path}')
        self.model = YOLO(self.model_path)
        
        # GPU 사용 가능 여부 확인
        if self.device == 'cuda' and not torch.cuda.is_available():
            self.get_logger().warn('GPU를 사용할 수 없습니다. CPU로 전환합니다.')
            self.device = 'cpu'
        
        self.get_logger().info(f'추론 디바이스: {self.device}')
        
        # 3. 구독자 생성 (/camera/image_raw)
        # queue_size=10: 최근 10개 프레임 유지
        # 카메라 노드에서 발행하는 Image 메시지를 구독
        self.subscription = self.create_subscription(
            Image,
            'camera/image_raw',
            self.image_callback,
            10
        )
        
        # 4. 발행자 생성 (/detection_results)
        # 탐지 결과를 Detection2DArray로 발행
        self.publisher_ = self.create_publisher(
            Detection2DArray,
            'detection_results',
            10
        )

        # [추가] 바운딩 박스가 그려진 디버깅용 이미지 토픽 발행자 생성
        self.image_publisher_ = self.create_publisher(
            Image,
            'detection/image_raw',
            10
        )
        
        self.get_logger().info('객체 탐지 노드 시작됨')

    def image_callback(self, msg):
        """
        이미지 수신 콜백 함수
        
        역할:
        1. ROS2 Image 메시지를 OpenCV 이미지로 변환
        2. YOLO 추론 실행
        3. 결과를 Detection2DArray로 변환하여 발행
        """
        
        # 1. ROS2 Image → OpenCV 변환
        # Image 메시지의 data 필드를 numpy 배열로 변환
        frame = self.imgmsg_to_cv2(msg)
        
        # 2. YOLO 추론 실행
        results = self.model.predict(
            source=frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False  # 로그 출력 억제
        )
        
        # 3. 결과를 Detection2DArray로 변환
        detection_msg = self.convert_to_detection_msg(results, msg.header)
        
        # 4. 탐지 결과 발행
        self.publisher_.publish(detection_msg)


        # [추가] YOLO 결과를 이미지 위에 그리고 시각화 토픽으로 발행
        if results and len(results) > 0:
            # YOLO가 제공하는 자동 렌더링(바운딩 박스 + 라벨 그리기) 기능 호출
            annotated_frame = results[0].plot()
            
            # 그려진 OpenCV 이미지를 다시 ROS2 Image 메시지로 변환
            annotated_msg = self.cv2_to_imgmsg(annotated_frame, msg.header)
            
            # 이미지 토픽 송출!
            self.image_publisher_.publish(annotated_msg)

        
        # 탐지된 객체 상세 로깅
        for i, det in enumerate(detection_msg.detections):
            class_name = det.results[0].hypothesis.class_id
            score = det.results[0].hypothesis.score
            cx = det.bbox.center.position.x
            cy = det.bbox.center.position.y
            w = det.bbox.size_x
            h = det.bbox.size_y
            self.get_logger().info(
                f'탐지 [{i}] {class_name} (신뢰도: {score:.2f}) '
                f'위치: ({cx:.0f}, {cy:.0f}) 크기: {w:.0f}x{h:.0f}'
            )

    def imgmsg_to_cv2(self, msg):
        """
        ROS2 Image 메시지를 OpenCV 이미지로 변환
        
        Args:
            msg: sensor_msgs/msg/Image
            
        Returns:
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
        
        # numpy 배열로 변환
        img = np.frombuffer(msg.data, dtype=dtype)
        img = img.reshape((msg.height, msg.width, channels))
        
        # RGB인 경우 BGR로 변환 (OpenCV는 BGR 사용)
        if msg.encoding == 'rgb8':
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        
        return img
    
    # [추가] OpenCV 이미지를 부드럽게 ROS2 이미지 장부로 변환해주는 순정 함수
    def cv2_to_imgmsg(self, img, header):
        msg = Image()
        msg.header = header
        msg.height = img.shape[0]
        msg.width = img.shape[1]
        msg.encoding = 'bgr8'
        msg.is_bigendian = 0
        msg.step = img.shape[1] * 3
        msg.data = img.tobytes()
        return msg

    def convert_to_detection_msg(self, results, header):
        """
        YOLO 결과를 Detection2DArray 메시지로 변환
        
        Args:
            results: YOLO 추론 결과
            header: 원본 이미지의 헤더 (타임스탬프 유지)
            
        Returns:
            vision_msgs/msg/Detection2DArray
        """
        detection_msg = Detection2DArray()
        detection_msg.header = header  # 원본 이미지 타임스탬프 유지
        
        # 탐지 결과가 없으면 빈 메시지 반환
        if not results or len(results) == 0:
            return detection_msg
        
        # 첫 번째 결과 사용 (단일 이미지 추론)
        result = results[0]
        boxes = result.boxes
        
        if boxes is None or len(boxes) == 0:
            return detection_msg
        
        # 각 바운딩박스를 Detection2D로 변환
        for box in boxes:
            detection = Detection2D()
            
            # 바운딩박스 좌표 (좌상단, 우하단)
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            
            # 중심점과 크기 계산 (BoundingBox2D 형식)
            center_x = (x1 + x2) / 2.0
            center_y = (y1 + y2) / 2.0
            width = x2 - x1
            height = y2 - y1
            
            # 바운딩박스 설정
            detection.bbox.center.position.x = center_x
            detection.bbox.center.position.y = center_y
            detection.bbox.size_x = width
            detection.bbox.size_y = height
            
            # 클래스 ID 및 신뢰도
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            
            # 클래스 이름 가져오기 (모델의 class_names 사용)
            class_name = result.names[cls_id]
            
            # ObjectHypothesisWithPose 생성
            hypothesis = ObjectHypothesisWithPose()
            hypothesis.hypothesis.class_id = class_name
            hypothesis.hypothesis.score = conf
            
            detection.results.append(hypothesis)
            
            # Detection2D에 추가
            detection_msg.detections.append(detection)
        
        return detection_msg


def main(args=None):
    """노드 실행 함수"""
    rclpy.init(args=args)
    detector_node = DetectorNode()
    
    try:
        rclpy.spin(detector_node)  # 노드가 종료될 때까지 대기
    except KeyboardInterrupt:
        pass
    finally:
        detector_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
