# 데몬 연결 대상 .env 설정 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.env`의 `REACHY_MINI_HOST`/`REACHY_MINI_PORT`로 실물 로봇(예: 192.168.0.144)·시뮬레이터 연결 대상을 선택한다.

**Architecture:** `config.py`에 순수 함수 `resolve_daemon_connection()`으로 env 값 → `ReachyMini(...)` kwargs 매핑을 두고, `main.py`의 robot 초기화에서 반영한다. SDK가 이미 `host`/`port`/`connection_mode`를 지원하므로 신규 연결 로직은 없다.

**Tech Stack:** Python 3.10+, reachy-mini SDK (기존 의존성)

**Spec:** [`oss_plan/2026-08-01-daemon-connection-env-design.md`](2026-08-01-daemon-connection-env-design.md)

## Global Constraints

- 신규 pip 의존성 금지; `huggingface_realtime.py` 수정 금지
- 게이트: `ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v`
- 테스트는 실제 로봇/데몬 연결 금지 (순수 함수만 테스트)

---

### Task 1: resolve_daemon_connection + main.py 반영 + .env.example

**Files:**
- Modify: `src/reachy_mini_conversation_app/config.py`
- Modify: `src/reachy_mini_conversation_app/main.py` (robot 초기화, 142-150행 부근)
- Modify: `.env.example`
- Test: `tests/test_daemon_connection.py` (신규)

**Interfaces:**
- Consumes: SDK `ReachyMini(host="reachy-mini.local", port=8000, connection_mode="auto"|"localhost_only"|"network")`
- Produces: `DaemonConnection(host: str | None, port: int, connection_mode: str | None)`, `resolve_daemon_connection(host_value: str | None, port_value: str | None) -> DaemonConnection`, `config.REACHY_MINI_HOST`, `config.REACHY_MINI_PORT`, `DEFAULT_DAEMON_PORT = 8000`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_daemon_connection.py` 신규:

```python
"""Tests for REACHY_MINI_HOST/PORT daemon connection resolution."""

import pytest

from reachy_mini_conversation_app.config import (
    DEFAULT_DAEMON_PORT,
    DaemonConnection,
    resolve_daemon_connection,
)


@pytest.mark.parametrize("host_value", [None, "", "   "])
def test_unset_host_keeps_sdk_auto(host_value: str | None) -> None:
    """No REACHY_MINI_HOST keeps the SDK's auto connection behavior."""
    result = resolve_daemon_connection(host_value, None)
    assert result == DaemonConnection(host=None, port=DEFAULT_DAEMON_PORT, connection_mode=None)


@pytest.mark.parametrize("host_value", ["sim", "SIM", "localhost", "127.0.0.1"])
def test_local_aliases_force_localhost_only(host_value: str) -> None:
    """sim/localhost aliases must never fall back to a network robot."""
    result = resolve_daemon_connection(host_value, None)
    assert result.connection_mode == "localhost_only"
    assert result.host is None


def test_ip_host_uses_network_mode() -> None:
    """An IP/hostname targets the remote daemon explicitly."""
    result = resolve_daemon_connection("192.168.0.144", "8000")
    assert result == DaemonConnection(host="192.168.0.144", port=8000, connection_mode="network")


@pytest.mark.parametrize("port_value", ["abc", "-1", "0", "70000"])
def test_invalid_port_falls_back_to_default(port_value: str) -> None:
    """Bad port values warn and fall back instead of blocking startup."""
    result = resolve_daemon_connection("192.168.0.144", port_value)
    assert result.port == DEFAULT_DAEMON_PORT


def test_custom_port_is_used() -> None:
    """A valid custom port is honored."""
    assert resolve_daemon_connection("sim", "8123").port == 8123
```

- [ ] **Step 2: 실패 확인**

Run: `pytest tests/test_daemon_connection.py -v`
Expected: FAIL — `ImportError: cannot import name 'DaemonConnection'`

- [ ] **Step 3: config.py 구현**

OpenAI 백엔드 상수 블록 아래에 추가:

```python
# --- Robot daemon connection target ------------------------------------------
REACHY_MINI_HOST_ENV = "REACHY_MINI_HOST"
REACHY_MINI_PORT_ENV = "REACHY_MINI_PORT"
DEFAULT_DAEMON_PORT = 8000
_LOCAL_DAEMON_HOST_ALIASES = {"sim", "localhost", "127.0.0.1"}


