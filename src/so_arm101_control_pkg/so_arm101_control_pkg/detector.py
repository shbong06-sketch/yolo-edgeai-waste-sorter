import rclpy

from rclpy.node import Node
from vision_msgs.msg import Detection2DArray, Detection2D, ObjectHypothesisWithPose

from rcl_interfaces.msg import SetParametersResult

import random

IMG_SIZE = (640, 480)

classNames = ["CAN", "PET", "STYLOFOAM"]

class PositionMaker(Node):
    def __init__(self):
        super().__init__("position_maker")

        # 검출된 객체정보 : 클래스, 위치정보, 스코어
        self.dectect_positions = {}

        self.declare_parameter("interval", 10.0)
        self.pub_interval = self.get_parameter("interval").value

        # 객체 위치 전송용 퍼블리셔 생성
        self.positionPublisher = self.create_publisher(
            Detection2DArray, "topcam/position_maker", 10
        )


        self.add_on_set_parameters_callback(self.on_params_changed)

        self.pubTimer = self.create_timer(10.0, self.tick_publish)


    def on_params_changed(self, params):
        for param in params:
            self.get_logger().info(f"파라미터 변경이 요청되었습니다. {param.name} : {param.value}")

            if param.name == "interval":
                if not 0 < param.value < 30.0:
                    return SetParametersResult(successful = False, reason = "타이머 주기가 0보다 작거나 30초보다 큼")

                self.pub_interval = param.value
                self.pubTimer.reset()

                self.get_logger().info(f"위치발행 타이머 주기가 변경 되었습니다. -> {self.pub_interval}")
                return SetParametersResult(successful = True)

    
    def generate_random_detectionYOLO(self, objectcnt=1):
        detections = []
        indx = 0
        for _ in range(objectcnt):

            det = Detection2D()

            # 가로, 세로 margin 100 범위 내 임의 좌표 및 박스 생성.
            det.bbox.center.position.x = float(random.randint(100, IMG_SIZE[0] - 100))
            det.bbox.center.position.y = float(random.randint(100, IMG_SIZE[1] - 100))
            det.bbox.size_x = det.bbox.size_y = 80.0

            # 분류결과 클래스 하나 임의 생성.
            ObjHypothesis = ObjectHypothesisWithPose()
            ObjHypothesis.hypothesis.class_id = classNames[random.randint(0, 2)]
            ObjHypothesis.hypothesis.score = 85.0 + random.random()
            det.results.append(ObjHypothesis)


            detections.append(det)

            indx+=1
        print(indx)
        return detections

    def tick_publish(self):
        msgDetection = Detection2DArray()

        # 헤더
        msgDetection.header.stamp = self.get_clock().now().to_msg()
        msgDetection.header.frame_id = "isaac_sim_topcam"

        object_cnt = random.randint(1, 3)

        detections = self.generate_random_detectionYOLO(object_cnt)
        msgDetection.detections.extend(
            detections
        ) 

        for detect2d in msgDetection.detections:
            det_class = detect2d.results[0].hypothesis
            self.get_logger().info(f"generated : class = {det_class.class_id} [{det_class.score}] \
                                   position = {detect2d.bbox.center}")
        
        self.positionPublisher.publish(msgDetection)


def main():
    rclpy.init()

    rclpy.spin(PositionMaker())

    rclpy.shutdown()


if __name__ == "__main__":
    main()