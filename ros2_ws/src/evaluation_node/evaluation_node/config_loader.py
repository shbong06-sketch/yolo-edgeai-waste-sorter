"""사용자가 긴 ROS 인자를 입력하지 않아도 설정을 찾는 공통 로더."""

import os
from pathlib import Path

import yaml


def resolve_config_path(explicit_path=''):
    """명시 경로, 환경 변수, 사용자 설정, 패키지 기본값 순으로 찾는다."""
    if str(explicit_path).strip():
        return Path(explicit_path).expanduser()

    environment_path = os.environ.get('EVALUATION_CONFIG', '').strip()
    if environment_path:
        return Path(environment_path).expanduser()

    user_path = Path.home() / '.config' / 'evaluation_node' / 'evaluation.yaml'
    if user_path.is_file():
        return user_path

    # 마지막 단계에서 ROS 패키지 인덱스를 사용한다. 최소 테스트 환경에서는
    # 소스/설치 prefix도 확인하여 인자 없는 실행 경로를 검증할 수 있게 한다.
    try:
        from ament_index_python.packages import get_package_share_directory
        return Path(get_package_share_directory('evaluation_node')) / 'config' / 'evaluation.yaml'
    except ImportError:
        module_path = Path(__file__).resolve()
        candidates = (
            module_path.parents[1] / 'config' / 'evaluation.yaml',
            module_path.parents[4] / 'share' / 'evaluation_node' / 'config' / 'evaluation.yaml',
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return candidates[-1]


def load_config(explicit_path=''):
    """찾은 YAML 설정과 실제 사용 경로를 함께 반환한다."""
    path = resolve_config_path(explicit_path)
    if not path.is_file():
        raise FileNotFoundError(f'평가 설정 파일을 찾을 수 없습니다: {path}')
    return yaml.safe_load(path.read_text(encoding='utf-8')), path
