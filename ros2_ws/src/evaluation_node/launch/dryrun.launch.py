"""평가 결과를 현재 오버레이 워크스페이스의 tmp에 저장한다."""

from pathlib import Path

from ament_index_python.packages import get_package_prefix
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_prefix = Path(get_package_prefix('evaluation_node'))
    # <workspace>/install/evaluation_node에서 <workspace>를 구한다.
    workspace_root = package_prefix.parents[1]
    default_output = str(workspace_root / 'tmp')

    return LaunchDescription([
        DeclareLaunchArgument(
            'output_directory',
            default_value=default_output,
            description='평가 결과를 저장할 상위 디렉터리',
        ),
        DeclareLaunchArgument(
            'config_path',
            default_value='',
            description='비워 두면 설치된 evaluation.yaml을 사용',
        ),
        Node(
            package='evaluation_node',
            executable='evaluation_node',
            name='evaluation_node',
            output='screen',
            parameters=[{
                'config_path': LaunchConfiguration('config_path'),
                'output_directory': LaunchConfiguration('output_directory'),
            }],
        ),

        Node(
            package='evaluation_node',
            executable='dry_run',
            name='evaluation_dry_run_node',
            output='screen',
            parameters=[{
                'config_path': LaunchConfiguration('config_path'),
            }],
        ),
    ])
