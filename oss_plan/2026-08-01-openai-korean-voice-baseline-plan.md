# OpenAI 한국어 음성 베이스라인 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.env`에 `CONVERSATION_BACKEND=openai` + `OPENAI_API_KEY`를 넣으면 앱 전체가 OpenAI Realtime API로 한국어 대화를 하는 백엔드 provider를 추가한다.

**Architecture:** `openai_realtime.py`의 `OpenAIRealtimeHandler`가 `HuggingFaceRealtimeHandler`를 상속하고 HF 고정 지점 4곳(클라이언트/인증, 오디오 포맷 24 kHz, 보이스 카탈로그, 모델 선택)만 오버라이드한다. 대화 루프·도구·유휴 정책은 전부 부모 로직을 재사용한다. `main.py`의 기존 핸들러 팩토리에 분기 한 개를 추가한다.

**Tech Stack:** Python 3.10+, openai==2.28.0 (이미 의존성), numpy (전이 의존성, 이미 사용 중), pytest + pytest-asyncio

**Spec:** [`oss_plan/2026-08-01-openai-korean-voice-baseline-design.md`](2026-08-01-openai-korean-voice-baseline-design.md)

## Global Constraints

- 신규 pip 의존성 금지 — `uv.lock` 변경 없음. 리샘플링은 numpy `np.interp`로 구현 (scipy는 직접 의존성이 아니므로 사용 금지)
- upstream 파일 수정 최소화: `config.py`(설정 블록 추가), `main.py`(팩토리 분기), `.env.example`만. `huggingface_realtime.py`는 절대 수정하지 않는다
- 모든 커밋 전 게이트: `ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v`
- 테스트는 실제 API를 호출하지 않는다 (기존 `tests/test_huggingface_realtime.py`의 fake/monkeypatch 패턴 준수)
- Windows 개발 환경 포함: 하드코딩 경로 금지
- 커밋 메시지는 upstream 규칙(`feat:`/`test:`/`docs:`) 준수

---

### Task 1: config.py 백엔드 설정 + .env.example

**Files:**
- Modify: `src/reachy_mini_conversation_app/config.py` (상수·정규화 함수·Config 속성·refresh 함수)
- Modify: `.env.example` (OpenAI 설정 블록)
- Test: `tests/test_openai_realtime.py` (신규 파일)

**Interfaces:**
- Consumes: 기존 `HF_BACKEND = "huggingface"` 상수 (config.py:63), `config` 싱글턴
- Produces (이후 태스크가 의존):
  - `OPENAI_BACKEND: str = "openai"`, `OPENAI_REALTIME_URL: str`, `DEFAULT_OPENAI_REALTIME_MODEL: str`, `DEFAULT_OPENAI_VOICE: str` (모듈 상수)
  - `_normalize_conversation_backend(value: str | None) -> str`
  - `config.CONVERSATION_BACKEND: str`, `config.OPENAI_API_KEY: str | None`, `config.OPENAI_REALTIME_MODEL: str`, `config.OPENAI_VOICE: str`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_openai_realtime.py` 신규 생성:

```python
"""Tests for the OpenAI realtime backend (config + handler)."""

from typing import Any

import pytest

