# 슬립 대기 ↔ 대화 반복 루프 (standby 모드) — 설계 문서

- **작성일**: 2026-08-01
- **상태**: 설계 승인됨
- **결정**: A안(세션 유지 + 전사 기반 웨이크) · 웨이크 문구 기본 `깨어나,리치미니,일어나`

## 목표

실행 한 번으로 다음 루프가 무한 반복된다:

```
실행 → 자동기상 → [대화] --"종료해 줘"(go_to_sleep 도구)--> [슬립 대기]
                     ↑                                          |
                     +---- 웨이크 문구 전사 감지 (기상 모션+인사) --+
```

Ctrl+C만 진짜 종료(기존 sleep-on-exit 유지). HF 백엔드는 기존 "음성 종료=앱 종료" 동작 유지.

## 방식 (A안)

슬립 대기 중에도 OpenAI 세션을 유지하되 `ServerVad(create_response=False,
interrupt_response=False)`로 **전사만 계속, 모델 응답은 차단**. 사용자 전사에
웨이크 문구가 나타나면 기상. 로컬 웨이크워드 엔진(W3)은 추후 교체 가능하도록
진입/기상 메서드를 분리해 둔다.

**비용 주의**: 슬립 대기 중에도 오디오 입력 과금이 계속된다(gpt-realtime-mini 기준
시간당 수백 원 수준). `.env.example`에 명시한다.

## 컴포넌트

### openai_realtime.py — standby 상태 머신 (부모 클래스 무수정)

- `_standby: bool` 플래그, `_loop` 저장(`_build_realtime_client`에서 `asyncio.get_running_loop()`)
- `enter_standby()` (async): 모션 매니저 stop(reset_to_neutral=False) → `robot.goto_sleep()`
  (to_thread) → 세션 update(전사 전용 VAD) → `_standby=True`. 외부(도구 스레드)에서는
  `request_standby()` (sync)가 `asyncio.run_coroutine_threadsafe`로 호출
- `wake_from_standby()` (async): `_standby=False` → 모션 매니저 `start()` 재시작 →
  `enable_motors()`+`wake_up()` (to_thread, app_lifecycle 패턴) → 세션 복원
  (`ServerVad(interrupt_response=True)`) → 기상 인사(기존 startup greeting 패턴:
  `conversation.item.create` user 텍스트 + `_safe_response_create`)
- `_emit_transcript` 오버라이드: standby 중 user 최종 전사에서 웨이크 매칭 시
  `_loop.create_task(wake_from_standby())` 후 부모 호출
- `_idle_behavior_ready` 오버라이드: standby면 False (유휴 모션 차단)
- `matches_wake_phrase(transcript, phrases)` 순수 함수: 공백·문장부호 제거 후
  소문자 부분 일치

### config.py + .env.example

| 설정 | 기본값 | 의미 |
| :--- | :--- | :--- |
| `REACHY_MINI_STANDBY_ON_SLEEP` | `1` | 음성 go_to_sleep을 standby로 전환 (0이면 기존 앱 종료) |
| `REACHY_MINI_WAKE_PHRASES` | `깨어나,리치미니,일어나` | 쉼표 구분 웨이크 문구 |

### main.py — deps.go_to_sleep wiring 분기

OpenAI 백엔드 + `REACHY_MINI_STANDBY_ON_SLEEP=1`이면 `deps.go_to_sleep = handler.request_standby`
기반 콜백(앱 종료·스트림 close 없음), 아니면 기존 `go_to_sleep_and_stop_app`.
무활동 타임아웃 경로도 같은 콜백을 타므로 standby로 통일된다 (앱은 계속 떠서 웨이크 대기).

### Ctrl+C 상호작용

standby 중 Ctrl+C → 로봇이 이미 잠들어 있으므로 sleep-on-exit 취침 모션은 생략
(핸들러의 standby 상태 확인). 종료 자체는 기존대로 진행.

## 오류 처리

- standby 진입/기상 중 세션 update 실패: 경고 로그 후 상태 플래그는 그대로 진행
  (다음 전사에서 재시도 가능). raise로 대화 루프를 죽이지 않는다.
- 웨이크 중복 트리거: `_standby` 플래그를 웨이크 시작 시점에 내려 이중 실행 방지.

## 테스트

- `matches_wake_phrase` 유닛: 공백 변형("리치 미니"), 문장 속 포함("깨어나 리치미니야"),
  불일치, 빈 문자열
- 상태 전이: fake connection으로 `session.update` 캡처 — enter_standby 후
  `create_response=False`, wake 후 복원; `_emit_transcript` 경유 웨이크 트리거;
  standby 중 `_idle_behavior_ready()==False`
- 회귀: 기존 전체 스위트
- 라이브(실물): 음성 "종료해 줘" → 취침 유지 확인 → "깨어나 리치미니" → 기상·인사 →
  재대화 → 반복 1회 이상

## 범위 외

로컬 웨이크워드 엔진(W3에서 교체), DoA 기반 웨이크, 슬립 중 세션 자동 절전/재수립,
HF 백엔드 standby.
