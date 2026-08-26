"""Unit tests for YOLOv8 object detector and DetectObjects tool."""

from unittest.mock import MagicMock

import numpy as np
import pytest

from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.tools.detect_objects import DetectObjects
from reachy_mini_conversation_app.vision.yolo_detector import (
    COCO_KO_TRANSLATIONS,
    YOLODetector,
    DetectedObject,
)


def test_yolo_detector_empty_frame() -> None:
    """Empty or None frames must return empty detections without crashing."""
    detector = YOLODetector()
    empty_frame = np.zeros((0, 0, 3), dtype=np.uint8)
    assert detector.detect(empty_frame) == []


def test_yolo_translations_has_essential_classes() -> None:
    """Verify common desk companion items have Korean translations."""
    assert COCO_KO_TRANSLATIONS["person"] == "사람"
    assert COCO_KO_TRANSLATIONS["cell phone"] == "스마트폰"
    assert COCO_KO_TRANSLATIONS["cup"] == "컵"
    assert COCO_KO_TRANSLATIONS["laptop"] == "노트북"
    assert COCO_KO_TRANSLATIONS["mouse"] == "마우스"
    assert COCO_KO_TRANSLATIONS["keyboard"] == "키보드"
    assert COCO_KO_TRANSLATIONS["book"] == "책"


@pytest.mark.asyncio
async def test_detect_objects_tool_camera_disabled() -> None:
    """Tool must fail gracefully when camera is disabled."""
    tool = DetectObjects()
    mock_robot = MagicMock()
    mock_movement = MagicMock()
    deps = ToolDependencies(reachy_mini=mock_robot, movement_manager=mock_movement, camera_enabled=False)

    result = await tool(deps)
    assert result["detected"] is False
    assert result["error"] == "Camera is disabled"


@pytest.mark.asyncio
async def test_detect_objects_tool_no_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tool must fail gracefully when no frame is available."""
    tool = DetectObjects()
    mock_robot = MagicMock()
    mock_robot.media.get_frame.return_value = None
    mock_movement = MagicMock()
    deps = ToolDependencies(reachy_mini=mock_robot, movement_manager=mock_movement, camera_enabled=True)

    monkeypatch.setattr("reachy_mini_conversation_app.camera_service.CameraService.get_frame_bgr", lambda self: None)

    result = await tool(deps)
    assert result["detected"] is False
    assert result["error"] == "No frame available from camera"


@pytest.mark.asyncio
async def test_detect_objects_tool_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tool must parse detections, format Korean summary, and return object data."""
    tool = DetectObjects()
    mock_robot = MagicMock()
    mock_movement = MagicMock()
    deps = ToolDependencies(reachy_mini=mock_robot, movement_manager=mock_movement, camera_enabled=True)

    fake_detections = [
        DetectedObject(
            label="laptop",
            label_ko="노트북",
            confidence=0.92,
            bbox=(100.0, 100.0, 400.0, 350.0),
            center_xy=(250.0, 225.0),
        ),
        DetectedObject(
            label="cup",
            label_ko="컵",
            confidence=0.88,
            bbox=(420.0, 200.0, 500.0, 300.0),
            center_xy=(460.0, 250.0),
        ),
    ]

    monkeypatch.setattr(tool._detector, "detect", lambda frame, conf_threshold=0.3: fake_detections)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    monkeypatch.setattr("reachy_mini_conversation_app.camera_service.CameraService.get_frame_bgr", lambda self: frame)

    result = await tool(deps, target_object="all")
    assert result["detected"] is True
    assert result["count"] == 2
    assert "노트북 1개" in result["summary"]
    assert "컵 1개" in result["summary"]
    assert len(result["objects"]) == 2


@pytest.mark.asyncio
async def test_detect_objects_tool_target_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tool must filter for requested target object."""
    tool = DetectObjects()
    mock_robot = MagicMock()
    mock_movement = MagicMock()
    deps = ToolDependencies(reachy_mini=mock_robot, movement_manager=mock_movement, camera_enabled=True)

    fake_detections = [
        DetectedObject(
            label="cell phone",
            label_ko="스마트폰",
            confidence=0.95,
            bbox=(50.0, 50.0, 150.0, 250.0),
            center_xy=(100.0, 150.0),
        ),
        DetectedObject(
            label="cup",
            label_ko="컵",
            confidence=0.85,
            bbox=(400.0, 200.0, 480.0, 280.0),
            center_xy=(440.0, 240.0),
        ),
    ]

    monkeypatch.setattr(tool._detector, "detect", lambda frame, conf_threshold=0.3: fake_detections)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    monkeypatch.setattr("reachy_mini_conversation_app.camera_service.CameraService.get_frame_bgr", lambda self: frame)

    # Search for phone in Korean
    result_ko = await tool(deps, target_object="스마트폰")
    assert result_ko["detected"] is True
    assert result_ko["count"] == 1
    assert result_ko["objects"][0]["label_ko"] == "스마트폰"

    # Search for non-existent item
    result_missing = await tool(deps, target_object="강아지")
    assert result_missing["detected"] is False
    assert "찾지 못했습니다" in result_missing["message"]
