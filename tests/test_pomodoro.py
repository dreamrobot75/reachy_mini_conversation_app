"""Tests for the pomodoro timer tool."""

import json
import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

import reachy_mini_conversation_app.tools.pomodoro_timer as pomodoro_mod
from reachy_mini_conversation_app.config import DEFAULT_PROFILES_DIRECTORY
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies
from reachy_mini_conversation_app.tools.pomodoro_timer import (
    MAX_MINUTES,
    DEFAULT_BREAK_MINUTES,
    DEFAULT_FOCUS_MINUTES,
    PomodoroTimer,
)
from reachy_mini_conversation_app.tools.tool_constants import DETACHED_CALL_ID_PREFIX


class _FakeToolManager:
    """Records detached countdown launches instead of running them."""

    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []

    async def start_tool(self, call_id: str, tool_call_routine: Any, is_idle_tool_call: bool) -> None:
        self.started.append(
            {
                "call_id": call_id,
                "tool_name": tool_call_routine.tool_name,
                "args": json.loads(tool_call_routine.args_json_str),
                "is_idle_tool_call": is_idle_tool_call,
            }
        )


def _deps() -> ToolDependencies:
    return ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())


@pytest.fixture
def instant_sleep(monkeypatch: Any) -> list[float]:
    """Replace the timer sleep with an instant one that records durations."""
    slept: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(pomodoro_mod.asyncio, "sleep", _fake_sleep)
    return slept


@pytest.mark.asyncio
async def test_focus_completion_instructs_auto_break(instant_sleep: list[float]) -> None:
    """Finishing a focus phase tells the model to start the break immediately."""
    result = await PomodoroTimer()(_deps(), phase="focus", cycle=1, total_cycles=4)

    assert result["status"] == "focus_complete"
    assert result["cycle"] == 1
    assert result["total_cycles"] == 4
    assert result["minutes"] == DEFAULT_FOCUS_MINUTES
    assert "break" in result["next_action"]
    assert instant_sleep == [DEFAULT_FOCUS_MINUTES * 60]


@pytest.mark.asyncio
async def test_break_completion_mid_cycle_asks_to_continue(instant_sleep: list[float]) -> None:
    """A mid-cycle break end asks the user before the next set."""
    result = await PomodoroTimer()(_deps(), phase="break", cycle=1, total_cycles=4)

    assert result["status"] == "break_complete"
    assert result["minutes"] == DEFAULT_BREAK_MINUTES
    assert "물어" in result["next_action"]


@pytest.mark.asyncio
async def test_final_break_completion_celebrates(instant_sleep: list[float]) -> None:
    """The last break ends the whole pomodoro with a celebration instruction."""
    result = await PomodoroTimer()(_deps(), phase="break", cycle=4, total_cycles=4)

    assert result["status"] == "pomodoro_done"
    assert "축하" in result["next_action"]


@pytest.mark.asyncio
async def test_minutes_clamped_and_custom(instant_sleep: list[float]) -> None:
    """Minutes are honored and clamped into the sane range."""
    result = await PomodoroTimer()(_deps(), phase="focus", minutes=999)
    assert result["minutes"] == MAX_MINUTES

    result = await PomodoroTimer()(_deps(), phase="focus", minutes=0)
    assert result["minutes"] == 1

    result = await PomodoroTimer()(_deps(), phase="focus", minutes=10)
    assert result["minutes"] == 10


@pytest.mark.asyncio
async def test_focus_completion_announces_default_focus_and_break_minutes(instant_sleep: list[float]) -> None:
    """Without custom times the announcement uses the 25/5 defaults."""
    result = await PomodoroTimer()(_deps(), phase="focus")

    assert result["announce"] == "집중 시간 25분이 끝났어요! 5분간 가볍게 스트레칭하세요."
    assert "minutes=5" in result["next_action"]
    assert instant_sleep == [DEFAULT_FOCUS_MINUTES * 60]


