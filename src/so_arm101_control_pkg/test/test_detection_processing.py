from so_arm101_control_pkg.move_joints_action_client import (
    is_valid_detection,
    METERS_PER_PIXEL_X,
    METERS_PER_PIXEL_Y,
    pixel_to_robot_offset,
)
from vision_msgs.msg import Detection2D, ObjectHypothesisWithPose


def make_detection(score=0.9, width=80.0, height=80.0):
    detection = Detection2D()
    detection.bbox.size_x = width
    detection.bbox.size_y = height

    result = ObjectHypothesisWithPose()
    result.hypothesis.score = score
    detection.results.append(result)
    return detection


def test_valid_detection():
    assert is_valid_detection(make_detection())


def test_detection_requires_result():
    assert not is_valid_detection(Detection2D())


def test_detection_requires_confidence():
    assert not is_valid_detection(make_detection(score=0.84))


def test_detection_requires_positive_bbox():
    assert not is_valid_detection(make_detection(width=0.0))
    assert not is_valid_detection(make_detection(height=-1.0))


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
