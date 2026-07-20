from setuptools import find_packages, setup

package_name = 'camera_node_pkg'

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
        'opencv-python>=4.8',
        'numpy',
    ],
    zip_safe=True,
    maintainer='shbong',
    maintainer_email='shbong@todo.todo',
    description='Camera node for waste detection system',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'camera_node = camera_node_pkg.camera_node:main',
        ],
    },
)
