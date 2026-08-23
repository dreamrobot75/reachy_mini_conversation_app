"""Unit tests for GoogleCalendarService and GetSchedule tool."""

from unittest.mock import MagicMock, patch

import pytest

from reachy_mini_conversation_app.calendar_service import GoogleCalendarService
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.tools.get_schedule import GetSchedule


def test_calendar_service_unauthenticated_graceful_response() -> None:
    """When credentials don't exist, get_events should return an informative unauthenticated message."""
    service = GoogleCalendarService()
    with patch.object(service, "get_credentials", return_value=None):
        result = service.get_events(target_date="today")
        assert result["authenticated"] is False
        assert result["event_count"] == 0
        assert "구글 캘린더 OAuth 인증이 필요합니다" in result["message"]


def test_calendar_service_success_formatting() -> None:
    """When events exist, verify correct summary and message formatting."""
    service = GoogleCalendarService()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {
                "summary": "오픈소스 개발자대회 멘토링",
                "start": {"dateTime": "2026-08-23T10:00:00+09:00"},
                "end": {"dateTime": "2026-08-23T11:30:00+09:00"},
            },
            {
                "summary": "팀 주간 회의",
                "start": {"dateTime": "2026-08-23T14:00:00+09:00"},
                "end": {"dateTime": "2026-08-23T15:00:00+09:00"},
            },
        ]
    }

    with (
        patch.object(service, "get_access_token", return_value="mock_access_token"),
        patch("httpx.get", return_value=mock_resp),
    ):
        result = service.get_events(target_date="today")
        assert result["authenticated"] is True
        assert result["event_count"] == 2
        assert len(result["events"]) == 2
        assert "총 2건의 일정이 있습니다" in result["message"]
        assert "오픈소스 개발자대회 멘토링" in result["message"]


@pytest.mark.asyncio
async def test_get_schedule_tool_execution() -> None:
    """Verify GetSchedule tool returns calendar events properly."""
    tool = GetSchedule()
    mock_robot = MagicMock()
    mock_movement = MagicMock()
    deps = ToolDependencies(reachy_mini=mock_robot, movement_manager=mock_movement, camera_enabled=True)

    expected_return = {
        "authenticated": True,
        "date": "2026-08-23",
        "event_count": 1,
        "events": [{"summary": "테스트 회의", "start": "10:00", "end": "11:00"}],
        "message": "오늘 총 1건의 일정이 있습니다.",
    }

    with patch.object(tool._service, "get_events", return_value=expected_return):
        res = await tool(deps, target_date="today")
        assert res["authenticated"] is True
        assert res["event_count"] == 1
        assert "테스트 회의" in res["events"][0]["summary"]
