"""평가 서비스를 키보드로 호출하는 독립 ROS 2 노드."""

import queue

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

from .config_loader import load_config
from .keyboard_control import KeyboardController


class KeyboardControlNode(Node):
    """키 입력을 평가 노드의 서비스 요청으로만 변환한다."""

    def __init__(self):
        super().__init__('evaluation_keyboard_node')
        # 평가 노드와 같은 탐색 규칙을 사용하므로 별도 ROS 인자가 필요 없다.
        self.declare_parameter('config_path', '')
        config, config_path = load_config(self.get_parameter('config_path').value)

        self.commands = queue.Queue()
        self.keys = {
            config['start_key'].lower(): 'start_next_trial',
            config['end_key'].lower(): 'end_trial',
            config['quit_key'].lower(): 'stop_run',
        }
        self.clients = {
            name: self.create_client(Trigger, f'/evaluation/{name}')
            for name in ('start_next_trial', 'end_trial', 'stop_run', 'analyze')
        }
        self.pending = None
        self.quitting = False
        self.keyboard = KeyboardController(
            self.commands,
            keys=(config['start_key'], config['end_key'], config['quit_key']))
        self.keyboard.start()
        # Ctrl+C도 q 명령과 같은 서비스 순서를 거치게 한다.
        self.keyboard.install_signal_handler(
            lambda: self.keyboard.feed_key(config['quit_key']))
        self.create_timer(.05, self._process_commands)
        self.get_logger().info(
            f"평가 키: {config['start_key']}=시작, "
            f"{config['end_key']}=저장, {config['quit_key']}=중단·분석·종료")
        self.get_logger().info(f'평가 설정: {config_path}')

    def _process_commands(self):
        # 이전 요청 응답을 기다리는 동안 중복 서비스 호출을 만들지 않는다.
        if self.pending is not None:
            return
        try:
            command = self.commands.get_nowait()
        except queue.Empty:
            return
        service = self.keys.get(command.key)
        if service == 'stop_run':
            self.quitting = True
        self._request(service)

    def _request(self, service):
        client = self.clients[service]
        if not client.service_is_ready():
            self.get_logger().warning(
                f'/evaluation/{service} 서비스를 사용할 수 없습니다.')
            if self.quitting:
                self.keyboard.restore()
                rclpy.shutdown()
            return
        self.pending = client.call_async(Trigger.Request())
        self.pending.add_done_callback(
            lambda future, name=service: self._response(name, future))

    def _response(self, service, future):
        self.pending = None
        try:
            response = future.result()
            log = self.get_logger().info if response.success else self.get_logger().warning
            log(f'[{service}] {response.message}')
        except Exception as error:  # 서비스 장애가 나도 터미널은 반드시 복구한다.
            self.get_logger().error(f'[{service}] 요청 실패: {error}')
            if self.quitting:
                self.keyboard.restore()
            return

        # q는 먼저 활성 회차를 폐기하고, 그 다음 분석 생성을 요청한다.
        if service == 'stop_run' and self.quitting:
            self._request('analyze')
        elif service == 'analyze' and self.quitting:
            self.keyboard.restore()
            rclpy.shutdown()

    def destroy_node(self):
        self.keyboard.restore()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = KeyboardControlNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        # signal handler가 정상 설치되지 않은 환경에서도 터미널을 복구한다.
        node.keyboard.restore()
    finally:
        node.keyboard.restore()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
