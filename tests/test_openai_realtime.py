"""Tests for the OpenAI realtime backend (config + handler)."""

from typing import Any

import numpy as np
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


def test_resample_pcm_16k_to_24k_length_and_dtype() -> None:
    """16 kHz mono int16 frames must resample to 1.5x length, keeping dtype."""
    from reachy_mini_conversation_app.openai_realtime import resample_pcm

    source = np.arange(1600, dtype=np.int16)
    result = resample_pcm(source, 16000, 24000)

    assert result.dtype == np.int16
    assert result.shape[0] == 2400
    # Monotone ramp stays monotone after linear interpolation.
    assert result[0] == source[0]
    assert int(result[-1]) >= int(source[-2])


def test_resample_pcm_same_rate_is_passthrough() -> None:
    """Same-rate input must be returned unchanged (no copy semantics required)."""
    from reachy_mini_conversation_app.openai_realtime import resample_pcm

    source = np.arange(160, dtype=np.int16)
    result = resample_pcm(source, 24000, 24000)

    assert np.array_equal(result, source)


def test_default_openai_voice_validates_config(monkeypatch: Any) -> None:
    """OPENAI_VOICE is normalized against the catalog; unsupported values fall back to marin."""
    from reachy_mini_conversation_app import openai_realtime as oai_mod

    monkeypatch.setattr(config, "OPENAI_VOICE", "CEDAR")
    assert oai_mod._default_openai_voice() == "cedar"

    monkeypatch.setattr(config, "OPENAI_VOICE", "Aiden")  # HF voice, not OpenAI
    assert oai_mod._default_openai_voice() == "marin"
