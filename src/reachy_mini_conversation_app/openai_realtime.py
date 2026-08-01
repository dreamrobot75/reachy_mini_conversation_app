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
from openai.types.realtime import RealtimeSessionCreateRequestParam

from reachy_mini_conversation_app.config import OPENAI_REALTIME_URL, DEFAULT_OPENAI_VOICE, config
from reachy_mini_conversation_app.prompts import get_session_voice
from reachy_mini_conversation_app.streaming import audio_to_int16
from reachy_mini_conversation_app.tools.core_tools import ToolSpec
from reachy_mini_conversation_app.conversation_handler import HandlerOutput
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
OPENAI_TARGET_SAMPLE_RATE: int = 24000

# Rate assumed when the media backend cannot report its output sample rate.
FALLBACK_OUTPUT_SAMPLE_RATE: int = 16000

# 3-tap binomial low-pass applied before downsampling to limit aliasing.
_ANTI_ALIAS_KERNEL = np.array([0.25, 0.5, 0.25], dtype=np.float64)


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
    """Linearly resample mono int16 PCM between the mic/speaker and OpenAI's 24 kHz.

    Used both ways: 16 kHz mic -> 24 kHz uplink, and 24 kHz model audio -> the
    output device rate. Downsampling first runs a cheap 3-tap low-pass so the
    content above the new Nyquist frequency does not alias; upsampling needs no
    filter.

    Known limitation: resampling happens per frame and each frame is
    interpolated over its own endpoints, so frame boundaries are not
    phase-continuous. The artifact is inaudible at speech frame sizes and
    avoiding it would require carrying filter state across calls.
    """
    if audio.size == 0 or source_rate == target_rate:
        return audio
    audio_float = audio.astype(np.float64)
    if target_rate < source_rate:
        audio_float = np.convolve(audio_float, _ANTI_ALIAS_KERNEL, mode="same")
    target_length = max(1, round(audio.shape[0] * target_rate / source_rate))
    source_positions = np.arange(audio.shape[0], dtype=np.float64)
    target_positions = np.linspace(0.0, audio.shape[0] - 1, num=target_length)
    resampled = np.interp(target_positions, source_positions, audio_float)
    return np.round(resampled).astype(np.int16)


class OpenAIRealtimeHandler(HuggingFaceRealtimeHandler):
    """Realtime stream handler for the OpenAI Realtime API."""

    SAMPLE_RATE = OPENAI_TARGET_SAMPLE_RATE

    _output_sample_rate: int | None = None

    def _get_output_sample_rate(self) -> int:
        """Return (and cache) the playback device rate, falling back to 16 kHz."""
        cached = self._output_sample_rate
        if cached is not None:
            return cached

        rate = FALLBACK_OUTPUT_SAMPLE_RATE
        try:
            reported = self.deps.reachy_mini.media.get_output_audio_samplerate()
        except Exception as e:
            logger.warning("Could not read the output sample rate (%s); assuming %d Hz", e, rate)
        else:
            if isinstance(reported, int) and not isinstance(reported, bool) and reported > 0:
                rate = reported
            else:
                logger.warning("Ignoring invalid output sample rate %r; assuming %d Hz", reported, rate)

        self._output_sample_rate = rate
        logger.info("Playback sample rate: %d Hz (model audio is %d Hz)", rate, self.SAMPLE_RATE)
        return rate

    async def emit(self) -> HandlerOutput:
        """Emit queued output, resampling model audio to the playback device rate.

        The playback path downstream (`console.py` -> `push_audio_sample`) drops
        the rate from the emitted tuple and feeds a fixed-rate sink, so 24 kHz
        model audio would otherwise play back slowed down. Resample here, where
        the rate is still known.
        """
        handler_output = await super().emit()
        if not isinstance(handler_output, tuple):
            return handler_output

        source_rate, audio = handler_output
        target_rate = self._get_output_sample_rate()
        if source_rate == target_rate or audio.size == 0:
            return handler_output

        flat = np.asarray(audio).reshape(-1)
        resampled = resample_pcm(flat, source_rate, target_rate)
        if audio.ndim == 2:
            resampled = resampled.reshape(1, -1)
        return (target_rate, resampled)

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
        """Change the voice, reconnecting the session because OpenAI locks it after audio."""
        default_voice = _default_openai_voice()
        resolved_voice = (
            self._resolve_backend_voice(voice, source="requested voice", fallback=default_voice) or default_voice
        )
        self._voice_override = resolved_voice
        if self.connection is not None:
            # OpenAI rejects session.update voice changes once a response has produced
            # audio, and the startup greeting guarantees it has. Restart instead, the
            # same way the parent handler recovers in apply_personality().
            try:
                await self._restart_session()
                return f"Voice changed to {resolved_voice}; reconnecting session."
            except Exception as e:
                logger.warning("Failed to restart session for voice change: %s", e)
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
