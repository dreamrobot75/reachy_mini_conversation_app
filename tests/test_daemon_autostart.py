"""Tests for optional remote daemon auto-start."""

from typing import Any

import pytest

import reachy_mini_conversation_app.daemon_autostart as autostart_mod
from reachy_mini_conversation_app.daemon_autostart import ensure_remote_daemon_running


class _FakeResponse:
    def __init__(self, state: str) -> None:
        self._state = state

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return {"state": self._state}


class _FakeHttpx:
    """Fake httpx module recording calls and serving scripted daemon states."""

    def __init__(self, states: list[str]) -> None:
        self.states = list(states)
        self.get_calls: list[str] = []
        self.post_calls: list[str] = []

    def get(self, url: str, timeout: float) -> _FakeResponse:
        self.get_calls.append(url)
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if state == "error":
            raise ConnectionError("unreachable")
        return _FakeResponse(state)

    def post(self, url: str, params: dict[str, str], timeout: float) -> _FakeResponse:
        self.post_calls.append(url)
        return _FakeResponse("stopped")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: Any) -> None:
    monkeypatch.setattr(autostart_mod.time, "sleep", lambda _s: None)


def test_running_daemon_is_left_alone(monkeypatch: Any) -> None:
    """A running daemon needs no action and no start request."""
    fake = _FakeHttpx(["running"])
    monkeypatch.setattr(autostart_mod, "httpx", fake)

    assert ensure_remote_daemon_running("10.0.0.1", 8000, auto_start=True) == "running"
    assert fake.post_calls == []


def test_stopped_daemon_without_optin_only_warns(monkeypatch: Any) -> None:
    """Without the opt-in flag a stopped daemon is reported, never started."""
    fake = _FakeHttpx(["stopped"])
    monkeypatch.setattr(autostart_mod, "httpx", fake)

    assert ensure_remote_daemon_running("10.0.0.1", 8000, auto_start=False) == "stopped"
    assert fake.post_calls == []


def test_stopped_daemon_with_optin_starts_and_waits(monkeypatch: Any) -> None:
    """With opt-in the daemon is started and polled until running."""
    fake = _FakeHttpx(["stopped", "stopped", "running"])
    monkeypatch.setattr(autostart_mod, "httpx", fake)

    result = ensure_remote_daemon_running("10.0.0.1", 8000, auto_start=True)

    assert result == "started"
    assert len(fake.post_calls) == 1
    assert fake.post_calls[0].endswith("/api/daemon/start")


def test_start_timeout_reports_timeout(monkeypatch: Any) -> None:
    """If the daemon never reaches running, report a timeout instead of hanging."""
    fake = _FakeHttpx(["stopped"])
    monkeypatch.setattr(autostart_mod, "httpx", fake)

    result = ensure_remote_daemon_running("10.0.0.1", 8000, auto_start=True, start_timeout_s=0.01)

    assert result == "timeout"


def test_unreachable_daemon_returns_unknown(monkeypatch: Any) -> None:
    """An unreachable daemon is reported as unknown; connection flow decides next."""
    fake = _FakeHttpx(["error"])
    monkeypatch.setattr(autostart_mod, "httpx", fake)

    assert ensure_remote_daemon_running("10.0.0.1", 8000, auto_start=True) == "unknown"
