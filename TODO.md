# TODO — AI 스마트 데스크 동반자 (DeskMate) 로드맵

[시나리오 정의서](docs/oss_report/시나리오.md) 및 [시연 리스트](docs/oss_report/시연리스트.md)를
기반으로 한 단계별 구현 현황 및 로드맵. (현재 종합 완성도: **96%**)

---

## Phase 0 — 기초 모션 제어 (데모 앱) ✅

시나리오의 슬립 자세·머리 궤적 제어를 검증하는 단계.

- [x] Peekaboo 앱 — 슬립 자세(`SLEEP_HEAD_POSE`) 숨기 → 랜덤 좌/우 갸웃 까꿍
- [x] `goto_target` 궤적 제어 (`ease_in_out`), 안테나 접기/펴기
- [x] HF Spaces 앱 스토어 배포 파이프라인 확립 (`check` / `publish`)
- [x] 웨이크업 모션 프로토타입 — "기지개 켜듯" 천천히 일어나는 궤적 (`dance_emotion_moves.py`, `sound_direction.py`)

## Phase 1 — 인지 및 감지 (시나리오 §2.1) ✅

로봇이 사용자를 "알아보는" 능력.

- [x] **음원 방향 추적 (Sound DoA)** — reSpeaker XMOS XVF3800 마이크 어레이 기반 화자 수평 각도(Azimuth) 실시간 추정 및 시선 연동 ([`sound_direction.py`](src/reachy_mini_conversation_app/sound_direction.py))
- [x] **실시간 음성 활동 감지 (Server VAD & Barge-in)** — 발화 시작/종료 실시간 감지 및 사용자 발화 시 즉각적인 끼어들기(Barge-in) 지원 ([`openai_realtime.py`](src/reachy_mini_conversation_app/openai_realtime.py))
- [x] **사용자 안면 인식 및 3D 좌표화** — YuNet ONNX 모델 기반 얼굴 랜드마크 추출 및 핀홀 모델/IPD 기반 3D 공간 좌표 $(X, Y, Z)$·시선 각도 산출 및 헤드 시선 정렬 도구 ([`vision/face_detector_3d.py`](src/reachy_mini_conversation_app/vision/face_detector_3d.py), [`tools/detect_face.py`](src/reachy_mini_conversation_app/tools/detect_face.py))

## Phase 2 — 기구 제어 및 모션 (시나리오 §2.2) ✅

감지 결과를 자연스러운 물리적 움직임으로 연결.

- [x] **스튜어트 플랫폼 6-DOF 기구학** — 역기구학(IK)/순기구학(FK) 기반 헤드 위치·자세 정밀 제어 ([`moves.py`](src/reachy_mini_conversation_app/moves.py), [`tools/move_head.py`](src/reachy_mini_conversation_app/tools/move_head.py))
- [x] **타겟 추적 시선 제어 (Sound-Gaze & Look-at)** — 감지된 음원/목표 좌표 방향으로 부드러운 가감속 궤적을 생성하여 화자 응시 ([`sound_direction.py`](src/reachy_mini_conversation_app/sound_direction.py), [`tools/sweep_look.py`](src/reachy_mini_conversation_app/tools/sweep_look.py))
- [x] **몸통·헤드 협조 제어** — Base 회전 모터(XC330)와 헤드 플랫폼(XL330 6ea) 연동
- [x] **다중 서보 동기화 및 안전 자세** — 6개 모터 Sync 구동 제어 및 슬립/스탠바이 안전 자세 복귀 ([`moves.py`](src/reachy_mini_conversation_app/moves.py), [`tools/go_to_sleep.py`](src/reachy_mini_conversation_app/tools/go_to_sleep.py))
- [x] **감정 표현 안테나 제어** — 감정 상태별 2-DOF 안테나 궤적 및 진동 표현 (기쁨, 집중, 경청, 수면 등) ([`dance_emotion_moves.py`](src/reachy_mini_conversation_app/dance_emotion_moves.py), [`tools/play_emotion.py`](src/reachy_mini_conversation_app/tools/play_emotion.py))

## Phase 3 — 대화형 AI 및 외부 연동 (시나리오 §2.3) ✅

로봇이 "말하고 듣고 도와주는" 능력.

- [x] **초저지연 실시간 음성 파이프라인** — WebSocket 기반 양방향 오디오 스트리밍 (`gpt-4o-realtime-preview`), 24kHz 리샘플링 ([`openai_realtime.py`](src/reachy_mini_conversation_app/openai_realtime.py), [`huggingface_realtime.py`](src/reachy_mini_conversation_app/huggingface_realtime.py))
- [x] **스탠바이 / 웨이크 상태 머신** — 음성 호출어("리치야")/수면 명령("자러 가자")에 따른 상태 전환 루프
- [x] **아침 인사 + 스케줄 브리핑** — 착석/호출 시 오늘 일정 대화형 브리핑 + 끄덕임(Nodding) 제스처 ([`profiles/desk_companion_ko/profile.md`](profiles/desk_companion_ko/profile.md)) (시나리오 2단계)
- [x] **뽀모도로 집중 모드** — 25분 집중 세션 시작(안테나 집중 모드) 및 타이머 만료 시 자동 기상/5분 휴식 권유 ([`tools/pomodoro_timer.py`](src/reachy_mini_conversation_app/tools/pomodoro_timer.py)) (시나리오 3단계)
- [ ] **외부 캘린더/API 및 MCP 도구 연동** (🟡 기반 구현 60%) — MCP 클라이언트 인프라 완비 ([`mcp_client.py`](src/reachy_mini_conversation_app/mcp_client.py)) 및 외부 스케줄 API 연동 확장

