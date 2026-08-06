from setuptools import find_packages, setup

package_name = 'so_arm101_control_pkg'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='rokey',
    maintainer_email='hansaekyo@gmail.com',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'move_joints_action_client = '
            'so_arm101_control_pkg.move_joints_action_client:main',
            'move_joints_action_server = '
            'so_arm101_control_pkg.move_joints_action_server:main',
            'mock_detector = so_arm101_control_pkg.detector:main',
        ],
    },
)
