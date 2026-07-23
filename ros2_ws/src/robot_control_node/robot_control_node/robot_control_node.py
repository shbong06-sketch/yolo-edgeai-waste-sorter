#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from action_msgs.msg import GoalStatus
import numpy as np
import threading
import time

from vision_msgs.msg import Detection2DArray
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from builtin_interfaces.msg import Duration
from sensor_msgs.msg import JointState 

class RobotControlNode(Node):

    def __init__(self):
        super().__init__('robot_control_node')
        
        self.declare_parameter('target_class', 'can')
        self.target_class = self.get_parameter('target_class').value
        
        # 캘리브레이션 행렬 로드
        npy_path = '/home/gt/yolo-edgeai-waste-sorter/AI/src/inference/homography_matrix.npy'
        try:
            self.H = np.load(npy_path)
            self.get_logger().info('캘리브레이션 행렬 파일 로드 완료!')
        except FileNotFoundError:
            self.get_logger().error(f'행렬 파일을 찾을 수 없습니다: {npy_path}')
            raise SystemExit
        
        self.main_cb_group = ReentrantCallbackGroup()
        
        # [중요] 레이스 컨디션 방지용 동기화 스레드 락 선언
        self.state_lock = threading.Lock()
        
        # 순정 액션 클라이언트 개방
        self._action_client = ActionClient(
            self,
            FollowJointTrajectory,
            '/follower/joint_trajectory_controller/follow_joint_trajectory',
            callback_group=self.main_cb_group
        )
        
        self.server_connected = False
        self.connection_thread = threading.Thread(target=self._connect_to_action_server, daemon=True)
        self.connection_thread.start()
        
        # 상태 머신 변수
        self.current_state = "IDLE"      
        self.saved_target_angles_6 = None  
        self.cmd_flex1_safe = 0.0  
        
        # 하드웨어 매핑 상수 및 오프셋 기준점
        self.joint_names = ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper']
        
        # 1. 하드웨어 날것의 원점 오프셋
        self.offset_pan   = 3.1738062501353914       
        self.offset_lift  = 1.3330293046726223      
        self.offset_flex1 = 4.535981189777841     
        self.offset_flex2 = 4.512971477959557   
        
        # 2. 스마트폰 실측 기반 기하학 기준점 동기화
        self.home_math_lift  = -0.1745     
        self.home_math_flex1 = -3.0543   
        
        # 어깨 감속비 보정 배율 (2.0 유지)
        self.scale_lift = 2.0
        
        # 고정 상수
        self.wrist_roll_val = 2.9805246708618007  
        self.gripper_open   = 3.80        
        
        self.gripper_close  = 2.70

        self.real_angles_6 = None  
        self.current_angles_6 = [self.offset_pan, self.offset_lift, self.offset_flex1, self.offset_flex2, self.wrist_roll_val, self.gripper_open]

        # YOLO 비전 구독
        self.subscription = self.create_subscription(
            Detection2DArray,
            'detection_results',
            self.detection_callback,
            10,
            callback_group=self.main_cb_group
        )
        
        # 실물 관절 상태 피드백 구독
        self.joint_state_sub = self.create_subscription(
            JointState,
            '/follower/joint_states',
            self.joint_state_callback,
            10,
            callback_group=self.main_cb_group
        )
        
        self.get_logger().info('=== 독자 스레드 격리형 무블로킹 액션 제어 노드 가동 ===')

    def _connect_to_action_server(self):
        while rclpy.ok():
            if self._action_client.wait_for_server(timeout_sec=1.0):
                self.server_connected = True
                self.get_logger().info(' [연결 성공] 로봇 하드웨어 액션 서버와 완벽히 동기화되었습니다!')
                break
            time.sleep(0.1)

    def joint_state_callback(self, msg):
        try:
            mapped_angles = []
            for name in self.joint_names:
                idx = msg.name.index(name)
                mapped_angles.append(msg.position[idx])
            self.real_angles_6 = mapped_angles
        except ValueError:
            pass 

    def detection_callback(self, msg):
        # 스레드 락을 걸어 여러 프레임이 동시에 IDLE 문턱을 넘지 못하게 차단[cite: 1]
        with self.state_lock:
            if self.current_state != "IDLE":
                return
            if not msg.detections:
                return
            if not self.server_connected:
                return

            for detection in msg.detections:
                class_name = detection.results[0].hypothesis.class_id
                if class_name.strip().lower() == self.target_class.strip().lower():
                    u = detection.bbox.center.position.x
                    v = detection.bbox.center.position.y
                    
                    robot_x, robot_y = self.convert_pixel_to_robot_space(u, v)
                    robot_z = 20.0  
                    
                    # 자가 오탐 및 가동 범위 외 예외 처리
                    if not (120.0 <= robot_x <= 400.0 and -250.0 <= robot_y <= 250.0):
                        return 
                    
                    self.get_logger().info(f' 캔 포착 성공 -> 월드 좌표: X={robot_x:.1f}mm, Y={robot_y:.1f}mm')
                    
                    joint_angles_6 = self.calculate_6_axis_positions(robot_x, robot_y, robot_z, self.gripper_open)
                    if joint_angles_6 is not None:
                        self.saved_target_angles_6 = joint_angles_6
                        
                        delta_l3_safe = (90.0 - 165.0) * np.pi / 180.0  
                        self.cmd_flex1_safe = self.offset_flex1 + delta_l3_safe  
                        
                        approach_1_angles = [
                            self.saved_target_angles_6[0],  
                            self.offset_lift,               
                            self.cmd_flex1_safe,            
                            self.offset_flex2,              
                            self.wrist_roll_val,            
                            self.gripper_open               
                        ]
                        
                        # 안전하게 스레드 단독으로 상태 전환[cite: 1]
                        self.current_state = "APPROACH_1"
                        self.get_logger().info(" [시퀀스 1단계] ➔ APPROACH_1 시작 (허리 조준, L3 90도 부양, 집게 최대 개방)")
                        self.send_trajectory_action_goal(approach_1_angles, travel_time_sec=2.5)
                    break

    def send_trajectory_action_goal(self, angles_6, travel_time_sec):
        goal_msg = FollowJointTrajectory.Goal()
        trajectory = JointTrajectory()
        trajectory.joint_names = self.joint_names

        start_angles = self.real_angles_6 if self.real_angles_6 is not None else self.current_angles_6

        point_start = JointTrajectoryPoint()
        point_start.positions = [float(x) for x in start_angles]
        point_start.time_from_start = Duration(sec=0, nanosec=0)
        trajectory.points.append(point_start)

        point_end = JointTrajectoryPoint()
        point_end.positions = [float(x) for x in angles_6]
        point_end.time_from_start = Duration(sec=int(travel_time_sec), nanosec=int((travel_time_sec % 1) * 1e9))
        trajectory.points.append(point_end)
        
        goal_msg.trajectory = trajectory
        
        # [그리퍼 디버깅 및 실물 피드백 교차 검증 로그]
        self.get_logger().info(f' [통신 지령] 목표 그리퍼 값 보냄 ➔ {angles_6[5]:.3f}')
        if self.real_angles_6 is not None:
            self.get_logger().info(f' [실물 피드백] 현재 실제 그리퍼 각도 인코더 값 ➔ {self.real_angles_6[5]:.3f}')
        
        send_goal_future = self._action_client.send_goal_async(goal_msg)
        send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.current_state = "IDLE"
            return
        get_result_future = goal_handle.get_result_async()
        get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        status = future.result().status
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.transition_next_state()
        else:
            self.get_logger().error(f' [주행 실패] 브레이크 발생. 코드: {status}')
            self.current_state = "IDLE"

    def transition_next_state(self):
        if self.current_state == "APPROACH_1":
            self.current_state = "APPROACH_2"
            self.get_logger().info(" [시퀀스 2단계] ➔ APPROACH_2 시작 (팔꿈치 90도 유지, 어깨만 선제 전진)")
            
            approach_2_angles = [
                self.saved_target_angles_6[0],  
                self.saved_target_angles_6[1],  
                self.cmd_flex1_safe,            
                self.offset_flex2,
                self.wrist_roll_val,
                self.gripper_open
            ]
            self.send_trajectory_action_goal(approach_2_angles, travel_time_sec=3.5)

        elif self.current_state == "APPROACH_2":
            self.current_state = "APPROACH_2_WAIT"
            self.get_logger().info(" [대기] L2 모터가 물리적으로 완전히 멈출 때까지 1.5초간 대기합니다...")
            self.settle_timer = self.create_timer(1.5, self.transition_to_approach_3, callback_group=self.main_cb_group)

        elif self.current_state == "APPROACH_3":
            self.current_state = "GRASP"
            self.get_logger().info(" [시퀀스 4단계] ➔ GRASP 시작 (집게 오므리기 기동)")
            self.saved_target_angles_6[5] = self.gripper_close  
            self.send_trajectory_action_goal(self.saved_target_angles_6, travel_time_sec=1.5)

        elif self.current_state == "GRASP":
            self.current_state = "LIFT_UP"
            self.get_logger().info(" [시퀀스 5단계] ➔ LIFT_UP 시작 (어깨 놔두고 팔꿈치만 다시 90도로 수직 복귀)")
            
            lift_up_target = [
                self.saved_target_angles_6[0],
                self.saved_target_angles_6[1],
                self.cmd_flex1_safe,            
                self.offset_flex2,
                self.wrist_roll_val,
                self.gripper_close              
            ]
            self.send_trajectory_action_goal(lift_up_target, travel_time_sec=2.0)

        elif self.current_state == "LIFT_UP":
            self.current_state = "LIFT_AND_MOVE"
            self.get_logger().info(" [시퀀스 6단계] ➔ LIFT_AND_MOVE 시작 (안전 고공 높이에서 홈으로 안전 이송)")
            home_target = [self.offset_pan, self.offset_lift, self.offset_flex1, self.offset_flex2, self.wrist_roll_val, self.gripper_close]
            self.send_trajectory_action_goal(home_target, travel_time_sec=4.0)

        elif self.current_state == "LIFT_AND_MOVE":
            self.current_state = "RELEASE"
            self.get_logger().info(" 🗑 [ACTION] ➔ RELEASE 시작 (집게 열기 및 폐기물 배출)")
            home_target = [self.offset_pan, self.offset_lift, self.offset_flex1, self.offset_flex2, self.wrist_roll_val, self.gripper_open]
            self.send_trajectory_action_goal(home_target, travel_time_sec=2.0)

        elif self.current_state == "RELEASE":
            self.current_state = "COOL_DOWN"
            self.get_logger().info(" ⏳ [SYSTEM COOL_DOWN] 안전을 위해 3초간 비전 차단...")
            self.cool_down_timer = self.create_timer(3.0, self.reset_to_idle, callback_group=self.main_cb_group)

    def transition_to_approach_3(self):
        self.settle_timer.cancel()
        if self.current_state == "APPROACH_2_WAIT":
            self.current_state = "APPROACH_3"
            self.get_logger().info(" [시퀀스 3단계] ➔ APPROACH_3 시작 (어깨 고정 확인 완료, 팔꿈치만 수직 하강)")
            self.send_trajectory_action_goal(self.saved_target_angles_6, travel_time_sec=2.0)

    def reset_to_idle(self):
        self.cool_down_timer.cancel()
        self.current_state = "IDLE"
        self.get_logger().info(" [ALL PROCESS DONE] ➔ 다음 쓰레기를 정상 대기합니다.\n")

    def convert_pixel_to_robot_space(self, u, v):
        pixel_vector = np.array([u, v, 1.0])
        robot_vector = np.dot(self.H, pixel_vector)
        scale = robot_vector[2]
        return robot_vector[0] / scale, robot_vector[1] / scale

    def calculate_6_axis_positions(self, x, y, z, gripper_val):
        try:
            L1, L2, L3 = 80.0, 117.0, 223.0
            theta1 = np.arctan2(y, x)

            r = np.sqrt(x**2 + y**2)
            s = z - L1
            
            cos_theta3 = (r**2 + s**2 - L2**2 - L3**2) / (2 * L2 * L3)
            if abs(cos_theta3) > 1.0:
                return None
                
            theta3 = np.arctan2(-np.sqrt(1 - cos_theta3**2), cos_theta3)
            theta2 = np.arctan2(s, r) - np.arctan2(L3 * np.sin(theta3), L2 + L3 * np.cos(theta3))
            
            cmd_pan = self.offset_pan - theta1
            cmd_lift = self.offset_lift + (theta2 - self.home_math_lift) * self.scale_lift
            cmd_flex1 = self.offset_flex1 + (theta3 - self.home_math_flex1)
            cmd_flex2 = self.offset_flex2
            
            return [cmd_pan, cmd_lift, cmd_flex1, cmd_flex2, self.wrist_roll_val, gripper_val]
        except Exception as e:
            self.get_logger().error(f"역기하학(IK) 연산 중 예외 에러 발생: {e}")
            return None

def main(args=None):
    rclpy.init(args=args)
    node = RobotControlNode()
    
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()