"""Tests for sound-direction (DoA) gaze support."""

import math
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

import reachy_mini_conversation_app.sound_direction as sd
from reachy_mini_conversation_app.sound_direction import (
    SpeakerGaze,
    SoundDirectionWatcher,
    doa_angle_to_head_yaw,
)


# --- angle mapping ------------------------------------------------------------


def test_angle_mapping_front_left_right() -> None:
    """DoA angles map onto head yaw: front->0, left->+clamp, right->-clamp."""
    assert doa_angle_to_head_yaw(math.pi / 2) == pytest.approx(0.0)
    assert doa_angle_to_head_yaw(0.0) == pytest.approx(sd.MAX_HEAD_YAW_RAD)
    assert doa_angle_to_head_yaw(math.pi) == pytest.approx(-sd.MAX_HEAD_YAW_RAD)
    assert doa_angle_to_head_yaw(1.0) == pytest.approx(math.pi / 2 - 1.0)


# --- watcher ------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> Any:
        return self._payload


class _FakeHttpx:
    """Serves scripted payloads; 'error' raises, None mimics a no-DoA daemon."""

    def __init__(self, payloads: list[Any]) -> None:
        self.payloads = list(payloads)

    def get(self, url: str, timeout: float) -> _FakeResponse:
        payload = self.payloads.pop(0) if len(self.payloads) > 1 else self.payloads[0]
        if payload == "error":
            raise ConnectionError("unreachable")
        return _FakeResponse(payload)


def test_poll_records_speech_and_calls_back(monkeypatch: Any) -> None:
    """A speech reading updates the recent angle and fires the callback."""
    heard: list[float] = []
    monkeypatch.setattr(sd, "httpx", _FakeHttpx([{"angle": 1.2, "speech_detected": True}]))
    watcher = SoundDirectionWatcher("10.0.0.1", 8000, on_speech=heard.append)

    watcher._poll_once()

    assert heard == [1.2]
    assert watcher.recent_speech_angle(5.0) == pytest.approx(1.2)
    assert watcher._failures == 0


def test_poll_without_speech_keeps_no_record(monkeypatch: Any) -> None:
    """Non-speech readings neither record nor call back."""
    heard: list[float] = []
    monkeypatch.setattr(sd, "httpx", _FakeHttpx([{"angle": 0.5, "speech_detected": False}]))
    watcher = SoundDirectionWatcher("10.0.0.1", 8000, on_speech=heard.append)

    watcher._poll_once()

    assert heard == []
    assert watcher.recent_speech_angle(5.0) is None


@pytest.mark.parametrize("payload", ["error", None])
def test_poll_failures_count_toward_disable(monkeypatch: Any, payload: Any) -> None:
    """Exceptions and null payloads (no DoA hardware) both count as failures."""
    monkeypatch.setattr(sd, "httpx", _FakeHttpx([payload]))
    watcher = SoundDirectionWatcher("10.0.0.1", 8000)

    watcher._poll_once()
    watcher._poll_once()

    assert watcher._failures == 2


def test_run_self_disables_after_failure_limit(monkeypatch: Any) -> None:
    """The polling loop exits on its own once the failure limit is reached."""
    monkeypatch.setattr(sd, "httpx", _FakeHttpx(["error"]))
    monkeypatch.setattr(sd, "DOA_POLL_INTERVAL_S", 0.0)
    watcher = SoundDirectionWatcher("10.0.0.1", 8000)

    watcher.run()  # run synchronously; must return instead of looping forever

    assert watcher._failures >= sd.DOA_FAILURE_LIMIT


def test_recent_speech_angle_expires(monkeypatch: Any) -> None:
    """Stale speech records are not returned."""
    watcher = SoundDirectionWatcher("10.0.0.1", 8000)
    watcher._last_speech_angle = 1.0
    watcher._last_speech_time = time.monotonic() - 20.0

    assert watcher.recent_speech_angle(10.0) is None
    assert watcher.recent_speech_angle(30.0) == pytest.approx(1.0)


