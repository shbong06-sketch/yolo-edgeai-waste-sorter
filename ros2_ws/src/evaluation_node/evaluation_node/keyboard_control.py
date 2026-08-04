"""Non-blocking foreground-terminal controls for an evaluation run."""

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
    """A command produced by an input source, without mutating ROS state."""

    key: str
    source: str = 'keyboard'


class KeyboardController:
    """Read one-character commands on a daemon thread and restore the TTY."""

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
        """Put a TTY in cbreak mode and start reading; do nothing for pipes."""
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
        """Normalize a test or terminal character and enqueue known keys."""
        key = str(value).lower()
        if key in self.keys:
            self.queue.put(KeyboardCommand(key=key))
            return True
        return False

    def stop(self):
        self._stop.set()
        self.restore()

    def restore(self):
        """Idempotently restore terminal attributes."""
        with self._lock:
            settings, self._settings = self._settings, None
            if settings is not None:
                termios.tcsetattr(self.stream.fileno(), termios.TCSADRAIN,
                                  settings)

    def install_signal_handler(self, callback):
        """Restore the terminal before delegating SIGINT to the node."""
        def handler(signum, frame):
            del signum, frame
            self.restore()
            callback()
        signal.signal(signal.SIGINT, handler)
