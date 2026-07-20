from setuptools import find_packages, setup

package_name = 'detector_node_pkg'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=[
        'setuptools',
        'ultralytics==8.4.87',
        'opencv-python>=4.8',
        'numpy',
        'torch',
    ],
    zip_safe=True,
    maintainer='shbong',
    maintainer_email='shbong@todo.todo',
    description='YOLO based waste detection ROS2 package',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'detector_node = detector_node_pkg.detector_node:main',
        ],
    },
)
