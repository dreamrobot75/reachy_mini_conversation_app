# 뽀모도로 타이머 도구 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `pomodoro_timer` LLM 도구로 집중/휴식 단계 타이머를 배경 실행하고, 완료 시 모델이 다음 단계(자동 휴식 전환·세트 확인)를 이어가게 한다.

**Architecture:** `tools/pomodoro.py` 단일 파일 도구. 취소 가능한 `asyncio.sleep` 본체 — 장기 실행·취소·상태는 기존 BackgroundToolManager/task_cancel/task_status가 처리(신규 인프라 없음). 완료 반환 dict의 `next_action` 지시로 모델이 단계를 연결. `desk_companion_ko` 프로필에 도구·사용 규칙 추가.

**Spec:** [`oss_plan/2026-08-01-pomodoro-tool-design.md`](2026-08-01-pomodoro-tool-design.md)

## Global Constraints

- 신규 pip 의존성 금지; upstream 파일(`background_tool_manager.py`, `core_tools.py` 등) 수정 금지
- 게이트: `ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v`
- 실패는 raise 대신 `{"error": ...}` 반환; `asyncio.CancelledError`는 전파 (CLAUDE.md 도구 규칙)

---

### Task 1: pomodoro.py + 프로필 + 테스트 (단일 태스크)

**Files:**
- Create: `src/reachy_mini_conversation_app/tools/pomodoro.py`
- Modify: `profiles/desk_companion_ko/profile.md` (default_tools + 집중 모드 규칙 섹션)
- Test: `tests/test_pomodoro.py` (신규)

**Interfaces:**
- `PomodoroTimer(Tool)`: `name="pomodoro_timer"`, `parameters_schema`: phase(str, enum focus|break, required) / minutes(number) / cycle(integer) / total_cycles(integer)
- 반환: `{"status": "focus_complete"|"break_complete"|"pomodoro_done", "cycle": int, "total_cycles": int, "minutes": int, "next_action": str}` 또는 `{"error": str}`
- 상수: `DEFAULT_FOCUS_MINUTES=25`, `DEFAULT_BREAK_MINUTES=5`, `MIN_MINUTES=1`, `MAX_MINUTES=120`

**Steps:**
- [ ] 실패 테스트: focus 완료 시 next_action에 break 자동 시작 지시, break 중간 세트(확인 지시)/마지막 세트(축하 지시) 분기, 기본값(25/5)·클램프(0→1, 999→120), phase 오류 → error dict, `asyncio.sleep` CancelledError 전파, 프로필 default_tools에 pomodoro_timer 포함
- [ ] 실패 확인 → 구현(go_to_sleep 도구 파일 패턴 준수) → 통과 → 게이트 → 커밋 `feat: pomodoro timer tool with auto break transition`
- [ ] 라이브 검증(실물): "1분 뽀모도로 시작해 줘" → 시작 발화 → 1분 후 완료 알림 + 휴식 타이머 자동 시작 → 휴식 완료 확인 질문
