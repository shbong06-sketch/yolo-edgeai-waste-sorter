"""평가 실행 중 포그라운드 터미널 키 입력을 처리한다."""

from dataclasses import dataclass
import queue
import select
import signal
import sys
import termios
import threading
import tty


NON_TTY_MESSAGE = '키보드 평가에는 포그라운드 ros2 run이 필요합니다.'


@dataclass(frozen=True)
class KeyboardCommand:
    """ROS 상태를 직접 바꾸지 않는 키 입력 명령."""

    key: str
    source: str = 'keyboard'


class KeyboardController:
    """데몬 스레드에서 한 글자 명령을 읽고 TTY를 복구한다."""

    def __init__(self, command_queue=None, stream=None, keys=('s', 'e', 'q'),
                 select_fn=select.select):
        self.queue = command_queue or queue.Queue()
        self.stream = stream or sys.stdin
        self.keys = tuple(str(key).lower() for key in keys)
        self._select = select_fn
        self._settings = None
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.available = bool(getattr(self.stream, 'isatty', lambda: False)())

    def start(self):
        """TTY를 cbreak 모드로 바꾸고 읽기를 시작한다. 파이프 입력에서는 비활성화한다."""
        if not self.available:
            print(NON_TTY_MESSAGE, file=sys.stderr)
            return False
        with self._lock:
            if self._thread and self._thread.is_alive():
                return True
            fd = self.stream.fileno()
            self._settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._read_loop, name='evaluation-keyboard', daemon=True)
            self._thread.start()
        return True

    def _read_loop(self):
        try:
            while not self._stop.is_set():
                readable, _, _ = self._select([self.stream], [], [], 0.1)
                if not readable:
                    continue
                value = self.stream.read(1)
                if not value:
                    break
                self.feed_key(value)
        finally:
            self.restore()

    def feed_key(self, value):
        """테스트/터미널 문자를 정규화하고 등록된 키만 큐에 넣는다."""
        key = str(value).lower()
        if key in self.keys:
            self.queue.put(KeyboardCommand(key=key))
            return True
        return False

    def stop(self):
        self._stop.set()
        self.restore()

    def restore(self):
        """터미널 속성을 여러 번 호출해도 안전하게 복구한다."""
        with self._lock:
            settings, self._settings = self._settings, None
            if settings is not None:
                termios.tcsetattr(self.stream.fileno(), termios.TCSADRAIN,
                                  settings)

    def install_signal_handler(self, callback):
        """SIGINT 처리를 노드에 넘기기 전에 터미널을 복구한다."""
        def handler(signum, frame):
            del signum, frame
            self.restore()
            callback()
        signal.signal(signal.SIGINT, handler)
