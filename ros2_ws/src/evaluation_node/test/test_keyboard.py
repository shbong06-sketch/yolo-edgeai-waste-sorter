import queue

from evaluation_node.keyboard_control import KeyboardController


class Pipe:
    def isatty(self):
        return False


def test_uppercase_and_unknown_keys():
    commands = queue.Queue()
    keyboard = KeyboardController(commands, stream=Pipe())
    assert keyboard.feed_key('S')
    assert keyboard.feed_key('E')
    assert keyboard.feed_key('Q')
    assert not keyboard.feed_key('x')
    assert [commands.get().key for _ in range(3)] == ['s', 'e', 'q']


def test_non_tty_is_disabled_and_restore_is_idempotent(capsys):
    keyboard = KeyboardController(stream=Pipe())
    assert keyboard.start() is False
    assert '포그라운드 ros2 run' in capsys.readouterr().err
    keyboard.restore(); keyboard.restore(); keyboard.stop()
