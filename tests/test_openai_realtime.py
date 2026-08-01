"""Tests for the OpenAI realtime backend (config + handler)."""

import base64
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

import reachy_mini_conversation_app.conversation_handler as conv_mod
import reachy_mini_conversation_app.huggingface_realtime as hf_mod
from reachy_mini_conversation_app.config import (
    HF_BACKEND,
    OPENAI_BACKEND,
    DEFAULT_PROFILES_DIRECTORY,
    config,
    _normalize_conversation_backend,
)
from reachy_mini_conversation_app.streaming import AdditionalOutputs
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


def test_resample_pcm_24k_to_16k_length_and_dtype() -> None:
    """24 kHz model audio must downsample to 2/3 length, keeping int16 dtype."""
    from reachy_mini_conversation_app.openai_realtime import resample_pcm

    source = (np.sin(np.arange(2400) * 0.05) * 10000).astype(np.int16)
    result = resample_pcm(source, 24000, 16000)

    assert result.dtype == np.int16
    assert result.shape[0] == 1600


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


def test_session_config_uses_24k_pcm_and_korean_language(monkeypatch: Any) -> None:
    """Session config must request 24 kHz PCM both ways and forward the transcription language."""
    from reachy_mini_conversation_app import openai_realtime as oai_mod

    monkeypatch.setattr(hf_mod, "get_session_instructions", lambda _instance_path=None: "test")
    monkeypatch.setattr(oai_mod, "get_session_voice", lambda default: default)
    monkeypatch.setattr(config, "REALTIME_TRANSCRIPTION_LANGUAGE", "ko")

    handler = _make_handler()
    session = handler._get_session_config([])

    assert session["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert session["audio"]["output"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert session["audio"]["input"]["transcription"]["language"] == "ko"
    assert session["audio"]["output"]["voice"] == "marin"


def test_voice_normalization_against_openai_catalog() -> None:
    """Case-insensitive OpenAI voices resolve; HF voices fall back to marin."""
    handler = _make_handler(startup_voice="CEDAR")
    assert handler.get_current_voice() == "cedar"

    handler_hf_voice = _make_handler(startup_voice="Aiden")
    assert handler_hf_voice.get_current_voice() == "marin"


@pytest.mark.asyncio
async def test_get_available_voices_returns_openai_catalog() -> None:
    """The UI voice list must be the OpenAI catalog, not the HF one."""
    from reachy_mini_conversation_app.openai_realtime import OPENAI_AVAILABLE_VOICES

    handler = _make_handler()
    assert await handler.get_available_voices() == OPENAI_AVAILABLE_VOICES


@pytest.mark.asyncio
async def test_change_voice_updates_live_session(monkeypatch: Any) -> None:
    """Changing voice should update the active session in place, like the HF handler."""
    captured_update: dict[str, Any] = {}

    class FakeSession:
        async def update(self, **kwargs: Any) -> None:
            captured_update.update(kwargs)

    class FakeConnection:
        session = FakeSession()

    handler = _make_handler()
    handler.connection = FakeConnection()

    result = await handler.change_voice("cedar")

    assert result == "Voice changed to cedar."
    assert handler.get_current_voice() == "cedar"
    assert captured_update["session"]["audio"]["output"]["voice"] == "cedar"


@pytest.mark.asyncio
async def test_receive_resamples_mic_frames_to_24k() -> None:
    """16 kHz mic frames must arrive at the connection as 24 kHz PCM16."""
    appended: list[str] = []

    class FakeInputBuffer:
        async def append(self, audio: str) -> None:
            appended.append(audio)

    class FakeConnection:
        input_audio_buffer = FakeInputBuffer()

    handler = _make_handler()
    handler.connection = FakeConnection()

    frame = (16000, np.arange(1600, dtype=np.int16))
    await handler.receive(frame)

    assert len(appended) == 1
    decoded = np.frombuffer(base64.b64decode(appended[0]), dtype=np.int16)
    assert decoded.shape[0] == 2400


@pytest.mark.asyncio
async def test_emit_resamples_model_audio_to_output_device_rate(monkeypatch: Any) -> None:
    """24 kHz model audio must reach the playback path at the device rate, not 1.5x slow."""
    handler = _make_handler()
    handler.deps.reachy_mini.media.get_output_audio_samplerate.return_value = 16000
    pcm = (np.sin(np.arange(2400) * 0.05) * 10000).astype(np.int16).reshape(1, -1)
    monkeypatch.setattr(conv_mod, "wait_for_item", AsyncMock(return_value=(24000, pcm)))

    result = await handler.emit()

    assert isinstance(result, tuple)
    rate, audio = result
    assert rate == 16000
    assert audio.dtype == np.int16
    assert audio.shape == (1, 1600)


@pytest.mark.asyncio
async def test_emit_passes_through_non_audio_output(monkeypatch: Any) -> None:
    """Transcript payloads and empty emissions must pass through untouched."""
    handler = _make_handler()
    handler.deps.reachy_mini.media.get_output_audio_samplerate.return_value = 16000
    outputs = AdditionalOutputs({"role": "assistant", "content": "hi"})
    monkeypatch.setattr(conv_mod, "wait_for_item", AsyncMock(return_value=outputs))

    assert await handler.emit() is outputs

    monkeypatch.setattr(conv_mod, "wait_for_item", AsyncMock(return_value=None))
    assert await handler.emit() is None


@pytest.mark.asyncio
async def test_emit_falls_back_to_16k_when_device_rate_unavailable(monkeypatch: Any) -> None:
    """A media backend that cannot report its rate must not break playback."""
    handler = _make_handler()
    handler.deps.reachy_mini.media.get_output_audio_samplerate.side_effect = RuntimeError("no device")
    pcm = np.zeros(2400, dtype=np.int16)
    monkeypatch.setattr(conv_mod, "wait_for_item", AsyncMock(return_value=(24000, pcm)))

    rate, audio = await handler.emit()

    assert rate == 16000
    assert audio.shape == (1600,)


@pytest.mark.asyncio
async def test_emit_keeps_audio_when_device_matches_model_rate(monkeypatch: Any) -> None:
    """A 24 kHz-capable output device must receive the model audio unchanged."""
    handler = _make_handler()
    handler.deps.reachy_mini.media.get_output_audio_samplerate.return_value = 24000
    pcm = np.arange(240, dtype=np.int16).reshape(1, -1)
    monkeypatch.setattr(conv_mod, "wait_for_item", AsyncMock(return_value=(24000, pcm)))

    rate, audio = await handler.emit()

    assert rate == 24000
    assert np.array_equal(audio, pcm)


def test_desk_companion_ko_profile_exists_and_speaks_korean() -> None:
    """The Korean desk companion profile must exist in the new profile.md format."""
    profile_path = DEFAULT_PROFILES_DIRECTORY / "desk_companion_ko" / "profile.md"
    assert profile_path.is_file()

    content = profile_path.read_text(encoding="utf-8")
    assert content.startswith("+++")
    assert "schema_version = 1" in content
    assert "한국어" in content
