# 종료 시 자연스러운 슬립 — 설계 문서

- **작성일**: 2026-08-01
- **상태**: 설계 승인됨 (슬립 모션만, 데몬은 running 유지)

## 배경

현재 앱은 종료 시 로봇을 의도적으로 재우지 않는다 (upstream 설계: 대시보드/모바일의
"앱 중지"는 로봇 끄기가 아님 — main.py poll_stop_event 주석). 슬립은 음성
`go_to_sleep` 도구와 무활동 타임아웃에만 예약되어 있어, 콘솔에서 Ctrl+C로 끝내면
로봇이 깨어 있는 채로 남는다.

## 결정

- **콘솔 직접 종료(Ctrl+C, Windows에서는 Ctrl+Break 포함)일 때만** 취침 모션 후 종료.
- **외부 중지**(대시보드·모바일 `app_stop_event`)는 upstream 동작 그대로 유지 (재우지 않음).
- **데몬은 정지하지 않는다** — 다음 실행 시 빠른 기상. (전체 꺼짐이 필요하면 대시보드/API 사용)
- 설정: `REACHY_MINI_SLEEP_ON_EXIT` (기본 **켜짐**, `0`으로 끄기 가능).

## 구현

- **config.py**: `REACHY_MINI_SLEEP_ON_EXIT = _env_flag(..., default=True)` + refresh + `.env.example` 주석.
- **main.py**:
  - `except KeyboardInterrupt`에서 `keyboard_interrupted = True` 기록.
  - Windows 콘솔 호환: `signal.SIGBREAK`가 있으면 KeyboardInterrupt를 일으키는 핸들러 등록
    (Ctrl+Break·콘솔 종료도 같은 경로).
  - `finally` 블록 진입 직후: `keyboard_interrupted and config.REACHY_MINI_SLEEP_ON_EXIT and
    not go_to_sleep_requested.is_set()`이면 기존 `run_go_to_sleep_tool()` 호출 (음성 도구와
    동일 시퀀스: 모션 정지 → `robot.goto_sleep()` → 스트림 정리; 중복 요청은 내부 lock이 방지).
  - 이후 기존 정리(모터 정지·미디어 close·disconnect) 그대로.

## 오류 처리

`run_go_to_sleep_tool`은 실패를 dict로 반환하고 raise하지 않으므로 종료 흐름을 막지 않는다.

## 테스트

- config 플래그 기본값(True)·env 끄기(`0`) 유닛 테스트.
- 라이브 검증: 실물 로봇으로 앱 실행 → Ctrl+Break(자동화) 종료 → 취침 모션 확인,
  `REACHY_MINI_SLEEP_ON_EXIT=0`이면 기존 동작 확인.

## 범위 외

데몬 정지(옵션 B), 외부 중지 경로 변경, 종료 인사 TTS 멘트(페르소나 작업에서 별도).
