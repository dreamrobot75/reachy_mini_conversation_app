# Claude Code Instructions

Read `AGENTS.md` in this directory for full instructions on developing Reachy Mini applications.
**AGENTS.md의 코드 품질·스타일·PR·CI 규칙은 이 프로젝트에서도 그대로 적용된다. 아래 내용은 그 위에 얹는 공모전 프로젝트 컨텍스트다.**

---

## 프로젝트 컨텍스트 — AI 스마트 데스크 동반자 공모전

이 저장소는 upstream `reachy_mini_conversation_app`을 **베이스 프레임워크**로 삼아,
Reachy Mini를 **감정 반응형 스마트 데스크 동반자**로 만드는 공모전 프로젝트다.
전체 계획은 [`oss_plan/plan_first.md`](oss_plan/plan_first.md) 참고.

핵심 시나리오는 4단계 상태 흐름이다:

| 단계 | 동작 |
| :--- | :--- |
| **1. 슬립/대기** | 고개를 숙이고 안테나를 눕힌 채 웨이크 워드 대기 |
| **2. 웨이크업** | 음성 방향(DoA)·카메라로 사용자를 감지하고 기지개 켜듯 일어나 시선 고정 |
| **3. 데스크 파트너** | 일정 브리핑, 뽀모도로 집중 모드, 날씨·대화 지원 |
| **4. 수면 복귀** | 종료 인사 후 안전 토크 홀드와 함께 슬립 모드 전환 |

## 베이스 프레임워크가 이미 제공하는 것

새 기능을 만들기 전에 **기존 구현부터 확인**한다. 아래는 이미 동작하는 기능이므로
다시 만들지 말고 확장한다:

- **실시간 대화 루프** (VAD → STT → LLM → TTS): `huggingface_realtime.py` + `conversation_handler.py`
- **LLM 도구 프레임워크**: `tools/core_tools.py`의 `Tool` 서브클래스 (예: `move_head.py`, `play_emotion.py`)
- **슬립/기상 모션**: `tools/go_to_sleep.py`, 모터 제어는 `moves.py`
- **얼굴 추적**: `tools/head_tracking.py`, `tools/camera.py`
- **유휴 행동 정책**: `idle_policy.py` (대기 상태 행동의 진입점)
- **감정 모션·댄스**: `dance_emotion_moves.py`, `tools/play_emotion.py`
- **장기 기억**: `memory.py`, `tools/remember.py` / `tools/forget.py`
- **페르소나 시스템**: `profiles/` (디렉토리 1개 = 페르소나 1개), `personality.py`
- **외부 서비스 연동 통로**: `mcp_client.py` (MCP), `tool_spaces.py`

## 공모전 기능 → 코드 매핑

계획서의 기능을 이 코드베이스에 구현할 때의 기본 배치:

| 계획서 기능 | 구현 위치 |
| :--- | :--- |
| 웨이크 워드 감지 | `audio/` 확장 + `app_lifecycle.py`/`idle_policy.py` 연동 |
| 음원 방향 추적 (DoA) | `audio/` 신규 모듈 (reSpeaker 의존 → mock 인터페이스 필수) |
| 안면 인식·착석 감지 | `tools/head_tracking.py`·`tools/camera.py` 확장 |
| 시선 제어 (look_at) | `moves.py` + `tools/move_head.py` 확장 |
| 기지개 웨이크업·인사 모션 | `dance_emotion_moves.py`에 모션 추가 |
| 감정별 안테나 제어 | `moves.py` / `dance_emotion_moves.py` |
| 일정 브리핑 (구글 캘린더) | `tools/` 신규 도구 또는 `mcp_client.py` 경유 |
| 날씨 | `tools/` 신규 도구 |
| 뽀모도로 집중 모드 | `tools/` 신규 도구 + `background_tool_manager.py` (타이머류 장기 작업) |
| 데스크 동반자 페르소나 | `profiles/` 신규 디렉토리 |
| 안전 장치 (토크 홀드, 자동 슬립) | `moves.py`·`app_lifecycle.py` |

- **LLM이 호출하는 기능**은 전부 `tools/`의 `Tool` 서브클래스로: 파일 1개 = 도구 1개,
  `name`/`description`/`parameters_schema` + async `__call__(self, deps, **kwargs)` → `dict`.
  실패 시 raise 대신 `{"error": ...}` 반환 (대화 루프를 죽이지 않는다).
- **LLM 개입 없이 자율 동작하는 기능**(웨이크 워드, DoA, 착석 감지)은 도구가 아니라
  `idle_policy.py`·`app_lifecycle.py`에 연결되는 모듈로 만든다.
- 새 설정값은 `config.py` + `.env.example`에 추가한다.

## 팀 협업 규칙 (plan_first.md 요약)

- **담당 단위**: 기능 1개 = 팀원 1명(팀). 다른 사람 담당 코드는 PR 없이 수정하지 않는다.
- **브랜치**: `feat/<기능>` 형식 (upstream 규칙 `<type>/<short-description>` 준수).
- **시뮬 기준 개발**: 실물 로봇 없이 MuJoCo 시뮬 데몬으로 개발·시연 가능해야 한다.
  하드웨어 의존 기능(reSpeaker DoA 등)은 mock 인터페이스를 함께 제공한다.
- **인터페이스 합의**: 기능 간 연동(perception → motion 등)은 구현 전에 함수 시그니처를
  이슈/PR로 합의한다.
- **튜닝 파라미터**는 각 모듈 상단 상수로 모은다 (자세·타이밍·각도 등).

## Windows 개발 주의사항

- 팀 개발 환경에 Windows가 포함된다. 하드코딩 경로·OS 전용 API 금지 (upstream 규칙과 동일).
- 한글 소스를 다루는 SDK 도구(`reachy-mini-app-assistant` 등) 실행 전
  `$env:PYTHONUTF8 = "1"` 설정 (cp949 인코딩 깨짐 방지).

## 명령어

venv 활성화 후, 리뷰 요청 전 반드시 전체 게이트 통과:

```bash
ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v
```

| 작업 | 명령 |
|------|------|
| 앱 실행 | `reachy-mini-conversation-app` |
| 의존성 변경 시 | `uv lock` (CI가 `uv.lock` 일치 검증) |