# --- speaker gaze -------------------------------------------------------------


def _make_gaze(enabled: bool = True) -> tuple[SpeakerGaze, MagicMock, MagicMock]:
    movement_manager = MagicMock()
    movement_manager.is_idle.return_value = True
    movement_manager._head_tracking = False
    reachy_mini = MagicMock()
    reachy_mini.get_current_joint_positions.return_value = ([0.0], [0.0, 0.0])
    gaze = SpeakerGaze(movement_manager, reachy_mini, is_enabled=lambda: enabled)
    return gaze, movement_manager, reachy_mini


def test_speaker_gaze_queues_turn_toward_speech() -> None:
    """An enabled, idle robot turns toward the detected speech angle."""
    gaze, movement_manager, _ = _make_gaze()

    gaze.on_speech(0.3)  # well off-center

    movement_manager.queue_move.assert_called_once()
    movement_manager.set_moving_state.assert_called_once()


def test_speaker_gaze_respects_disable_and_busy_and_tracking() -> None:
    """Disabled, busy, or face-tracking states suppress the turn."""
    gaze, movement_manager, _ = _make_gaze(enabled=False)
    gaze.on_speech(0.3)
    movement_manager.queue_move.assert_not_called()

    gaze, movement_manager, _ = _make_gaze()
    movement_manager.is_idle.return_value = False
    gaze.on_speech(0.3)
    movement_manager.queue_move.assert_not_called()

    gaze, movement_manager, _ = _make_gaze()
    movement_manager._head_tracking = True
    gaze.on_speech(0.3)
    movement_manager.queue_move.assert_not_called()


# --- wake gaze ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_wake_from_standby_gazes_toward_recent_speech() -> None:
    """Waking looks toward the direction the wake phrase came from."""
    from unittest.mock import AsyncMock

    from reachy_mini_conversation_app.openai_realtime import OpenAIRealtimeHandler
    from reachy_mini_conversation_app.tools.core_tools import ToolDependencies

    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    deps.reachy_mini.get_current_joint_positions.return_value = ([0.0], [0.0, 0.0])
    handler = OpenAIRealtimeHandler(deps)
    handler._standby = True
    handler._safe_response_create = AsyncMock()  # type: ignore[method-assign]
    watcher = MagicMock()
    watcher.recent_speech_angle.return_value = 0.4  # speaker on the left
    handler.sound_watcher = watcher

    await handler.wake_from_standby()

    watcher.recent_speech_angle.assert_called_once_with(sd.WAKE_GAZE_MAX_AGE_S)
    deps.movement_manager.queue_move.assert_called()


@pytest.mark.asyncio
async def test_wake_from_standby_without_recent_speech_skips_gaze() -> None:
    """No fresh speech direction means no gaze move on wake."""
    from unittest.mock import AsyncMock

    from reachy_mini_conversation_app.openai_realtime import OpenAIRealtimeHandler
    from reachy_mini_conversation_app.tools.core_tools import ToolDependencies

    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    handler = OpenAIRealtimeHandler(deps)
    handler._standby = True
    handler._safe_response_create = AsyncMock()  # type: ignore[method-assign]
    watcher = MagicMock()
    watcher.recent_speech_angle.return_value = None
    handler.sound_watcher = watcher

    await handler.wake_from_standby()

    deps.movement_manager.queue_move.assert_not_called()


def test_speaker_gaze_threshold_and_cooldown() -> None:
    """Small angle changes and rapid re-triggers are ignored."""
    gaze, movement_manager, _ = _make_gaze()

    gaze.on_speech(0.3)
    gaze.on_speech(0.35)  # < threshold from previous target
    assert movement_manager.queue_move.call_count == 1

    gaze.on_speech(2.8)  # big change but still within cooldown
    assert movement_manager.queue_move.call_count == 1

    gaze._last_turn_time = time.monotonic() - 10.0
    gaze.on_speech(2.8)
    assert movement_manager.queue_move.call_count == 2
