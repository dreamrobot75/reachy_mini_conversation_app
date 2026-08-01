"""OpenAI Realtime API backend: a thin subclass of the Hugging Face handler.

Only the Hugging Face-specific attachment points are overridden (client/auth,
24 kHz audio format, voice catalog, model selection). The conversation loop,
tool plumbing, and idle policy are inherited unchanged.
"""

import logging

import numpy as np
from openai import AsyncOpenAI
from numpy.typing import NDArray
from openai.types.realtime import RealtimeSessionCreateRequestParam

from reachy_mini_conversation_app.config import OPENAI_REALTIME_URL, DEFAULT_OPENAI_VOICE, config
from reachy_mini_conversation_app.tools.core_tools import ToolSpec
from reachy_mini_conversation_app.huggingface_realtime import (
    HuggingFaceRealtimeHandler,
    _build_openai_compatible_client_from_realtime_url,
)


logger = logging.getLogger(__name__)

# gpt-realtime voice catalog. marin and cedar are the newest, most natural voices.
OPENAI_AVAILABLE_VOICES: list[str] = [
    "alloy",
    "ash",
    "ballad",
    "cedar",
    "coral",
    "echo",
    "marin",
    "sage",
    "shimmer",
    "verse",
]

# The OpenAI realtime endpoint only accepts 24 kHz PCM16.
OPENAI_TARGET_SAMPLE_RATE = 24000


def _default_openai_voice() -> str:
    """Return the configured default OpenAI voice, validated against the catalog."""
    configured = (getattr(config, "OPENAI_VOICE", None) or "").strip()
    voice_by_lowercase = {candidate.lower(): candidate for candidate in OPENAI_AVAILABLE_VOICES}
    normalized = voice_by_lowercase.get(configured.lower())
    if normalized is not None:
        return normalized
    if configured:
        logger.warning("Ignoring unsupported OPENAI_VOICE %r; using %s", configured, DEFAULT_OPENAI_VOICE)
    return DEFAULT_OPENAI_VOICE


def resample_pcm(
    audio: NDArray[np.int16],
    source_rate: int,
    target_rate: int,
) -> NDArray[np.int16]:
    """Linearly resample mono int16 PCM; adequate for 16 kHz mic -> 24 kHz speech."""
    if audio.size == 0 or source_rate == target_rate:
        return audio
    target_length = max(1, round(audio.shape[0] * target_rate / source_rate))
    source_positions = np.arange(audio.shape[0], dtype=np.float64)
    target_positions = np.linspace(0.0, audio.shape[0] - 1, num=target_length)
    resampled = np.interp(target_positions, source_positions, audio.astype(np.float64))
    return np.round(resampled).astype(np.int16)


class OpenAIRealtimeHandler(HuggingFaceRealtimeHandler):
    """Realtime stream handler for the OpenAI Realtime API."""

    SAMPLE_RATE = OPENAI_TARGET_SAMPLE_RATE

    async def _build_realtime_client(self) -> AsyncOpenAI:
        """Build the OpenAI realtime client from OPENAI_API_KEY."""
        api_key = (getattr(config, "OPENAI_API_KEY", None) or "").strip()
        if not api_key:
            raise RuntimeError("CONVERSATION_BACKEND=openai requires OPENAI_API_KEY to be set")
        client, connect_query = _build_openai_compatible_client_from_realtime_url(
            OPENAI_REALTIME_URL,
            api_key,
        )
        connect_query["model"] = config.OPENAI_REALTIME_MODEL
        self._realtime_connect_query = connect_query
        logger.info("Using OpenAI realtime endpoint (model=%s)", config.OPENAI_REALTIME_MODEL)
        return client

    def _get_session_config(self, tool_specs: list[ToolSpec]) -> RealtimeSessionCreateRequestParam:
        """Return the inherited session config adjusted to OpenAI's 24 kHz PCM."""
        session = super()._get_session_config(tool_specs)
        pcm_24k = {"type": "audio/pcm", "rate": OPENAI_TARGET_SAMPLE_RATE}
        session["audio"]["input"]["format"] = pcm_24k  # type: ignore[typeddict-item]
        session["audio"]["output"]["format"] = pcm_24k  # type: ignore[typeddict-item]
        return session
