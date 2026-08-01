"""Tests for the pomodoro timer tool."""

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

import reachy_mini_conversation_app.tools.pomodoro as pomodoro_mod
from reachy_mini_conversation_app.config import DEFAULT_PROFILES_DIRECTORY
from reachy_mini_conversation_app.tools.pomodoro import (
    MAX_MINUTES,
    DEFAULT_BREAK_MINUTES,
    DEFAULT_FOCUS_MINUTES,
    PomodoroTimer,
)
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies


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


def test_profile_enables_pomodoro_tool() -> None:
    """The Korean desk companion profile ships the pomodoro tool."""
    content = (DEFAULT_PROFILES_DIRECTORY / "desk_companion_ko" / "profile.md").read_text(encoding="utf-8")
    assert '"pomodoro_timer"' in content
    assert "뽀모도로" in content
