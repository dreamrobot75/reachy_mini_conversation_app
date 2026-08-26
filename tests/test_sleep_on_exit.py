"""Tests for the REACHY_MINI_SLEEP_ON_EXIT flag."""

from typing import Any, Iterator

import pytest

from reachy_mini_conversation_app.config import config, refresh_runtime_config_from_env


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Yield monkeypatch and restore runtime config from the real env afterwards."""
    yield monkeypatch
    monkeypatch.undo()
    refresh_runtime_config_from_env()


def test_sleep_on_exit_defaults_to_enabled(env: Any) -> None:
    """Without the env var, sleep-on-exit is enabled."""
    env.delenv("REACHY_MINI_SLEEP_ON_EXIT", raising=False)
    refresh_runtime_config_from_env()
    assert config.REACHY_MINI_SLEEP_ON_EXIT is True


def test_sleep_on_exit_can_be_disabled(env: Any) -> None:
    """REACHY_MINI_SLEEP_ON_EXIT=0 turns the behavior off."""
    env.setenv("REACHY_MINI_SLEEP_ON_EXIT", "0")
    refresh_runtime_config_from_env()
    assert config.REACHY_MINI_SLEEP_ON_EXIT is False
