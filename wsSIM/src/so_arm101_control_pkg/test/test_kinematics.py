from pathlib import Path

import numpy as np

from so_arm101_control_pkg.kinematics import RobotKinematics


URDF_PATH = (
    Path(__file__).parents[2]
    / 'so_arm101_description'
    / 'urdf'
    / 'so_arm101.urdf'
)


def make_kinematics():
    return RobotKinematics(
        URDF_PATH,
        'base_link',
        'gripper_frame_link',
    )


def test_arm_chain_matches_isaac_joint_names():
    kinematics = make_kinematics()
    assert kinematics.joint_names == [
        'shoulder_pan',
        'shoulder_lift',
        'elbow_flex',
        'wrist_flex',
        'wrist_roll',
    ]


def test_inverse_position_returns_current_pose():
    kinematics = make_kinematics()
    seed = np.zeros(5)
    target = kinematics.forward(seed)[:3, 3]
    solution = kinematics.inverse_position(target, seed)
    assert np.allclose(solution, seed, atol=1e-6)


def test_inverse_position_reaches_small_xy_offset():
    kinematics = make_kinematics()
    seed = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
    target = kinematics.forward(seed)[:3, 3]
    target += np.array([0.02, 0.01, 0.0])

    solution = kinematics.inverse_position(target, seed)
    reached = kinematics.forward(solution)[:3, 3]
    assert np.linalg.norm(reached - target) <= 0.005
