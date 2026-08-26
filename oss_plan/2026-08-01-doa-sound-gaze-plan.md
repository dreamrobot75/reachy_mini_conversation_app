# DoA 소리 방향 시선 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대화 중 화자 방향으로 머리를 돌리고, 웨이크 시 부른 사람 방향으로 시선을 고정한다.

**Architecture:** 신규 `sound_direction.py`에 폴링 스레드(`SoundDirectionWatcher`)·각도 매핑·시선 큐잉(`queue_gaze`, sweep_look 패턴)·대화 중 필터(`SpeakerGaze`)를 모두 담는다. `main.py`가 watcher를 기동·와이어링하고, `openai_realtime.py`의 `wake_from_standby`가 최근 음성 방향으로 기상 시선을 큐잉한다.

**Spec:** [`oss_plan/2026-08-01-doa-sound-gaze-design.md`](2026-08-01-doa-sound-gaze-design.md)

## Global Constraints

- 신규 pip 의존성 금지; `huggingface_realtime.py`·`moves.py`·`dance_emotion_moves.py` 수정 금지
- 게이트: `ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v`
- 테스트는 실제 로봇·네트워크 호출 금지 (httpx fake·MagicMock)
- 튜닝 상수는 `sound_direction.py` 상단에 모은다 (팀 규칙)

---

### Task 1: sound_direction.py (매핑·watcher·queue_gaze·SpeakerGaze) + config

**Files:**
- Create: `src/reachy_mini_conversation_app/sound_direction.py`
- Modify: `src/reachy_mini_conversation_app/config.py` (`REACHY_MINI_DOA_LOOK` `_env_flag(default=True)` + refresh)
- Modify: `.env.example`
- Test: `tests/test_sound_direction.py` (신규)

**Interfaces (Task 2가 의존):**
- `doa_angle_to_head_yaw(angle: float) -> float` — yaw = π/2−angle, ±`MAX_HEAD_YAW_RAD`(70°) 클램프
- `queue_gaze(movement_manager, reachy_mini, yaw: float, duration: float = 0.8) -> None`
- `SoundDirectionWatcher(host: str, port: int, on_speech: Callable[[float], None] | None)` — `start()`/`stop()`/`recent_speech_angle(max_age_s: float) -> float | None`; 연속 `DOA_FAILURE_LIMIT`(10)회 실패(null 응답 포함) 시 자가 종료
- `SpeakerGaze(movement_manager, reachy_mini, is_enabled: Callable[[], bool])` — `on_speech(angle)`: enabled·`is_idle()`·`_head_tracking` False·15° 임계·1.5초 쿨다운 통과 시 `queue_gaze`
- `WAKE_GAZE_MAX_AGE_S = 10.0`
- `config.REACHY_MINI_DOA_LOOK: bool`

**Steps:**
- [ ] 실패 테스트 작성: 매핑(0/π/2/π/클램프), `_poll_once` speech 기록·콜백, null·예외 응답의 실패 카운트, 실패 한도 자가 종료, `recent_speech_angle` 신선도, SpeakerGaze 게이트(비활성·not idle·tracking 중·임계 미만·쿨다운) 및 정상 큐잉
- [ ] 실패 확인 → 구현 → 통과 → 게이트 → 커밋 `feat: sound-direction (DoA) watcher and speaker gaze`

### Task 2: main.py 와이어링 + 웨이크 시선 + 라이브 검증

**Files:**
- Modify: `src/reachy_mini_conversation_app/main.py` (watcher 기동/정지, SpeakerGaze 연결, 핸들러 클래스에 watcher 주입)
- Modify: `src/reachy_mini_conversation_app/openai_realtime.py` (`sound_watcher` 속성 + `wake_from_standby` 기상 시선)
- Test: `tests/test_sound_direction.py` (웨이크 시선 케이스 추가)

**Steps:**
- [ ] 실패 테스트: `wake_from_standby`가 `sound_watcher.recent_speech_angle(10.0)` 결과로 `queue_move` 호출 / None이면 미호출
- [ ] `openai_realtime.py`: 클래스 속성 `sound_watcher = None`; `wake_from_standby`의 기상 모션 직후 시선 큐잉(`asyncio.to_thread(queue_gaze, ...)`, 실패는 경고 로그)
- [ ] `main.py`: `config.REACHY_MINI_DOA_LOOK`이면 `SoundDirectionWatcher(daemon_connection.host or "localhost", daemon_connection.port, on_speech=speaker_gaze.on_speech)` 기동. `SpeakerGaze.is_enabled`는 활성 핸들러가 standby 아닐 때 True(늦은 바인딩, go_to_sleep_action 패턴). `OpenAIRealtimeHandler.sound_watcher = watcher`(클래스 속성 — UI 재빌드 핸들러도 상속). `finally`에서 `watcher.stop()`
- [ ] `.env.example`: `# REACHY_MINI_DOA_LOOK=1` + 주석
- [ ] 게이트 → 커밋 `feat: wire DoA gaze into conversation and wake` → 라이브 검증(실물): 대화 중 좌→우 발화 시선 추종, 측면 웨이크 → 기상 후 시선, 시뮬/DoA 없음 환경 자가 비활성(로그 1줄) 확인

## Self-Review 결과

- 스펙 커버리지: 표의 3개 상태(대화/대기/웨이크), watcher 자가 종료, 게이트 4조건, 설정 1개, 종료 정리 — 전부 태스크에 대응
- 타입 일관성: Task 2가 쓰는 `recent_speech_angle`·`queue_gaze`·`WAKE_GAZE_MAX_AGE_S`는 Task 1 Interfaces와 동일
