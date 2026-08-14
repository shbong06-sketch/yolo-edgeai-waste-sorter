import math

import pytest

from evaluation_node.dry_run import joints_for_xy, make_error_cases
from evaluation_node.kinematics import forward_kinematics


def test_error_cases_have_three_of_each_category_and_are_shuffled():
    cases = make_error_cases(7.0, 10.0, seed=101)
    assert len(cases) == 9
    assert [label for label, _ in cases].count('pass') == 3
    assert [label for label, _ in cases].count('warning') == 3
    assert [label for label, _ in cases].count('fail') == 3
    assert [label for label, _ in cases] != ['pass'] * 3 + ['warning'] * 3 + ['fail'] * 3
    for label, error in cases:
        if label == 'pass':
            assert error <= 7.0
        elif label == 'warning':
            assert 7.0 < error <= 10.0
        else:
            assert error > 10.0


@pytest.mark.parametrize('xy', [(122.0, 84.5), (134.5, 84.5), (115.0, 70.0)])
def test_inverse_values_reproduce_requested_fk_xy(xy):
    actual = forward_kinematics(joints_for_xy(*xy, gripper=2.7))
    assert math.isclose(actual[0], xy[0], abs_tol=1e-6)
    assert math.isclose(actual[1], xy[1], abs_tol=1e-6)
