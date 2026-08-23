import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from reachy_mini.vision.face_detector import Face
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.tools.detect_face import DetectFace
from reachy_mini_conversation_app.vision.face_detector_3d import (
    NOMINAL_IPD_METERS,
    NOMINAL_FACE_WIDTH_METERS,
    Face3DDetector,
    Face3DCoordinates,
)


def test_face_3d_coordinates_attributes() -> None:
    """Test attributes and getters of Face3DCoordinates dataclass."""
    coords = Face3DCoordinates(
        x=1.0,
        y=0.2,
        z=-0.1,
        distance=1.025,
        azimuth_rad=0.1974,
        elevation_rad=-0.0977,
        azimuth_deg=11.31,
        elevation_deg=-5.6,
        bbox=(100.0, 100.0, 80.0, 80.0),
        landmarks={"nose": (140.0, 140.0)},
    )
    assert coords.x == 1.0
    assert coords.y == 0.2
    assert coords.distance == 1.025
    assert coords.azimuth_deg == 11.31


def test_face_3d_detector_empty_frame() -> None:
    """Test face detection on empty and zero-sized frame inputs."""
    detector = Face3DDetector()
    assert detector.detect(np.array([])) == []
    assert detector.detect(np.zeros((0, 0, 3), dtype=np.uint8)) == []


def test_face_3d_detector_estimation_center_face() -> None:
    """Test 3D coordinate estimation for a centered face."""
    detector = Face3DDetector(horizontal_fov_rad=math.radians(60.0))
    width, height = 640, 480
    fx, _, cx, cy = detector._get_camera_intrinsics(width, height)

    target_depth = 1.0
    eye_dist_px = (fx * NOMINAL_IPD_METERS) / target_depth
    face_width_px = (fx * NOMINAL_FACE_WIDTH_METERS) / target_depth

    face = Face(
        bbox=(cx - face_width_px / 2, cy - face_width_px / 2, face_width_px, face_width_px),
        right_eye=(cx - eye_dist_px / 2, cy),
        left_eye=(cx + eye_dist_px / 2, cy),
        nose=(cx, cy),
    )

    coords = detector._estimate_3d_coordinates(face, width, height)
    assert coords is not None
    assert math.isclose(coords.x, target_depth, rel_tol=0.05)
    assert math.isclose(coords.y, 0.0, abs_tol=0.02)
    assert math.isclose(coords.z, 0.0, abs_tol=0.02)
    assert math.isclose(coords.azimuth_deg, 0.0, abs_tol=1.0)
    assert math.isclose(coords.elevation_deg, 0.0, abs_tol=1.0)


def test_face_3d_detector_estimation_offset_face() -> None:
    """Test 3D coordinate and angle estimation for off-center faces."""
    detector = Face3DDetector(horizontal_fov_rad=math.radians(60.0))
    width, height = 640, 480
    _, _, cx, cy = detector._get_camera_intrinsics(width, height)

    face_left = Face(
        bbox=(50.0, 100.0, 80.0, 80.0),
        right_eye=(70.0, 130.0),
        left_eye=(110.0, 130.0),
        nose=(90.0, 150.0),
    )

    coords_left = detector._estimate_3d_coordinates(face_left, width, height)
    assert coords_left is not None
    assert coords_left.y > 0
    assert coords_left.azimuth_deg > 0

    face_right = Face(
        bbox=(500.0, 100.0, 80.0, 80.0),
        right_eye=(520.0, 130.0),
        left_eye=(560.0, 130.0),
        nose=(540.0, 150.0),
    )

    coords_right = detector._estimate_3d_coordinates(face_right, width, height)
    assert coords_right is not None
    assert coords_right.y < 0
    assert coords_right.azimuth_deg < 0


@pytest.mark.asyncio
async def test_detect_face_tool_camera_disabled() -> None:
    """Test DetectFace tool response when camera is disabled."""
    tool = DetectFace()
    mock_robot = MagicMock()
    mock_movement = MagicMock()
    deps = ToolDependencies(reachy_mini=mock_robot, movement_manager=mock_movement, camera_enabled=False)

    result = await tool(deps)
    assert result["detected"] is False
    assert result["error"] == "Camera is disabled"


@pytest.mark.asyncio
async def test_detect_face_tool_no_frame() -> None:
    """Test DetectFace tool response when no frame is available."""
    tool = DetectFace()
    mock_robot = MagicMock()
    mock_robot.media.get_frame.return_value = None
    mock_movement = MagicMock()
    deps = ToolDependencies(reachy_mini=mock_robot, movement_manager=mock_movement, camera_enabled=True)

    result = await tool(deps)
    assert result["detected"] is False
    assert result["error"] == "No frame available from camera"


@pytest.mark.asyncio
async def test_detect_face_tool_success() -> None:
    """Test successful face detection and look-at move execution."""
    tool = DetectFace()
    mock_robot = MagicMock()
    mock_robot.get_current_head_pose.return_value = np.eye(4)
    mock_robot.get_current_joint_positions.return_value = ([0.0], [0.0, 0.0])
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_robot.media.get_frame.return_value = frame
    mock_movement = MagicMock()

    deps = ToolDependencies(
        reachy_mini=mock_robot,
        movement_manager=mock_movement,
        camera_enabled=True,
        motion_duration_s=1.0,
    )

    with patch.object(Face3DDetector, "detect") as mock_detect:
        mock_detect.return_value = [
            Face3DCoordinates(
                x=0.8,
                y=0.0,
                z=0.0,
                distance=0.8,
                azimuth_rad=0.0,
                elevation_rad=0.0,
                azimuth_deg=0.0,
                elevation_deg=0.0,
                bbox=(270.0, 190.0, 100.0, 100.0),
                landmarks={"nose": (320.0, 250.0)},
            )
        ]

        result = await tool(deps, look_at_face=True)
        assert result["detected"] is True
        assert result["face_count"] == 1
        assert result["primary_face"]["distance_meters"] == 0.8
        mock_movement.queue_move.assert_called_once()
        mock_movement.set_moving_state.assert_called_once_with(1.0)
