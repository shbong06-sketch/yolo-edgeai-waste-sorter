"""SO-ARM101 URDF를 사용하는 순기구학 및 위치 역기구학."""

from dataclasses import dataclass
from math import pi
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation


@dataclass
class JointDescription:
    """URDF 관절 하나의 기구학 정보."""

    name: str
    joint_type: str
    parent: str
    child: str
    origin_xyz: np.ndarray
    origin_rpy: np.ndarray
    axis: np.ndarray
    lower: float
    upper: float


def parse_vector(text, default):
    """공백으로 구분된 URDF 벡터 문자열을 numpy 배열로 변환한다."""
    if text is None:
        return np.array(default, dtype=float)
    return np.array([float(value) for value in text.split()], dtype=float)


def make_transform(translation, rotation):
    """이동 벡터와 회전 행렬로 4×4 변환 행렬을 생성한다."""
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = translation
    return transform


class RobotKinematics:
    """URDF 체인에서 FK를 계산하고 수치적으로 위치 IK를 푼다."""

    def __init__(self, urdf_path, base_link, tip_link):
        self.urdf_path = Path(urdf_path)
        self.base_link = base_link
        self.tip_link = tip_link
        self.chain = self._load_chain()
        self.movable_joints = [
            joint
            for joint in self.chain
            if joint.joint_type != 'fixed'
        ]
        self.joint_names = [
            joint.name
            for joint in self.movable_joints
        ]
        self.lower_limits = np.array(
            [joint.lower for joint in self.movable_joints]
        )
        self.upper_limits = np.array(
            [joint.upper for joint in self.movable_joints]
        )

    def _load_chain(self):
        """URDF에서 base_link부터 tip_link까지의 관절 체인을 읽는다."""
        root = ET.parse(self.urdf_path).getroot()
        joints_by_child = {}

        for element in root.findall('joint'):
            origin = element.find('origin')
            axis = element.find('axis')
            limit = element.find('limit')
            joint_type = element.get('type')

            description = JointDescription(
                name=element.get('name'),
                joint_type=joint_type,
                parent=element.find('parent').get('link'),
                child=element.find('child').get('link'),
                origin_xyz=parse_vector(
                    origin.get('xyz') if origin is not None else None,
                    [0.0, 0.0, 0.0],
                ),
                origin_rpy=parse_vector(
                    origin.get('rpy') if origin is not None else None,
                    [0.0, 0.0, 0.0],
                ),
                axis=parse_vector(
                    axis.get('xyz') if axis is not None else None,
                    [0.0, 0.0, 1.0],
                ),
                lower=(
                    float(limit.get('lower'))
                    if limit is not None and limit.get('lower') is not None
                    else -pi
                ),
                upper=(
                    float(limit.get('upper'))
                    if limit is not None and limit.get('upper') is not None
                    else pi
                ),
            )
            joints_by_child[description.child] = description

        chain = []
        current_link = self.tip_link

        while current_link != self.base_link:
            if current_link not in joints_by_child:
                raise ValueError(
                    f'No URDF chain from {self.base_link} '
                    f'to {self.tip_link}.'
                )
            joint = joints_by_child[current_link]
            chain.append(joint)
            current_link = joint.parent

        chain.reverse()
        return chain

    def forward(self, joint_positions):
        """주어진 팔 관절값의 end-effector 4×4 Pose를 계산한다."""
        positions = dict(zip(self.joint_names, joint_positions))
        transform = np.eye(4)

        for joint in self.chain:
            origin_rotation = Rotation.from_euler(
                'xyz',
                joint.origin_rpy,
            ).as_matrix()
            transform = transform @ make_transform(
                joint.origin_xyz,
                origin_rotation,
            )

            if joint.joint_type != 'fixed':
                axis = joint.axis / np.linalg.norm(joint.axis)
                joint_rotation = Rotation.from_rotvec(
                    axis * positions[joint.name]
                ).as_matrix()
                transform = transform @ make_transform(
                    np.zeros(3),
                    joint_rotation,
                )

        return transform

    def inverse_position(self, target_position, seed):
        """현재 관절값을 초기값으로 사용해 목표 XYZ의 관절값을 계산한다."""
        target = np.asarray(target_position, dtype=float)
        initial = np.asarray(seed, dtype=float)

        if initial.shape != (len(self.joint_names),):
            raise ValueError('IK seed size does not match the arm chain.')

        # 위치 오차를 우선 줄이되 현재 자세에서 크게 벗어나는 해를 억제한다.
        def residual(positions):
            current_position = self.forward(positions)[:3, 3]
            position_error = current_position - target
            regularization = 0.005 * (positions - initial)
            return np.concatenate((position_error, regularization))

        solution = least_squares(
            residual,
            initial,
            bounds=(self.lower_limits, self.upper_limits),
            max_nfev=300,
        )
        position_error = np.linalg.norm(
            self.forward(solution.x)[:3, 3] - target
        )

        if not solution.success or position_error > 0.005:
            raise ValueError(
                f'IK did not converge: position error={position_error:.4f}m'
            )

        return solution.x