@pytest.mark.asyncio
async def test_focus_completion_announces_custom_minutes(instant_sleep: list[float]) -> None:
    """A '1분간 집중' style request runs 1 minute and announces the real durations."""
    result = await PomodoroTimer()(_deps(), phase="focus", minutes=1, break_minutes=10)

    assert result["minutes"] == 1
    assert result["announce"] == "집중 시간 1분이 끝났어요! 10분간 가볍게 스트레칭하세요."
    assert "minutes=10" in result["next_action"]
    assert instant_sleep == [60]


@pytest.mark.asyncio
async def test_invalid_break_minutes_returns_error(instant_sleep: list[float]) -> None:
    """A non-numeric break_minutes fails with an error dict before sleeping."""
    result = await PomodoroTimer()(_deps(), phase="focus", break_minutes="soon")

    assert "error" in result
    assert instant_sleep == []


@pytest.mark.asyncio
async def test_invalid_phase_returns_error(instant_sleep: list[float]) -> None:
    """Unknown phases fail with an error dict, never an exception."""
    result = await PomodoroTimer()(_deps(), phase="nap")

    assert "error" in result
    assert instant_sleep == []


@pytest.mark.asyncio
async def test_cancellation_propagates(monkeypatch: Any) -> None:
    """task_cancel must be able to cancel the timer: CancelledError propagates."""

    async def _cancelled_sleep(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(pomodoro_mod.asyncio, "sleep", _cancelled_sleep)

    with pytest.raises(asyncio.CancelledError):
        await PomodoroTimer()(_deps(), phase="focus")


@pytest.mark.asyncio
async def test_focus_start_returns_immediately_with_start_announcement(instant_sleep: list[float]) -> None:
    """With a tool manager the tool returns at once so the start line is always spoken."""
    manager = _FakeToolManager()
    result = await PomodoroTimer()(_deps(), phase="focus", minutes=1, break_minutes=10, tool_manager=manager)

    assert result["status"] == "focus_started"
    assert result["announce"] == "지금부터 1분간 집중 시작!"
    assert instant_sleep == []  # no blocking wait in the start call

    assert len(manager.started) == 1
    spawn = manager.started[0]
    assert spawn["call_id"].startswith(DETACHED_CALL_ID_PREFIX)
    assert spawn["tool_name"] == "pomodoro_timer"
    assert spawn["args"]["_wait"] is True
    assert spawn["args"]["minutes"] == 1
    assert spawn["args"]["break_minutes"] == 10


@pytest.mark.asyncio
async def test_break_start_returns_immediately_without_duplicate_announcement(instant_sleep: list[float]) -> None:
    """The auto-started break must not repeat the stretching announcement."""
    manager = _FakeToolManager()
    result = await PomodoroTimer()(_deps(), phase="break", minutes=5, tool_manager=manager)

    assert result["status"] == "break_started"
    assert instant_sleep == []
    assert manager.started[0]["args"]["phase"] == "break"


@pytest.mark.asyncio
async def test_detached_wait_call_runs_the_countdown(instant_sleep: list[float]) -> None:
    """The spawned _wait call sleeps the full phase and returns the completion payload."""
    result = await PomodoroTimer()(_deps(), phase="focus", minutes=1, break_minutes=10, _wait=True)

    assert result["status"] == "focus_complete"
    assert result["announce"] == "집중 시간 1분이 끝났어요! 10분간 가볍게 스트레칭하세요."
    assert instant_sleep == [60]


def test_profile_enables_pomodoro_tool() -> None:
    """The Korean desk companion profile ships the pomodoro tool."""
    content = (DEFAULT_PROFILES_DIRECTORY / "desk_companion_ko" / "profile.md").read_text(encoding="utf-8")
    assert '"pomodoro_timer"' in content
    assert "뽀모도로" in content


def test_profile_and_tool_require_explicit_start_announcement() -> None:
    """Starting a focus phase must be announced as '지금부터 X분간 집중 시작!'."""
    content = (DEFAULT_PROFILES_DIRECTORY / "desk_companion_ko" / "profile.md").read_text(encoding="utf-8")
    assert "지금부터" in content and "집중 시작" in content
    assert "지금부터" in PomodoroTimer.description and "집중 시작" in PomodoroTimer.description
