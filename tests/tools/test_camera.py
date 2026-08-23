"""Tests for the camera tool."""

import base64
from unittest.mock import MagicMock

import pytest

from reachy_mini_conversation_app.tools.camera import Camera
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies


@pytest.mark.asyncio
async def test_camera_tool_returns_base64_of_sdk_jpeg() -> None:
    """The tool base64-encodes the JPEG bytes returned by the SDK."""
    jpeg_bytes = b"\xff\xd8jpeg\xff\xd9"
    reachy_mini = MagicMock()
    reachy_mini.media.get_frame_jpeg.return_value = jpeg_bytes

    deps = ToolDependencies(
        reachy_mini=reachy_mini,
        movement_manager=MagicMock(),
        camera_enabled=True,
    )

    result = await Camera()(deps, question="What color is this?")

    assert result["b64_im"] == base64.b64encode(jpeg_bytes).decode("utf-8")


@pytest.mark.asyncio
async def test_camera_tool_captures_a_fresh_frame_on_each_call() -> None:
    """Repeat questions must capture a new frame, never reuse the previous one."""
    reachy_mini = MagicMock()
    reachy_mini.media.get_frame_jpeg.side_effect = [b"first-frame", b"second-frame"]

    deps = ToolDependencies(
        reachy_mini=reachy_mini,
        movement_manager=MagicMock(),
        camera_enabled=True,
    )

    camera = Camera()
    first = await camera(deps, question="What is this?")
    second = await camera(deps, question="And now?")

    assert first["b64_im"] == base64.b64encode(b"first-frame").decode("utf-8")
    assert second["b64_im"] == base64.b64encode(b"second-frame").decode("utf-8")
    assert reachy_mini.media.get_frame_jpeg.call_count == 2


def test_camera_tool_description_demands_recapture_for_every_question() -> None:
    """The tool description must tell the model to re-call the tool for each visual question."""
    description = Camera.description.lower()
    assert "outdated" in description
    assert "every new question" in description


@pytest.mark.asyncio
async def test_camera_tool_reports_error_when_no_frame() -> None:
    """With no frame available the tool returns an error."""
    reachy_mini = MagicMock()
    reachy_mini.media.get_frame_jpeg.return_value = None

    deps = ToolDependencies(
        reachy_mini=reachy_mini,
        movement_manager=MagicMock(),
        camera_enabled=True,
    )

    result = await Camera()(deps, question="What color is this?")

    assert "error" in result


@pytest.mark.asyncio
async def test_camera_tool_reports_error_when_camera_disabled() -> None:
    """With the camera disabled the tool returns an error and never reads a frame."""
    reachy_mini = MagicMock()
    deps = ToolDependencies(
        reachy_mini=reachy_mini,
        movement_manager=MagicMock(),
        camera_enabled=False,
    )

    result = await Camera()(deps, question="What color is this?")

    assert "error" in result
    reachy_mini.media.get_frame_jpeg.assert_not_called()
