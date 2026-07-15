import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
import cv2


class CameraNode(Node):
    """
    카메라 영상을 구독하여 ROS2 토픽으로 발행하는 노드
    
    역할:
    - USB 카메라 또는 웹캠에서 영상 프레임을 읽음
    - OpenCV 이미지를 ROS2 Image 메시지로 변환
    - /camera/image_raw 토픽으로 발행
    
    파라미터:
    - ~camera_id: 카메라 인덱스 (기본값: 0)
    - ~frame_width: 프레임 너비 (기본값: 640)
    - ~frame_height: 프레임 높이 (기본값: 480)
    - ~fps: 초당 프레임 수 (기본값: 30)
    """

    def __init__(self):
        super().__init__('camera_node')
        
        # 파라미터 선언 및 설정
        # ROS2 파라미터는 실행 시점에 값을 변경할 수 있음
        # 예: ros2 run camera_node_pkg camera_node --ros-args -p camera_id:=1
        self.declare_parameter('camera_id', 0)
        self.declare_parameter('frame_width', 640)
        self.declare_parameter('frame_height', 480)
        self.declare_parameter('fps', 30)
        
        # 파라미터 값 가져오기
        self.camera_id = self.get_parameter('camera_id').value
        self.frame_width = self.get_parameter('frame_width').value
        self.frame_height = self.get_parameter('frame_height').value
        self.fps = self.get_parameter('fps').value
        
        # 카메라 초기화
        self.cap = cv2.VideoCapture(self.camera_id)
        if not self.cap.isOpened():
            self.get_logger().error(f'카메라 {self.camera_id}를 열 수 없습니다.')
            return
        
        # 카메라 해상도 설정
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        
        # 발행자 생성
        # queue_size=10: 버퍼 크기 (최근 10개 메시지 유지)
        self.publisher_ = self.create_publisher(Image, 'camera/image_raw', 10)
        
        # 타이머 생성 (프레임 전송 간격)
        # 1/fps초마다 publish_image 콜백 함수 실행
        timer_period = 1.0 / self.fps
        self.timer = self.create_timer(timer_period, self.publish_image)
        
        self.get_logger().info(
            f'카메라 노드 시작: 카메라 {self.camera_id}, '
            f'{self.frame_width}x{self.frame_height} @ {self.fps}fps'
        )

    def publish_image(self):
        """카메라 프레임을 읽어 ROS2 토픽으로 발행"""
        
        # 카메라에서 프레임 읽기
        ret, frame = self.cap.read()
        if not ret:
            self.get_logger().warn('프레임을 읽을 수 없습니다.')
            return
        
        # OpenCV BGR 이미지를 ROS2 Image 메시지로 변환
        image_msg = Image()
        image_msg.header.stamp = self.get_clock().now().to_msg()
        image_msg.header.frame_id = 'camera_frame'
        image_msg.height = frame.shape[0]  # 프레임 높이
        image_msg.width = frame.shape[1]   # 프레임 너비
        image_msg.encoding = 'bgr8'        # OpenCV는 기본적으로 BGR 포맷
        image_msg.is_bigendian = False
        image_msg.step = frame.shape[1] * 3  # 너비 * 3채널(RGB)
        image_msg.data = frame.tobytes()     #numpy 배열을 바이트로 변환
        
        # 토픽 발행
        self.publisher_.publish(image_msg)

    def destroy_node(self):
        """노드 종료 시 카메라 리소스 해제"""
        if self.cap.isOpened():
            self.cap.release()
        super().destroy_node()


def main(args=None):
    """노드 실행 함수"""
    rclpy.init(args=args)
    camera_node = CameraNode()
    
    try:
        rclpy.spin(camera_node)  # 노드가 종료될 때까지 대기
    except KeyboardInterrupt:
        pass
    finally:
        camera_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