@dataclass(frozen=True)
class DaemonConnection:
    """Resolved robot daemon connection target for ReachyMini(...) kwargs."""

    host: str | None
    port: int
    connection_mode: str | None  # None -> keep the SDK default ("auto")


def resolve_daemon_connection(host_value: str | None, port_value: str | None) -> DaemonConnection:
    """Map REACHY_MINI_HOST/REACHY_MINI_PORT values onto ReachyMini connection kwargs."""
    port = DEFAULT_DAEMON_PORT
    raw_port = (port_value or "").strip()
    if raw_port:
        try:
            parsed_port = int(raw_port)
        except ValueError:
            parsed_port = -1
        if 0 < parsed_port < 65536:
            port = parsed_port
        else:
            logger.warning("Invalid %s=%r; using %d.", REACHY_MINI_PORT_ENV, port_value, DEFAULT_DAEMON_PORT)

    host = (host_value or "").strip()
    if not host:
        return DaemonConnection(host=None, port=port, connection_mode=None)
    if host.lower() in _LOCAL_DAEMON_HOST_ALIASES:
        return DaemonConnection(host=None, port=port, connection_mode="localhost_only")
    return DaemonConnection(host=host, port=port, connection_mode="network")
```

`Config` 클래스의 `OPENAI_VOICE = ...` 줄 아래에 추가:

```python
    REACHY_MINI_HOST = os.getenv(REACHY_MINI_HOST_ENV)
    REACHY_MINI_PORT = os.getenv(REACHY_MINI_PORT_ENV)
```

`refresh_runtime_config_from_env()`의 OpenAI 갱신 줄 아래에 추가:

```python
    config.REACHY_MINI_HOST = os.getenv(REACHY_MINI_HOST_ENV)
    config.REACHY_MINI_PORT = os.getenv(REACHY_MINI_PORT_ENV)
```

- [ ] **Step 4: main.py 반영**

`from reachy_mini_conversation_app.config import (...)` 블록에 `resolve_daemon_connection` 추가.
robot 초기화의 `robot_kwargs` 구성(142-150행 부근)을 다음으로 교체:

```python
            robot_kwargs: dict[str, Any] = {}
            if args.robot_name is not None:
                robot_kwargs["robot_name"] = args.robot_name

            daemon_connection = resolve_daemon_connection(config.REACHY_MINI_HOST, config.REACHY_MINI_PORT)
            if daemon_connection.connection_mode is not None:
                robot_kwargs["connection_mode"] = daemon_connection.connection_mode
            if daemon_connection.host is not None:
                robot_kwargs["host"] = daemon_connection.host
            robot_kwargs["port"] = daemon_connection.port
            logger.info(
                "Connecting to Reachy Mini daemon (%s, %s:%d)",
                daemon_connection.connection_mode or "auto",
                daemon_connection.host or "localhost",
                daemon_connection.port,
            )
            robot = ReachyMini(**robot_kwargs)
```

(`Any`가 main.py에 import되어 있지 않으면 typing import에 추가. 기존
`logger.info("Initializing ReachyMini (SDK will auto-detect appropriate backend)")` 줄은 위 로그로 대체.)

- [ ] **Step 5: .env.example 추가**

한국어 프리셋 블록 아래에 추가:

```bash
# --- Robot daemon connection --------------------------------------------------
# Unset: SDK auto mode (tries localhost first, then reachy-mini.local fallback).
# Simulator / local daemon only (never falls back to a network robot):
# REACHY_MINI_HOST=sim
# Real robot on your network:
# REACHY_MINI_HOST=192.168.0.144
# REACHY_MINI_PORT=8000
```

- [ ] **Step 6: 테스트 통과 + 게이트 + 커밋**

Run: `pytest tests/test_daemon_connection.py -v` → 전부 PASS
Run: `ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v` → 전부 PASS

```bash
git add src/reachy_mini_conversation_app/config.py src/reachy_mini_conversation_app/main.py .env.example tests/test_daemon_connection.py
git commit -m "feat: select robot daemon target via REACHY_MINI_HOST/PORT"
```

---

## Self-Review 결과

- 스펙 커버리지: 표의 3개 케이스(미설정/sim·localhost/IP) + 포트 폴백 + 로그 + .env.example — 전부 Task 1에 포함
- placeholder 없음, 타입 일관성 확인 (`DaemonConnection` 필드명·시그니처 테스트와 일치)
