"""사용자가 긴 ROS 인자를 입력하지 않아도 설정을 찾는 공통 로더."""

from importlib.util import find_spec
import os
from pathlib import Path

import yaml


def _source_config_paths():
    module_path = Path(__file__).resolve()
    return (
        module_path.parents[1] / 'config' / 'evaluation.yaml',
        module_path.parents[4] / 'share' / 'evaluation_node' / 'config' / 'evaluation.yaml',
    )


def _ament_config_path():
    if (find_spec('ament_index_python') is None or
            find_spec('ament_index_python.packages') is None):
        return None
    from ament_index_python.packages import (
        PackageNotFoundError, get_package_share_directory)
    try:
        share_dir = get_package_share_directory('evaluation_node')
    except PackageNotFoundError:
        return None
    return Path(share_dir) / 'config' / 'evaluation.yaml'


def resolve_config_path(explicit_path=''):
    """명시 경로, 환경 변수, 사용자 설정, 기본 설정 순으로 찾는다."""
    for value in (explicit_path, os.environ.get('EVALUATION_CONFIG', '')):
        if str(value).strip():
            return Path(value).expanduser()

    user_path = Path.home() / '.config' / 'evaluation_node' / 'evaluation.yaml'
    if user_path.is_file():
        return user_path

    for candidate in (*_source_config_paths(), _ament_config_path()):
        if candidate is not None and candidate.is_file():
            return candidate
    return _source_config_paths()[-1]


def load_config(explicit_path=''):
    """찾은 YAML 설정과 실제 사용 경로를 함께 반환한다."""
    path = resolve_config_path(explicit_path)
    if not path.is_file():
        raise FileNotFoundError(f'평가 설정 파일을 찾을 수 없습니다: {path}')
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict):
        raise ValueError(f'평가 설정 YAML은 mapping/object 형식이어야 합니다: {path}')
    return config, path
