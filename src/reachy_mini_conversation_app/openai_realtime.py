"""OpenAI Realtime API backend: a thin subclass of the Hugging Face handler.

Only the Hugging Face-specific attachment points are overridden (client/auth,
24 kHz audio format, voice catalog, model selection). The conversation loop,
tool plumbing, and idle policy are inherited unchanged.
"""

import logging

import numpy as np
from numpy.typing import NDArray

from reachy_mini_conversation_app.config import DEFAULT_OPENAI_VOICE, config


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
