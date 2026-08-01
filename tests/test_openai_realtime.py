"""Tests for the OpenAI realtime backend (config + handler)."""

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import numpy as np
import pytest

import reachy_mini_conversation_app.huggingface_realtime as hf_mod
from reachy_mini_conversation_app.config import (
    HF_BACKEND,
    OPENAI_BACKEND,
    config,
    _normalize_conversation_backend,
)
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies


if TYPE_CHECKING:
    from reachy_mini_conversation_app.openai_realtime import OpenAIRealtimeHandler


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


def _fake_openai_client(captured_kwargs: dict[str, Any]) -> type:
    """Return a fake AsyncOpenAI class that records its constructor kwargs."""

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

    return FakeClient


def _make_handler(**kwargs: Any) -> "OpenAIRealtimeHandler":
    from reachy_mini_conversation_app.openai_realtime import OpenAIRealtimeHandler

    return OpenAIRealtimeHandler(
        ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock()),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_build_realtime_client_targets_openai_endpoint(monkeypatch: Any) -> None:
    """The client must hit api.openai.com with the API key and pass the model via connect query."""
    client_kwargs: dict[str, Any] = {}
    monkeypatch.setattr(hf_mod, "AsyncOpenAI", _fake_openai_client(client_kwargs))
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(config, "OPENAI_REALTIME_MODEL", "gpt-realtime-mini")

    handler = _make_handler()
    client = await handler._build_realtime_client()

    assert client is not None
    assert client_kwargs["api_key"] == "sk-test"
    assert client_kwargs["base_url"] == "https://api.openai.com/v1"
    assert client_kwargs["websocket_base_url"] == "wss://api.openai.com/v1"
    assert handler._realtime_connect_query == {"model": "gpt-realtime-mini"}


@pytest.mark.asyncio
async def test_build_realtime_client_requires_api_key(monkeypatch: Any) -> None:
    """A missing OPENAI_API_KEY must fail loudly, never silently connect."""
    monkeypatch.setattr(config, "OPENAI_API_KEY", None)

    handler = _make_handler()

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await handler._build_realtime_client()


@pytest.mark.xfail(reason="voice override lands in Task 4", strict=False)
def test_session_config_uses_24k_pcm_and_korean_language(monkeypatch: Any) -> None:
    """Session config must request 24 kHz PCM both ways and forward the transcription language."""
    monkeypatch.setattr(hf_mod, "get_session_instructions", lambda _instance_path=None: "test")
    # NOTE: the plan brief patches `oai_mod.get_session_voice`, which presumes Task 4's
    # `get_current_voice` override (importing get_session_voice into openai_realtime.py
    # and calling it there). Task 3 does not add that override yet, and importing
    # get_session_voice into openai_realtime.py without using it would be an unused
    # import under ruff. Until Task 4 lands, `_get_session_config` resolves the voice
    # through the inherited `get_current_voice`, which reads `hf_mod.get_session_voice`
    # (huggingface_realtime.py's own imported reference) -- so we patch it there instead.
    # Task 4 must switch this back to patching `oai_mod.get_session_voice` per the brief.
    monkeypatch.setattr(hf_mod, "get_session_voice", lambda default: default)
    monkeypatch.setattr(config, "REALTIME_TRANSCRIPTION_LANGUAGE", "ko")

    handler = _make_handler()
    session = handler._get_session_config([])

    assert session["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert session["audio"]["output"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert session["audio"]["input"]["transcription"]["language"] == "ko"
    assert session["audio"]["output"]["voice"] == "marin"
