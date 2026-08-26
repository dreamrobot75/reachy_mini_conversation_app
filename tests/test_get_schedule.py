"""Unit tests for GoogleCalendarService and GetSchedule tool."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reachy_mini_conversation_app.calendar_service import GoogleCalendarService
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.tools.get_schedule import GetSchedule


class _OAuthCredentials:
    def to_json(self) -> str:
        return '{"token": "access-token", "refresh_token": "refresh-token"}'


class _OAuthFlow:
    def __init__(self) -> None:
        self.credentials = _OAuthCredentials()
        self._authorization_started = False

    def authorization_url(self, **kwargs: object) -> tuple[str, str]:
        self._authorization_started = True
        return "https://accounts.google.com/o/oauth2/auth?state=oauth-state", "oauth-state"

    def fetch_token(self, *, code: str) -> None:
        if not self._authorization_started:
            raise ValueError("PKCE verifier was not preserved")


def test_calendar_service_unauthenticated_graceful_response() -> None:
    """When credentials don't exist, get_events should return the fixed default schedules."""
    service = GoogleCalendarService()
    with patch.object(service, "get_credentials", return_value=None):
        result = service.get_events(target_date="today")
        assert result["authenticated"] is False
        assert result["is_default"] is True
        assert result["event_count"] == 5
        assert len(result["events"]) == 5
        assert "팀 데일리 스크럼" in result["message"]


def test_calendar_service_generates_browser_auth_url_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server-managed OAuth credentials should enable one-click browser login."""
    monkeypatch.setattr("reachy_mini_conversation_app.calendar_service.CREDENTIALS_PATHS", [])
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    flow_factory = MagicMock(return_value=_OAuthFlow())
    monkeypatch.setattr(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
        flow_factory,
    )
    service = GoogleCalendarService()

    auth_url, error = service.get_auth_url(redirect_uri="http://localhost:7860/api/calendar/oauth2callback")

    assert service.has_credentials() is True
    assert error is None
    assert auth_url == "https://accounts.google.com/o/oauth2/auth?state=oauth-state"
    client_config = flow_factory.call_args.args[0]
    assert client_config["web"]["client_id"] == "client-id.apps.googleusercontent.com"
    assert client_config["web"]["client_secret"] == "client-secret"


def test_calendar_service_reuses_authorization_flow_for_token_exchange(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The OAuth callback must reuse the flow that owns the PKCE verifier."""
    credentials_path = tmp_path / "credentials.json"
    credentials_path.write_text("{}", encoding="utf-8")
    token_path = tmp_path / ".google_token.json"
    monkeypatch.setattr(
        "reachy_mini_conversation_app.calendar_service.CREDENTIALS_PATHS",
        [credentials_path],
    )
    monkeypatch.setattr("reachy_mini_conversation_app.calendar_service.TOKEN_PATH", token_path)
    monkeypatch.setattr(
        "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
        lambda *args, **kwargs: _OAuthFlow(),
    )
    service = GoogleCalendarService()

    auth_url, error = service.get_auth_url()
    exchanged = service.exchange_code("authorization-code", "oauth-state")

    assert error is None
    assert auth_url == "https://accounts.google.com/o/oauth2/auth?state=oauth-state"
    assert exchanged is True
    assert token_path.read_text(encoding="utf-8") == '{"token": "access-token", "refresh_token": "refresh-token"}'


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
