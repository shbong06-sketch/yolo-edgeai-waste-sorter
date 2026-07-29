from so_arm101_control_pkg.move_joints_action_client import (
    METERS_PER_PIXEL_X,
    METERS_PER_PIXEL_Y,
    pixel_to_robot_offset,
)


def test_image_center_maps_to_zero_offset():
    assert pixel_to_robot_offset(320.0, 240.0) == (0.0, 0.0)


def test_image_axes_map_to_negative_robot_axes():
    robot_x, robot_y = pixel_to_robot_offset(321.0, 241.0)
    assert robot_x == -METERS_PER_PIXEL_X
    assert robot_y == -METERS_PER_PIXEL_Y


def test_image_corners_map_to_table_extents():
    top_left = pixel_to_robot_offset(0.0, 0.0)
    bottom_right = pixel_to_robot_offset(640.0, 480.0)

    assert top_left == (0.8085078 / 2.0, 1.1356210 / 2.0)
    assert bottom_right == (-0.8085078 / 2.0, -1.1356210 / 2.0)
