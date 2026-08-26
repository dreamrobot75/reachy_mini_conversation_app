# 원격 데몬 자동 시작 (opt-in) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `REACHY_MINI_AUTO_START_DAEMON=1`일 때, network 모드 연결 전에 원격 데몬 백엔드가 `stopped`면 자동으로 시작한다 (기본은 꺼짐 — 모터 기동은 물리 동작이므로 opt-in).

**Architecture:** 신규 모듈 `daemon_autostart.py`에 httpx 기반 순수 로직(상태 조회 → start POST → running 폴링)을 두고, `main.py`의 network 연결 직전에 호출한다. 자동 시작이 꺼져 있고 데몬이 stopped면 해결 방법을 안내하는 경고 로그만 남기고 기존 흐름(연결 시도 → 실패 시 기존 에러)을 유지한다.

**Tech Stack:** httpx (기존 의존성), 데몬 API `GET /api/daemon/status` · `POST /api/daemon/start?wake_up=false`

## Global Constraints

- 신규 pip 의존성 금지; `huggingface_realtime.py` 수정 금지
- 게이트: `ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v`
- 테스트는 실제 로봇/네트워크 호출 금지 (httpx monkeypatch)

---

### Task 1: daemon_autostart 모듈 + config 플래그 + main.py 연동

**Files:**
- Create: `src/reachy_mini_conversation_app/daemon_autostart.py`
- Modify: `src/reachy_mini_conversation_app/config.py` (`REACHY_MINI_AUTO_START_DAEMON` `_env_flag`, refresh 포함)
- Modify: `src/reachy_mini_conversation_app/main.py` (network 모드일 때 연결 전 호출)
- Modify: `.env.example` (연결 블록에 한 줄 추가)
- Test: `tests/test_daemon_autostart.py` (신규)

**Interfaces:**
- Produces: `get_daemon_state(host: str, port: int) -> str | None`,
  `ensure_remote_daemon_running(host: str, port: int, *, auto_start: bool, start_timeout_s: float = 45.0) -> str`
  (반환: "running" | "stopped" | "timeout" | "unknown" | 기타 데몬 state 문자열),
  `config.REACHY_MINI_AUTO_START_DAEMON: bool` (기본 False)
- 실패는 절대 raise하지 않는다 — 로그 후 상태 문자열 반환 (연결 시도는 기존 흐름이 담당)

- [ ] Step 1: 실패하는 테스트 작성 (httpx monkeypatch로 running/stopped/opt-out/자동시작 성공/타임아웃/unreachable 케이스)
- [ ] Step 2: 실패 확인 → Step 3: 모듈·config·main.py 구현 → Step 4: .env.example → Step 5: 게이트 → 커밋
- [ ] Step 6: 실물 로봇으로 라이브 검증 — 데몬 stop 후 `REACHY_MINI_AUTO_START_DAEMON=1`로 앱 실행, 자동 시작·연결 확인

(코드 상세는 구현 시 이 계획을 실행하는 세션이 테스트와 함께 작성 — 함수 시그니처·반환 계약은 위 Interfaces가 기준)
