import pytest

from evaluation_node.kinematics import JOINT_NAMES, forward_kinematics, ordered_positions


def test_joint_state_is_name_mapped():
    names = list(reversed(JOINT_NAMES))
    values = list(reversed(range(6)))
    assert ordered_positions(names, values) == list(range(6))


def test_fk_requires_six_finite_values():
    with pytest.raises(ValueError):
        forward_kinematics([1, 2])
