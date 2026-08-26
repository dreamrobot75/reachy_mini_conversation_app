# DoA 소리 방향 시선 — 설계 문서

- **작성일**: 2026-08-01
- **상태**: 설계 승인됨 (대화 중 화자 방향 보기 + 웨이크 시 부른 방향 시선)
- **선행 확인**: 실물(192.168.0.144)에서 `GET /api/state/doa` 동작 검증 완료 —
  `{angle, speech_detected}`, 응답 ~30ms, 각도 실시간 갱신·음성 플래그 확인.
  reSpeaker 좌표: 0=좌, π/2=정면(후면 모호), π=우.

## 동작

| 상태 | 동작 |
| :--- | :--- |
| 대화 중 | `speech_detected`면 화자 방향으로 머리 yaw 회전(0.8초). 현재 시선과 15° 이상 차이 + 최소 1.5초 간격일 때만 (잔떨림 방지) |
| 슬립 대기 중 | 움직이지 않고 마지막 음성 방향·시각만 기록 |
| 웨이크 시 | 기상 모션 직후, 최근 10초 내 기록된 음성 방향으로 시선 고정 (계획서 "부른 사람을 보며 일어남" 시나리오) |

## 컴포넌트

### sound_direction.py (신규) — 튜닝 상수는 모듈 상단

- `doa_angle_to_head_yaw(angle: float) -> float` 순수 함수:
  yaw = π/2 − angle (DoA 0=좌 → yaw +π/2 좌회전; π/2 → 0 정면; π → −π/2 우회전),
  ±70°(≈1.22 rad) 클램프. `create_head_pose`의 yaw 부호(+=좌)와 일치 (sweep_look 참조).
- `SoundDirectionWatcher(host, port, on_speech)` — daemon 스레드:
  - 0.4초 간격으로 `http://{host}:{port}/api/state/doa` 폴링 (httpx)
  - `speech_detected=True`면 `last_speech_angle`/`last_speech_time`(monotonic) 갱신 + `on_speech(angle)` 콜백
  - `recent_speech_angle(max_age_s) -> float | None` 조회 API
  - 연속 실패 `DOA_FAILURE_LIMIT`(10)회면 경고 1회 남기고 자가 종료
    (시뮬레이터·reSpeaker 미장착 환경에서 조용히 비활성 — mock 인터페이스 요건)
  - `start()` / `stop()`

### 대화 중 시선 — main.py 연동

콜백(`on_speech`)에서 다음을 모두 만족할 때만 시선 큐잉:
1. 활성 핸들러가 standby 아님 (`in_standby` False 또는 속성 없음)
2. `movement_manager.is_idle()` — 댄스·감정·수동 모션에 양보
3. 얼굴 추적 비활성 (`getattr(movement_manager, "_head_tracking", False)` False —
   upstream 무수정을 위한 private 접근, 허용된 트레이드오프)
4. 목표 yaw와 직전 목표의 차이 ≥ `DOA_TURN_THRESHOLD_RAD`(0.26) 및
   직전 회전 후 `DOA_TURN_COOLDOWN_S`(1.5초) 경과

큐잉은 sweep_look 패턴 그대로: `create_head_pose(0,0,0,0,0,yaw)` +
`GotoQueueMove(duration=0.8)` + `queue_move` + `set_moving_state(0.8)`.
body yaw는 돌리지 않는다 (±70° 클램프 내 머리만).

### 웨이크 시선 — openai_realtime.py

핸들러에 `sound_watcher` 속성(기본 None, main.py에서 주입).
`wake_from_standby()`의 기상 모션 직후·VAD 복원 전에:
`watcher.recent_speech_angle(10.0)`이 있으면 위와 같은 GotoQueueMove로 해당 방향 시선.

### 설정

| 변수 | 기본값 | 의미 |
| :--- | :--- | :--- |
| `REACHY_MINI_DOA_LOOK` | `1` | 소리 방향 시선 전체 on/off |

데몬 주소는 기존 `REACHY_MINI_HOST`/`REACHY_MINI_PORT` 해석 결과를 재사용
(auto 모드면 localhost 대상, 실패 시 자가 비활성화가 처리).

## 오류 처리

- 폴링 실패: 카운트만 누적, 한도 도달 시 경고 1회 후 스레드 종료. 성공 시 카운트 리셋.
- 시선 큐잉 실패: 경고 로그, 대화 루프 영향 없음.
- 앱 종료 시 `watcher.stop()` (finally 블록).

## 테스트

- 유닛: 각도→yaw 매핑(0/π/2/π/클램프 경계), watcher가 speech 시 기록·콜백하는지,
  연속 실패 자가 종료, `recent_speech_angle`의 신선도 판정, 웨이크 시선 트리거
  (기록 있음/오래됨/None) — fake httpx·MagicMock movement_manager
- 라이브(실물): 대화 중 좌→우 이동 발화로 시선 추종 확인, 측면에서 웨이크 워드 →
  기상 후 그 방향 시선 확인

## 범위 외

body yaw 회전(70° 초과 각도 커버), 자는 중 고개 돌리기, 전면/후면 모호성 해소,
카메라 얼굴 탐색과의 융합(웨이크 후 head_tracking 자동 시작 등).
