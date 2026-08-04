from pathlib import Path

from evaluation_node.config_loader import load_config, resolve_config_path


def test_explicit_config_path_does_not_need_ros_arguments(tmp_path):
    config = tmp_path / 'evaluation.yaml'
    config.write_text('control_mode: keyboard\n', encoding='utf-8')
    value, path = load_config(config)
    assert path == config
    assert value['control_mode'] == 'keyboard'


def test_environment_config_is_used_without_parameter(tmp_path, monkeypatch):
    config = tmp_path / 'evaluation.yaml'
    config.write_text('start_key: s\n', encoding='utf-8')
    monkeypatch.setenv('EVALUATION_CONFIG', str(config))
    assert resolve_config_path() == Path(config)
