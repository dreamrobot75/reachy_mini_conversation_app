"""Tests for the OpenAI realtime backend (config + handler)."""

import pytest

from reachy_mini_conversation_app.config import (
    HF_BACKEND,
    OPENAI_BACKEND,
    config,
    _normalize_conversation_backend,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, HF_BACKEND),
        ("", HF_BACKEND),
        ("hf", HF_BACKEND),
        ("huggingface", HF_BACKEND),
        ("HF", HF_BACKEND),
        ("openai", OPENAI_BACKEND),
        ("OpenAI", OPENAI_BACKEND),
        ("bogus", HF_BACKEND),
    ],
)
def test_normalize_conversation_backend(raw: str | None, expected: str) -> None:
    """CONVERSATION_BACKEND accepts hf/huggingface/openai case-insensitively, defaults to HF."""
    assert _normalize_conversation_backend(raw) == expected


def test_config_exposes_openai_settings() -> None:
    """The config singleton must expose the OpenAI backend settings with safe defaults."""
    assert config.CONVERSATION_BACKEND in {HF_BACKEND, OPENAI_BACKEND}
    assert hasattr(config, "OPENAI_API_KEY")
    assert config.OPENAI_REALTIME_MODEL  # non-empty default
    assert config.OPENAI_VOICE  # non-empty default
