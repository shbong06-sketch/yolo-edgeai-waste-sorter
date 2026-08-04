"""SO-ARM 실제 관절각을 평가용 손끝 좌표로 변환하는 순기구학 모듈."""

import math


JOINT_NAMES = ('shoulder_pan', 'shoulder_lift', 'elbow_flex',
               'wrist_flex', 'wrist_roll', 'gripper')
OFFSETS = (3.1738062501353914, 1.3330293046726223,
           4.535981189777841, 4.512971477959557)
HOME_LIFT = -0.1745
HOME_ELBOW = -3.0543
LIFT_SCALE = 2.0
LINKS_MM = (80.0, 117.0, 223.0)


def ordered_positions(names, positions):
    """JointState 배열을 로봇 제어기의 6축 이름 순서로 안전하게 정렬한다."""
    lookup = dict(zip(names, positions))
    values = [float(lookup[name]) for name in JOINT_NAMES]
    if len(lookup) != len(names) or not all(math.isfinite(v) for v in values):
        raise ValueError('joint state has duplicate or non-finite values')
    return values


def forward_kinematics(joints):
    """측정한 6축 관절각으로 그리퍼 끝의 XYZ 좌표(mm)를 계산한다."""
    if len(joints) != 6 or not all(math.isfinite(float(v)) for v in joints):
        raise ValueError('six finite joint values are required')
    pan = OFFSETS[0] - float(joints[0])
    shoulder = HOME_LIFT + (float(joints[1]) - OFFSETS[1]) / LIFT_SCALE
    elbow = HOME_ELBOW + float(joints[2]) - OFFSETS[2]
    l1, l2, l3 = LINKS_MM
    radius = l2 * math.cos(shoulder) + l3 * math.cos(shoulder + elbow)
    vertical = l2 * math.sin(shoulder) + l3 * math.sin(shoulder + elbow)
    return (radius * math.cos(pan), radius * math.sin(pan), l1 + vertical)
