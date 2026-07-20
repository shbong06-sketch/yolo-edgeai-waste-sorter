from setuptools import find_packages, setup

package_name = 'robot_control_node'
from setuptools import setup

package_name = 'robot_control_node'

setup(
    name=package_name,
    version='0.0.0',
    # find_packages() 대신 폴더명을 명확하게 수동 지정하여 인식 오류를 원천 차단합니다.
    packages=[package_name], 
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Seonghyun Park',
    maintainer_email='seonghyun@todo.todo',
    description='YOLO 탐지 결과를 받아 호모그래피 변환 및 IK를 수행하는 독립 제어 노드',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'robot_control_node = robot_control_node.robot_control_node:main',
        ],
    },
)