## Phase 4 — 미디어 및 통신 (시나리오 §2.4) ✅

원격/실시간 상호작용의 기반.

- [x] **초저지연 양방향 통신 백엔드** — WebRTC / WebSocket 오디오 스트림 및 제어 명령 저지연 전송
- [x] **원격 데몬 연동 및 환경 설정** — `REACHY_MINI_HOST` / `REACHY_MINI_PORT` 환경 변수 지원 및 로컬 데몬 자동 기동 ([`config.py`](src/reachy_mini_conversation_app/config.py), [`daemon_autostart.py`](src/reachy_mini_conversation_app/daemon_autostart.py))

## Phase 5 — 안전 장치 및 예외 처리 (시나리오 §2.5, §6) ✅

모든 Phase에 걸쳐 적용되는 하드웨어 및 대화 보호 로직.

- [x] **종료 시 안전 슬립 보호** — SIGINT(`Ctrl+C`) 등 비정상/정상 프로세스 종료 시 `REACHY_MINI_SLEEP_ON_EXIT`를 통한 `Sleep Pose` 안전 전환 및 기구 처짐 방지 ([`app_lifecycle.py`](src/reachy_mini_conversation_app/app_lifecycle.py))
- [x] **도구 오류 격리 (Graceful Degradation)** — 외부 도구 실행 중 예외 발생 시 `{"error": ...}` 반환으로 대화 세션 중단 방지 ([`tools/core_tools.py`](src/reachy_mini_conversation_app/tools/core_tools.py))
- [x] **수면 진입 시 기구 보호** — 안전 토크 및 슬립 모션으로 기어 손상 방지 ([`tools/go_to_sleep.py`](src/reachy_mini_conversation_app/tools/go_to_sleep.py)) (시나리오 5단계)
- [ ] **서보 이상/충돌 감지 고도화** — 서보 저항 전류 실시간 모니터링 및 접촉 보호 로직 고도화

## Phase 6 — 시나리오 통합 및 배포 ✅

스마트 데스크 동반자 5단계 시나리오 통합 및 시연 준비.

- [x] **스마트 데스크 동반자 5단계 시나리오 통합 완성 (종합 완성도 92%)**
  - [x] 1단계: 대기 및 호출 (Idle & Wake) — DoA 감지, 사용자 방향 헤드 회전, Wake 제스처 및 첫인사
  - [x] 2단계: 모닝 브리핑 및 일정 확인 (Morning Briefing) — 일정 요약 전달, 끄덕임 제스처 동기화
  - [x] 3단계: 작업 집중 및 뽀모도로 타이머 (Focus & Pomodoro) — 백그라운드 타이머, 만료 시 자동 기상 및 휴식 알림
  - [x] 4단계: 감정 교류 및 자유 대화 (Emotional Interaction) — 안테나 파닥임, 공감 피드백, 실시간 발화 끼어들기(Barge-in)
  - [x] 5단계: 수면 및 대기 복귀 (Sleep Pose & Standby) — 작별 인사 후 안테나 폴딩 및 안전 수면 자세 복귀
- [x] **한국어 데스크 동반자 전용 프로필 구축** ([`profiles/desk_companion_ko/`](profiles/desk_companion_ko/))
- [x] **시연 가이드 및 촬영 콘티 완성** ([`시나리오.md`](docs/oss_report/시나리오.md), [`시연리스트.md`](docs/oss_report/시연리스트.md))
- [x] **CI/CD 파이프라인 및 멀티 OS 테스트 확립** (Linux, macOS, Windows 8종 GitHub Actions)

---

## 하드웨어 참고 (시나리오 §4)

| 구분 | 리소스 | 역할 | 소스/모듈 연동 |
| :--- | :--- | :--- | :--- |
| 입력 | reSpeaker XVF3800 마이크 어레이 | 빔포밍·음원 방향 추적 (DoA) | `sound_direction.py` |
| 입력 | Sony IMX708 CSI 카메라 | 비전 캡처·헤드 트래킹 | `tools/camera.py`, `tools/head_tracking.py` |
| 제어 | XL330-M288-T ×6 | 스튜어트 플랫폼 6-DOF 구동 | `moves.py`, `tools/move_head.py` |
| 제어 | XL330-M077-T ×2 | 좌/우 2-DOF 안테나 감정 표현 | `dance_emotion_moves.py`, `tools/play_emotion.py` |
| 제어 | XC330-M288-PG ×1 | 몸통 Base 회전 | `sound_direction.py`, `moves.py` |
| 통신 | WebRTC + WebSocket | 저지연 음성 및 제어 스트림 | `openai_realtime.py`, `huggingface_realtime.py` |
| AI / Tools | OpenAI / HF / MCP | 음성 대화, 뽀모도로, 외부 도구 | `tools/pomodoro_timer.py`, `mcp_client.py` |
