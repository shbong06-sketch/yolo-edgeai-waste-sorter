from setuptools import find_packages, setup

package_name = 'evaluation_node'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name, ['README.md']),
        ('share/' + package_name + '/config', ['config/evaluation.yaml']),
        ('share/' + package_name + '/docs', ['docs/branch_compatibility.md']),
    ],
    install_requires=['setuptools', 'PyYAML'],
    extras_require={'test': ['pytest']},
    zip_safe=True,
    maintainer='shbong',
    maintainer_email='shbong06@gmail.com',
    description='SO-ARM 101 관찰 전용 평가 노드',
    license='Apache-2.0',
    entry_points={'console_scripts': [
        'evaluation_node = evaluation_node.evaluation_node:main',
        'keyboard_node = evaluation_node.keyboard_node:main',
    ]},
)
