# 종료 시 슬립 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ctrl+C(Windows에서는 Ctrl+Break 포함)로 앱을 종료하면 로봇이 취침 모션 후 잠든 채 종료된다 (기본 켜짐, `REACHY_MINI_SLEEP_ON_EXIT=0`으로 끄기).

**Architecture:** `main.py`의 KeyboardInterrupt 경로에서만 기존 `run_go_to_sleep_tool()`을 재사용해 음성 도구와 동일한 취침 시퀀스를 실행. 외부 중지(`app_stop_event`)는 upstream 동작 유지. `signal.SIGBREAK` 핸들러로 Windows Ctrl+Break·콘솔 종료도 같은 경로로 합류.

**Spec:** [`oss_plan/2026-08-01-sleep-on-exit-design.md`](2026-08-01-sleep-on-exit-design.md)

## Global Constraints

- 신규 pip 의존성 금지; `huggingface_realtime.py` 수정 금지
- 게이트: `ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v`

---

### Task 1: config 플래그 + main.py 종료 경로 + 라이브 검증

**Files:**
- Modify: `src/reachy_mini_conversation_app/config.py` (`REACHY_MINI_SLEEP_ON_EXIT` `_env_flag(default=True)` + refresh)
- Modify: `src/reachy_mini_conversation_app/main.py` (SIGBREAK 핸들러, keyboard_interrupted 추적, finally 선두에서 조건부 `run_go_to_sleep_tool()`)
- Modify: `.env.example` (연결 블록에 주석 한 줄)
- Test: `tests/test_sleep_on_exit.py` (신규 — 플래그 기본값 True·`0` 끄기, refresh 라운드트립; 테스트 후 config 복원)

**Steps:**
- [ ] 실패하는 테스트 → 실패 확인 → 구현 → 게이트 → 커밋
- [ ] 라이브 검증: 실물 로봇에서 앱 기동 후 CTRL_BREAK_EVENT 전송(드라이버 스크립트, CREATE_NEW_PROCESS_GROUP) → "Sleep-on-exit" 로그 + 취침 모션 확인
