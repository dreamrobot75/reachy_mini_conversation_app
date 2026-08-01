# 뽀모도로 타이머 도구 — 설계 문서

- **작성일**: 2026-08-01
- **상태**: 설계 승인됨 (집중↔휴식 자동 전환, 세트 반복은 사용자 확인)

## 동작

```
"뽀모도로 시작" → pomodoro_timer(phase=focus, minutes=25, cycle=1, total_cycles=N)
  완료 → 모델이 알리고 즉시 phase=break 타이머 시작 (자동)
  break 완료 → 세트 남음: "다음 세트 시작할까요?" 확인 / 마지막: 축하
중단·잔여 확인은 기존 task_cancel / task_status 도구가 담당.
```

기본값 집중 25분·휴식 5분, 음성으로 변경 가능("10분만 집중"). 분은 1~120 클램프.

## 구현

### tools/pomodoro.py (신규) — 파일 1개 = 도구 1개

- `PomodoroTimer(Tool)`, `name = "pomodoro_timer"`
- `parameters_schema`: `phase`("focus"|"break", 필수), `minutes`(number, 선택),
  `cycle`(integer, 기본 1), `total_cycles`(integer, 기본 1)
- `__call__`: 검증 실패 시 `{"error": ...}` (raise 금지, CLAUDE.md 규칙).
  본체는 `await asyncio.sleep(minutes * 60)` — BackgroundToolManager가 장기 실행·
  취소(task_cancel)·상태(task_status)·완료 알림을 모두 처리하므로 신규 인프라 없음.
  `asyncio.CancelledError`는 삼키지 않고 전파 (매니저가 CANCELLED 처리).
- 완료 반환 dict (모델 지시 포함):
  - focus: `{"status": "focus_complete", "cycle": c, "total_cycles": t, "next_action":
    "사용자에게 집중 완료를 알리고, 즉시 pomodoro_timer(phase='break', cycle=c,
    total_cycles=t)를 호출해 휴식 타이머를 시작하라"}`
  - break & c < t: `{"status": "break_complete", "next_action": "다음 세트(c+1/t)를
    시작할지 사용자에게 물어보고, 동의하면 phase='focus', cycle=c+1로 호출하라"}`
  - break & c >= t: `{"status": "pomodoro_done", "next_action": "전체 세트 완료를
    축하하고 마무리 인사를 하라"}`
- `needs_response`는 기본값(True) — 완료 시 모델이 발화.
- 튜닝 상수 모듈 상단: `DEFAULT_FOCUS_MINUTES = 25`, `DEFAULT_BREAK_MINUTES = 5`,
  `MIN_MINUTES = 1`, `MAX_MINUTES = 120`.

### profiles/desk_companion_ko/profile.md

- `default_tools`에 `"pomodoro_timer"` 추가 (task_status/task_cancel은 코어 자동 로드).
- 본문에 "집중 모드(뽀모도로)" 규칙 섹션: 집중 요청 시 pomodoro_timer 사용, 시작·완료를
  명확히 알림, 집중 완료 후 자동으로 휴식 타이머 시작, 세트 반복은 확인 후 진행,
  중단 요청 시 task_cancel 사용.

## 오류 처리

- phase 미지정/오타 → `{"error": "phase must be 'focus' or 'break'"}`
- minutes 비수치 → error dict; 범위 밖은 클램프 (에러 아님)
- cycle/total_cycles 비정상(<1) → 1로 보정

## 테스트

`tests/test_pomodoro.py` — `asyncio.sleep` monkeypatch로 즉시 완료:
focus 완료 메시지·break 자동 전환 지시, break 중간/마지막 세트 분기, 기본값(25/5)·클램프,
phase 오류, CancelledError 전파(pytest.raises), 프로필에 도구 포함 검증.
라이브: 실물에서 "1분 뽀모도로 시작" → 시작 발화 → 1분 후 완료 알림 + 휴식 자동 시작 확인.

## 범위 외

진행 중 중간 알림(매니저 확장 필요), UI 타이머 표시, 집중 중 유휴 모션 억제,
다른 프로필 반영.