from reachy_mini_conversation_app.config import (
    HF_BACKEND,
    OPENAI_BACKEND,
    _normalize_conversation_backend,
    config,
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_openai_realtime.py -v`
Expected: FAIL — `ImportError: cannot import name 'OPENAI_BACKEND'`

- [ ] **Step 3: config.py 구현**

`config.py`의 `HF_REALTIME_SESSION_PROXY_URL` 상수(69행 부근) 바로 아래에 추가:

```python
# --- OpenAI realtime backend (Korean voice baseline) -------------------------
CONVERSATION_BACKEND_ENV = "CONVERSATION_BACKEND"
OPENAI_BACKEND = "openai"
OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"
DEFAULT_OPENAI_REALTIME_MODEL = "gpt-realtime-mini"
DEFAULT_OPENAI_VOICE = "marin"
```

`_normalize_hf_connection_mode` 함수(141행 부근) 아래에 추가:

```python
def _normalize_conversation_backend(value: str | None) -> str:
    """Return the selected conversation backend: Hugging Face (default) or OpenAI."""
    candidate = (value or "").strip().lower()
    if not candidate:
        return HF_BACKEND
    if candidate in {"hf", HF_BACKEND}:
        return HF_BACKEND
    if candidate == OPENAI_BACKEND:
        return OPENAI_BACKEND
    logger.warning(
        "Invalid %s=%r. Expected hf or openai; using hf.",
        CONVERSATION_BACKEND_ENV,
        value,
    )
    return HF_BACKEND
```

`Config` 클래스의 `HF_TOKEN = os.getenv("HF_TOKEN")` 줄(320행 부근) 바로 아래에 추가:

```python
    CONVERSATION_BACKEND = _normalize_conversation_backend(os.getenv(CONVERSATION_BACKEND_ENV))
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_REALTIME_MODEL = (os.getenv("OPENAI_REALTIME_MODEL") or "").strip() or DEFAULT_OPENAI_REALTIME_MODEL
    OPENAI_VOICE = (os.getenv("OPENAI_VOICE") or "").strip() or DEFAULT_OPENAI_VOICE
```

`refresh_runtime_config_from_env()` 함수의 `config.HF_TOKEN = os.getenv("HF_TOKEN")` 줄 아래에 추가:

```python
    config.CONVERSATION_BACKEND = _normalize_conversation_backend(os.getenv(CONVERSATION_BACKEND_ENV))
    config.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    config.OPENAI_REALTIME_MODEL = (os.getenv("OPENAI_REALTIME_MODEL") or "").strip() or DEFAULT_OPENAI_REALTIME_MODEL
    config.OPENAI_VOICE = (os.getenv("OPENAI_VOICE") or "").strip() or DEFAULT_OPENAI_VOICE
```

`.env.example`의 `HF_TOKEN=` 블록 아래에 추가:

```bash
# --- OpenAI backend (Korean voice baseline) ---------------------------------
# Conversation backend: "hf" (default, Hugging Face) or "openai".
# CONVERSATION_BACKEND=openai

# Required when CONVERSATION_BACKEND=openai.
# OPENAI_API_KEY=sk-...

# OpenAI realtime model. Default is the cheaper mini; switch to gpt-realtime for demos.
# OPENAI_REALTIME_MODEL=gpt-realtime-mini

# OpenAI voice: marin (default), cedar, alloy, ash, ballad, coral, echo, sage, shimmer, verse.
# OPENAI_VOICE=marin
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_openai_realtime.py -v`
Expected: PASS (2개 테스트 그룹)

- [ ] **Step 5: 게이트 실행 후 커밋**

```bash
ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v
git add src/reachy_mini_conversation_app/config.py .env.example tests/test_openai_realtime.py
git commit -m "feat: add CONVERSATION_BACKEND and OpenAI realtime settings"
```

---

### Task 2: 리샘플 유틸 + OpenAI 보이스 카탈로그 (openai_realtime.py 뼈대)

**Files:**
- Create: `src/reachy_mini_conversation_app/openai_realtime.py`
- Test: `tests/test_openai_realtime.py` (테스트 추가)

**Interfaces:**
- Consumes: Task 1의 `DEFAULT_OPENAI_VOICE`, `config.OPENAI_VOICE`
- Produces (이후 태스크가 의존):
  - `OPENAI_AVAILABLE_VOICES: list[str]`
  - `OPENAI_TARGET_SAMPLE_RATE: int = 24000`
  - `resample_pcm(audio: NDArray[np.int16], source_rate: int, target_rate: int) -> NDArray[np.int16]`
  - `_default_openai_voice() -> str`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_openai_realtime.py`에 추가:

```python
import numpy as np


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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_openai_realtime.py -v -k "resample or default_openai_voice"`
Expected: FAIL — `ModuleNotFoundError: No module named 'reachy_mini_conversation_app.openai_realtime'`

- [ ] **Step 3: openai_realtime.py 뼈대 구현**

`src/reachy_mini_conversation_app/openai_realtime.py` 신규 생성:

```python
"""OpenAI Realtime API backend: a thin subclass of the Hugging Face handler.

Only the Hugging Face-specific attachment points are overridden (client/auth,
24 kHz audio format, voice catalog, model selection). The conversation loop,
tool plumbing, and idle policy are inherited unchanged.
"""

import base64
import logging
from typing import Tuple

import numpy as np
from numpy.typing import NDArray
from openai import AsyncOpenAI
from openai.types.realtime import (
    RealtimeAudioConfigParam,
    RealtimeAudioConfigOutputParam,
    RealtimeSessionCreateRequestParam,
)

from reachy_mini_conversation_app.config import (
    DEFAULT_OPENAI_VOICE,
    OPENAI_REALTIME_URL,
    config,
    get_session_voice,
)
from reachy_mini_conversation_app.streaming import audio_to_int16
from reachy_mini_conversation_app.huggingface_realtime import (
    HuggingFaceRealtimeHandler,
    _build_openai_compatible_client_from_realtime_url,
)
from reachy_mini_conversation_app.tools.core_tools import ToolSpec

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
```

(참고: `ToolSpec`·`RealtimeAudioConfigParam` 등 아직 안 쓰는 import는 Task 3·4에서 사용된다. ruff가 미사용 import를 지적하면 이 태스크에서는 해당 import를 빼고 Task 3·4에서 추가해도 된다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_openai_realtime.py -v`
Expected: PASS

- [ ] **Step 5: 게이트 실행 후 커밋**

```bash
ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v
git add src/reachy_mini_conversation_app/openai_realtime.py tests/test_openai_realtime.py
git commit -m "feat: add OpenAI voice catalog and PCM resampling helpers"
```

---

### Task 3: OpenAIRealtimeHandler — 클라이언트 생성과 24 kHz 세션 설정

**Files:**
- Modify: `src/reachy_mini_conversation_app/openai_realtime.py`
- Test: `tests/test_openai_realtime.py` (테스트 추가)

**Interfaces:**
- Consumes:
  - 부모 `HuggingFaceRealtimeHandler._build_realtime_client(self) -> AsyncOpenAI` / `_get_session_config(self, tool_specs: list[ToolSpec]) -> RealtimeSessionCreateRequestParam` / `self._realtime_connect_query: dict[str, str]`
  - `_build_openai_compatible_client_from_realtime_url(realtime_url: str, bearer_token: str | None) -> tuple[AsyncOpenAI, dict[str, str]]` (hf 모듈, AsyncOpenAI 심볼은 hf 모듈 것을 사용하므로 테스트에서 `hf_mod.AsyncOpenAI`를 patch)
- Produces: `OpenAIRealtimeHandler(deps, instance_path=None, startup_voice=None)` — Task 5의 팩토리가 사용

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_openai_realtime.py`에 추가 (파일 상단 import에 `MagicMock`, `hf_mod`, `ToolDependencies` 추가):

```python
from unittest.mock import MagicMock

import reachy_mini_conversation_app.huggingface_realtime as hf_mod
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies


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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_openai_realtime.py -v -k "build_realtime_client or session_config"`
Expected: FAIL — `ImportError: cannot import name 'OpenAIRealtimeHandler'`

- [ ] **Step 3: 핸들러 구현 (클라이언트 + 세션)**

`openai_realtime.py`에 추가:

```python
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
        session["audio"]["input"]["format"] = pcm_24k  # type: ignore[index,typeddict-item]
        session["audio"]["output"]["format"] = pcm_24k  # type: ignore[index,typeddict-item]
        return session
```

구현 노트:
- `_build_openai_compatible_client_from_realtime_url`은 URL 쿼리에서 `model`을 제거하므로(HF 정책), 모델은 반드시 반환된 `connect_query`에 **직접** 넣는다. 부모의 `_run_realtime_session`이 이 dict를 `client.realtime.connect(extra_query=...)`로 전달해 웹소켓 URL 쿼리에 실린다.
- `session["audio"]` 인덱싱에서 mypy가 TypedDict 오류를 내면 위처럼 `# type: ignore` 주석으로 처리한다 (부모 코드도 같은 패턴 사용, huggingface_realtime.py:231 참고).
- 이 시점에는 `get_current_voice`를 아직 오버라이드하지 않았으므로 `session["audio"]["output"]["voice"]` 검증은 Step 4에서 실패할 수 있다 → 그 경우 voice 검증 한 줄은 Task 4 완료 후 통과된다. **Task 4까지 끝낸 뒤 전체 테스트를 다시 돌려 최종 확인한다.** (Task 3 단계에서는 `-k "build_realtime_client"`만 통과해도 진행 가능)

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_openai_realtime.py -v -k "build_realtime_client"`
Expected: PASS (session_config의 voice 검증은 Task 4에서 완전 통과)

- [ ] **Step 5: 커밋**

```bash
ruff check . --fix && ruff format . && mypy --pretty --show-error-codes
git add src/reachy_mini_conversation_app/openai_realtime.py tests/test_openai_realtime.py
git commit -m "feat: add OpenAIRealtimeHandler client and 24kHz session config"
```

---

### Task 4: 보이스 메서드 + 마이크 리샘플 receive 오버라이드

**Files:**
- Modify: `src/reachy_mini_conversation_app/openai_realtime.py`
- Test: `tests/test_openai_realtime.py` (테스트 추가)

**Interfaces:**
- Consumes: 부모의 `_resolve_backend_voice(self, voice: str | None, *, source: str, fallback: str | None = None) -> str | None` 시그니처 (동일 시그니처로 오버라이드), `self._voice_override`, `self.connection`, `resample_pcm` (Task 2)
- Produces: UI 보이스 선택·프로필 보이스·마이크 입력이 OpenAI 백엔드에서 완전 동작

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_openai_realtime.py`에 추가:

```python
import base64


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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_openai_realtime.py -v -k "voice or receive"`
Expected: FAIL — `get_current_voice`가 HF 카탈로그 기준으로 동작 (`cedar` 미지원 → HF 기본 보이스 반환), `receive`는 리샘플 없이 1600 샘플 전송

- [ ] **Step 3: 보이스 메서드 + receive 구현**

`OpenAIRealtimeHandler` 클래스에 추가:

```python
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
```

구현 노트:
- 부모의 `_normalize_startup_voice`는 `self._resolve_backend_voice`를 호출하므로 오버라이드 불필요 — 인스턴스 디스패치로 우리 카탈로그가 적용된다.
- `get_session_voice`는 프로필이 지정한 보이스를 읽는다. HF 전용 보이스(예: Aiden)가 프로필에 있으면 `_resolve_backend_voice`가 경고 후 `marin`으로 폴백한다.
- 출력 오디오는 오버라이드 불필요: 부모의 delta 처리(huggingface_realtime.py:849-854)가 `self.SAMPLE_RATE`(=24000)를 output_queue 튜플에 실어 재생 계층이 그대로 처리한다.

- [ ] **Step 4: 전체 테스트 통과 확인 (Task 3의 session voice 검증 포함)**

Run: `pytest tests/test_openai_realtime.py tests/test_huggingface_realtime.py -v`
Expected: 전부 PASS — HF 테스트가 그대로 통과하는지 반드시 확인 (회귀 없음 검증)

- [ ] **Step 5: 게이트 실행 후 커밋**

```bash
ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v
git add src/reachy_mini_conversation_app/openai_realtime.py tests/test_openai_realtime.py
git commit -m "feat: OpenAI voice catalog integration and 24kHz mic resampling"
```

---

### Task 5: main.py 핸들러 팩토리 분기

**Files:**
- Modify: `src/reachy_mini_conversation_app/main.py` (`build_handler` 내부 함수, 167행 부근)
- Test: 수동 검증 (팩토리는 `main()` 내부 클로저라 유닛 테스트 대상에서 제외; 키 검증은 Task 3의 `_build_realtime_client` 테스트가 커버)

**Interfaces:**
- Consumes: Task 3·4의 `OpenAIRealtimeHandler`, Task 1의 `config.CONVERSATION_BACKEND` / `OPENAI_BACKEND`
- Produces: `CONVERSATION_BACKEND=openai` 설정 시 앱 전체가 OpenAI 백엔드로 기동

- [ ] **Step 1: build_handler 분기 추가**

`main.py`의 `build_handler` 함수를 다음으로 교체 (기존 HF 경로는 그대로 유지):

```python
    def build_handler(startup_voice: Optional[str] = None) -> ConversationHandler:
        """Build the realtime conversation handler for the configured backend."""
        if config.CONVERSATION_BACKEND == OPENAI_BACKEND:
            from reachy_mini_conversation_app.openai_realtime import OpenAIRealtimeHandler

            if not (config.OPENAI_API_KEY or "").strip():
                logger.error(
                    "CONVERSATION_BACKEND=openai requires OPENAI_API_KEY. "
                    "Set it in the environment or .env and restart."
                )
                sys.exit(1)
            logger.info("Using OpenAI realtime handler (model=%s)", config.OPENAI_REALTIME_MODEL)
            return OpenAIRealtimeHandler(
                deps,
                instance_path=instance_path,
                startup_voice=startup_voice,
            )

        from reachy_mini_conversation_app.huggingface_realtime import HuggingFaceRealtimeHandler

        hf_connection_selection = get_hf_connection_selection()
        transport_label = (
            "Hugging Face direct websocket"
            if hf_connection_selection.mode == HF_LOCAL_CONNECTION_MODE and hf_connection_selection.has_target
            else "Hugging Face session proxy"
        )
        logger.info("Using Hugging Face realtime handler (%s)", transport_label)
        return HuggingFaceRealtimeHandler(
            deps,
            instance_path=instance_path,
            startup_voice=startup_voice,
        )
```

`main.py` 상단의 `from reachy_mini_conversation_app.config import (...)` 블록에 `config`와 `OPENAI_BACKEND`를 추가한다 (이미 있는 심볼은 중복 추가하지 않는다). `sys`는 main.py에서 이미 import되어 있다 (sys.exit 사용 중, 144행 참고).

- [ ] **Step 2: 게이트 실행**

Run: `ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v`
Expected: 전부 PASS

- [ ] **Step 3: 수동 스모크 — 백엔드 미설정 시 HF 경로 유지 확인**

Run: `grep -n "CONVERSATION_BACKEND" .env 2>/dev/null; echo exit=$?`
`.env`에 `CONVERSATION_BACKEND`가 없거나 주석 상태인지 확인. 이후 시뮬 환경이 있으면 `reachy-mini-conversation-app` 기동 로그에 "Using Hugging Face realtime handler"가 그대로 나오는지 확인 (회귀 없음).

- [ ] **Step 4: 커밋**

```bash
git add src/reachy_mini_conversation_app/main.py
git commit -m "feat: select conversation backend from CONVERSATION_BACKEND"
```

---

### Task 6: 한국어 데스크 컴패니언 프로필 + 한국어 프리셋 안내

**Files:**
- Create: `profiles/desk_companion_ko/profile.md`
- Modify: `.env.example` (한국어 프리셋 주석 추가)
- Test: `tests/test_openai_realtime.py` (프로필 존재·형식 검증 추가)

**Interfaces:**
- Consumes: 프로필 스키마 — `+++` TOML frontmatter (`schema_version = 1`, `default_tools = [...]`), 본문은 시스템 프롬프트 (`profiles/default/profile.md` 참고, upstream #484 형식)
- Produces: `REACHY_MINI_CUSTOM_PROFILE=desk_companion_ko`로 선택 가능한 한국어 페르소나

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_openai_realtime.py`에 추가:

```python
from reachy_mini_conversation_app.config import DEFAULT_PROFILES_DIRECTORY


def test_desk_companion_ko_profile_exists_and_speaks_korean() -> None:
    """The Korean desk companion profile must exist in the new profile.md format."""
    profile_path = DEFAULT_PROFILES_DIRECTORY / "desk_companion_ko" / "profile.md"
    assert profile_path.is_file()

    content = profile_path.read_text(encoding="utf-8")
    assert content.startswith("+++")
    assert "schema_version = 1" in content
    assert "한국어" in content
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_openai_realtime.py -v -k desk_companion`
Expected: FAIL — `assert profile_path.is_file()` 실패

- [ ] **Step 3: 프로필 작성**

`profiles/desk_companion_ko/profile.md` 신규 생성 (UTF-8, `$env:PYTHONUTF8="1"` 환경에서 작업):

```markdown
+++
schema_version = 1
default_tools = [
  "dance",
  "stop_dance",
  "play_emotion",
  "stop_emotion",
  "camera",
  "idle_do_nothing",
  "move_head",
  "go_to_sleep",
  "sweep_look",
  "remember",
  "forget",
  "head_tracking",
  "pollen_robotics_reachy_mini_weather_tool__get_weather",
  "pollen_robotics_reachy_mini_time_tool__get_time",
]
+++

## 정체성
너는 Reachy Mini: 책상 위에서 함께 일하는 작고 다정한 로봇 동반자다.
성격: 차분하고 따뜻하며, 가끔 가벼운 유머를 곁들인다. 과장하지 않는다.

## 핵심 응답 규칙
- 항상 한국어로만 대답한다. 사용자가 명시적으로 다른 언어를 요청할 때만 예외로 한다.
- 기본 말투는 부드러운 존댓말(해요체)이다.
- 최대 1~2문장으로 짧게 대답한다. 음성으로 듣기 좋은 길이를 유지한다.
- 숫자·시간·날짜는 한국어 낭독에 자연스러운 형태로 말한다 (예: "오후 세 시 반").

## 행동
- 대화 내용과 감정에 맞춰 움직임·감정 표현 도구를 자연스럽게 사용한다.
- 사용자를 바라보고 반응하되, 요청받지 않은 긴 설명은 하지 않는다.
- 잘 모르는 것은 모른다고 솔직하게 말한다.
```

- [ ] **Step 4: .env.example에 한국어 프리셋 주석 추가**

Task 1에서 추가한 OpenAI 블록 끝에 덧붙인다:

```bash
# Korean demo preset: uncomment the three lines below together.
# CONVERSATION_BACKEND=openai
# REALTIME_TRANSCRIPTION_LANGUAGE=ko
# REACHY_MINI_CUSTOM_PROFILE=desk_companion_ko
```

(중복을 피하려면 Task 1의 `# CONVERSATION_BACKEND=openai` 예시 줄과 합쳐 하나의 프리셋 블록으로 정리해도 된다.)

- [ ] **Step 5: 테스트 통과 확인 후 커밋**

Run: `pytest tests/test_openai_realtime.py -v`
Expected: PASS

```bash
ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v
git add profiles/desk_companion_ko/profile.md .env.example tests/test_openai_realtime.py
git commit -m "feat: add Korean desk companion profile and demo preset"
```

---

### Task 7: 최종 게이트 + 수동 한국어 대화 검증

**Files:**
- 변경 없음 (검증 전용)

**Interfaces:**
- Consumes: Task 1~6 전체

- [ ] **Step 1: 전체 게이트 실행**

Run: `ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v`
Expected: 전부 PASS. 실패 시 해당 태스크로 돌아가 수정 후 재실행.

- [ ] **Step 2: 수동 한국어 대화 체크리스트 (시뮬 + 실제 API 키 필요)**

`.env`에 실제 키로 설정:

```bash
CONVERSATION_BACKEND=openai
OPENAI_API_KEY=sk-<실제 키>
REALTIME_TRANSCRIPTION_LANGUAGE=ko
REACHY_MINI_CUSTOM_PROFILE=desk_companion_ko
```

MuJoCo 시뮬 데몬 기동 후 `reachy-mini-conversation-app` 실행, 아래를 순서대로 확인:

1. 기동 로그에 `Using OpenAI realtime handler (model=gpt-realtime-mini)` 출력
2. "안녕, 리치야" → 한국어 존댓말 1~2문장 응답, 음성 자연스러움
3. "고개 들어봐" → `move_head` 도구 호출 로그 + 시뮬에서 머리 움직임
4. 로봇이 말하는 도중 말 끊기 → 응답 중단(인터럽트) 동작
5. 전사 로그에 한국어가 깨지지 않고 표기 (Windows에서는 `$env:PYTHONUTF8="1"` 설정)
6. `.env`에서 `CONVERSATION_BACKEND` 제거 후 재기동 → `Using Hugging Face realtime handler` 로그로 복귀 (회귀 없음)

- [ ] **Step 3: 검증 결과 기록 후 push**

수동 체크 결과(통과/이슈)를 PR 본문 또는 커밋 메시지에 기록:

```bash
git push -u origin feat/openai-korean-voice-baseline
```

(브랜치 전략: 이 계획의 작업은 `develop`에서 분기한 `feat/openai-korean-voice-baseline` 브랜치에서 진행하고, 완료 후 fork의 `develop`으로 PR을 올린다 — 팀 규칙 준수.)

---

## Self-Review 결과

- **스펙 커버리지**: 설정 4개(Task 1), 오버라이드 4지점(Task 3·4), 팩토리·키 검증(Task 5), 한국어 프로필(Task 6), 성공 기준 3항(Task 7 체크리스트) — 스펙 전 항목에 대응 태스크 존재
- **타입 일관성**: `_resolve_backend_voice` 시그니처는 부모(huggingface_realtime.py:195-201)와 동일하게 유지, `resample_pcm`·`OPENAI_AVAILABLE_VOICES`는 Task 2 정의를 Task 4가 동일 이름으로 사용
- **placeholder 없음**: 전 태스크 실제 코드 포함
