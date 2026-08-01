"""OpenAI Realtime API backend: a thin subclass of the Hugging Face handler.

Only the Hugging Face-specific attachment points are overridden (client/auth,
24 kHz audio format, voice catalog, model selection). The conversation loop,
tool plumbing, and idle policy are inherited unchanged.
"""

import base64
import logging
from typing import Tuple

import numpy as np
from openai import AsyncOpenAI
from numpy.typing import NDArray
from openai.types.realtime import (
    RealtimeAudioConfigParam,
    RealtimeAudioConfigOutputParam,
    RealtimeSessionCreateRequestParam,
)

from reachy_mini_conversation_app.config import OPENAI_REALTIME_URL, DEFAULT_OPENAI_VOICE, config
from reachy_mini_conversation_app.prompts import get_session_voice
from reachy_mini_conversation_app.streaming import audio_to_int16
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

    async def get_available_voices(self) -> list[str]:
        """Return the OpenAI realtime voice catalog."""
        return list(OPENAI_AVAILABLE_VOICES)

    def _resolve_backend_voice(
        self,
        voice: str | None,
        *,
        source: str,
        fallback: str | None = None,
    ) -> str | None:
        """Return an OpenAI-supported voice, optionally falling back when unsupported."""
        voice_value = (voice or "").strip()
        if not voice_value:
            return fallback

        voice_by_lowercase = {candidate.lower(): candidate for candidate in OPENAI_AVAILABLE_VOICES}
        normalized_voice = voice_by_lowercase.get(voice_value.lower())
        if normalized_voice is not None:
            return normalized_voice

        logger.warning(
            "Ignoring unsupported %s %r; expected one of %s",
            source,
            voice,
            OPENAI_AVAILABLE_VOICES,
        )
        return fallback

    def get_current_voice(self) -> str:
        """Return the voice currently selected for this handler."""
        default_voice = _default_openai_voice()
        voice = self._voice_override or get_session_voice(default=default_voice)
        return self._resolve_backend_voice(voice, source="session voice", fallback=default_voice) or default_voice

    async def change_voice(self, voice: str) -> str:
        """Change only the voice, updating the active session when possible."""
        default_voice = _default_openai_voice()
        resolved_voice = (
            self._resolve_backend_voice(voice, source="requested voice", fallback=default_voice) or default_voice
        )
        self._voice_override = resolved_voice
        if self.connection is not None:
            try:
                await self.connection.session.update(
                    session=RealtimeSessionCreateRequestParam(
                        type="realtime",
                        audio=RealtimeAudioConfigParam(
                            output=RealtimeAudioConfigOutputParam(voice=resolved_voice),
                        ),
                    ),
                )
                return f"Voice changed to {resolved_voice}."
            except Exception as e:
                logger.warning("Failed to update live session for voice change: %s", e)
                return "Voice change failed. Will take effect on next connection."
        return "Voice changed. Will take effect on next connection."

    async def receive(self, frame: Tuple[int, NDArray[np.int16]]) -> None:
        """Resample mic audio to 24 kHz and forward it to the realtime server."""
        if not self.connection:
            return

        source_rate, audio_frame = frame
        if audio_frame.size == 0:
            return

        # Mono-ize using the same conventions as the parent handler.
        if audio_frame.ndim == 2:
            if audio_frame.shape[1] > audio_frame.shape[0]:
                audio_frame = audio_frame.T
            if audio_frame.shape[1] > 1:
                audio_frame = audio_frame[:, 0]
        audio_frame = np.asarray(audio_frame).reshape(-1)

        audio_frame = audio_to_int16(audio_frame)
        audio_frame = resample_pcm(audio_frame, source_rate, self.SAMPLE_RATE)

        try:
            audio_message = base64.b64encode(audio_frame.tobytes()).decode("utf-8")
            await self.connection.input_audio_buffer.append(audio=audio_message)
        except Exception as e:
            logger.debug("Dropping audio frame: connection not ready (%s)", e)
            return
