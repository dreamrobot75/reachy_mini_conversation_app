# 슬립 대기↔대화 반복 루프 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 음성 "종료해 줘" → 슬립 대기(세션 유지·전사만), 웨이크 문구("깨어나/리치미니/일어나") → 기상·인사·대화 재개가 무한 반복된다. Ctrl+C만 진짜 종료.

**Architecture:** `OpenAIRealtimeHandler`에 standby 상태 머신(부모 무수정): `enter_standby()`가 취침 모션 + `ServerVad(create_response=False)`로 전사 전용 전환, `_emit_transcript` 오버라이드가 웨이크 문구를 감지해 `wake_from_standby()`(모션 재시작→기상 모션→VAD 복원→인사). `main.py`는 `deps.go_to_sleep`을 standby 콜백으로 분기.

**Spec:** [`oss_plan/2026-08-01-standby-wake-loop-design.md`](2026-08-01-standby-wake-loop-design.md)

## Global Constraints

- 신규 pip 의존성 금지; `huggingface_realtime.py`·`conversation_handler.py` 수정 금지
- 게이트: `ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v`
- 테스트는 실제 API·로봇 호출 금지 (fake connection·MagicMock)

---

### Task 1: 웨이크 매처 + standby 상태 머신 (openai_realtime.py) + config

**Files:**
- Modify: `src/reachy_mini_conversation_app/openai_realtime.py`
- Modify: `src/reachy_mini_conversation_app/config.py` (`REACHY_MINI_STANDBY_ON_SLEEP` `_env_flag(default=True)`, `REACHY_MINI_WAKE_PHRASES` raw str + refresh)
- Test: `tests/test_standby.py` (신규)

**Interfaces (Task 2가 의존):**
- `matches_wake_phrase(transcript: str, phrases: Sequence[str]) -> bool` — 공백·비단어문자 제거, 소문자 부분 일치
- `configured_wake_phrases() -> list[str]` — env 파싱, 기본 `["깨어나", "리치미니", "일어나"]`
- `OpenAIRealtimeHandler.request_standby() -> dict` (sync, 도구 스레드에서 호출; `run_coroutine_threadsafe`)
- `OpenAIRealtimeHandler.in_standby: bool` (property)
- async `enter_standby()` / `wake_from_standby()`; `_standby_loop`는 `_build_realtime_client`에서 저장
- `_idle_behavior_ready()` — standby 중 False

**Steps:**
- [ ] 실패 테스트: 매처 변형(공백/문장 포함/불일치/빈값), env 문구 파싱, enter_standby 후 `session.update`에 `create_response=False`·`_standby=True`·goto_sleep 호출, `_idle_behavior_ready()` False, wake_from_standby 후 복원·enable_motors/wake_up·인사 item 생성, `_emit_transcript`("user", 웨이크문구, True)가 wake 트리거(AsyncMock)
- [ ] 실패 확인 → 구현 → 통과 → 게이트 → 커밋 `feat: standby state machine with transcript wake phrases`

### Task 2: main.py wiring + Ctrl+C 상호작용 + .env.example + 라이브 검증

**Files:**
- Modify: `src/reachy_mini_conversation_app/main.py`
- Modify: `.env.example`

**Steps:**
- [ ] `deps.go_to_sleep` 분기: `config.REACHY_MINI_STANDBY_ON_SLEEP`이고 활성 핸들러에 `request_standby`가 있으면 standby, 아니면 기존 `go_to_sleep_and_stop_app` (HF 폴백). 활성 핸들러는 호출 시점에 `stream_manager.handler`로 해석 (UI 재빌드 대응)
- [ ] sleep-on-exit 가드에 `in_standby` 추가 (standby 중 Ctrl+C면 취침 모션 생략)
- [ ] `.env.example`: 두 설정 + 대기 중 과금 주의 주석
- [ ] 게이트 → 커밋 `feat: route voice sleep to standby wake loop`
- [ ] 라이브 검증(실물): 실행 → 대화 → "종료해 줘" → 취침·대기 확인 → "깨어나 리치미니" → 기상·인사 → 재대화 → Ctrl+C 종료(취침 모션 생략 확인)
