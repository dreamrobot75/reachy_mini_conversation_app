# OpenAI 한국어 음성 베이스라인 — 설계 문서

- **작성일**: 2026-08-01
- **상태**: 설계 승인됨, 구현 계획 수립 대기
- **선행 문서**: [2026-07-27-korean-desk-companion-design.md](2026-07-27-korean-desk-companion-design.md) (W1 "한국어 페르소나 + ko 전사" 항목의 구체화)

## 배경과 목표

베이스 앱의 음성 백엔드는 Hugging Face가 호스팅하는 OpenAI 호환 realtime 서버다.
한국어 전사는 `REALTIME_TRANSCRIPTION_LANGUAGE=ko`로 가능하지만, HF 백엔드의 한국어
응답·발화 품질에는 한계가 있다. 공모전 데모의 기반이 될 **"한국어로 듣고 한국어로
말하는" 베이스라인**을 OpenAI 정식 Realtime API로 확보한다.

핵심 관찰: 앱은 이미 openai-python SDK의 Realtime 프로토콜로 HF 서버와 통신한다
(`huggingface_realtime.py`). 따라서 새 파이프라인을 만드는 것이 아니라, HF에 고정된
연결 지점만 교체하는 **백엔드 provider 추가** 작업이다.

## 결정 사항 (브레인스토밍 결과)

| 결정 | 선택 | 근거 |
| :--- | :--- | :--- |
| 구성 형태 | 앱에 provider 추가 | 별도 예제 스크립트가 아니라 전체 앱이 한국어로 동작해야 이후 모든 공모전 기능의 실제 베이스라인이 됨 |
| 페르소나 범위 | 최소 한국어 프로필 포함 | 언어 설정만으로는 답변이 영어로 나올 수 있음. 본격 페르소나는 별도 작업 |
| 기본 모델 | `gpt-realtime-mini` | 한국어 품질 충분 + 반복 테스트 비용 1/4. 데모 직전 설정 한 줄로 `gpt-realtime` 승급 가능 |
| 통합 방식 | 서브클래스 (아래 참고) | upstream merge 충돌 최소화 |

### 통합 방식 비교

| 방식 | 판단 |
| :--- | :--- |
| **A. 서브클래스 (채택)** | `OpenAIRealtimeHandler(HuggingFaceRealtimeHandler)` — 오버라이드 4지점만 교체. upstream 파일 무수정 → 주간 upstream merge 충돌 최소. 검증된 대화 루프 1,000여 줄 재사용 |
| B. 기존 핸들러에 분기 | `huggingface_realtime.py` 직접 수정 → 매주 merge 충돌 자초. 기각 |
| C. 독립 핸들러 | 응답 큐잉·도구 배치·인터럽트 로직 복제 필요. 기각 |

서브클래스의 약점(부모 private 메서드 의존)은 upstream이 해당 메서드를 리팩터링하면
드러나지만, 그 경우 어떤 통합 방식이든 영향을 받으므로 감수한다.

## 성공 기준

1. `.env`에 `CONVERSATION_BACKEND=openai` + `OPENAI_API_KEY`만 넣으면 앱 전체(시뮬 포함)가 한국어 왕복 대화 가능
2. 전사 로그에 한국어가 정상 표기되고, 기존 도구 호출(`move_head`, `play_emotion` 등)이 동작
3. `CONVERSATION_BACKEND` 미설정 시 기존 HF 경로가 동일하게 유지 (upstream 회귀 없음)

## 컴포넌트 설계

### config.py + .env.example — 신규 설정 4개

| 설정 | 기본값 | 비고 |
| :--- | :--- | :--- |
| `CONVERSATION_BACKEND` | `hf` | `hf` \| `openai`. 미설정 시 기존 동작 |
| `OPENAI_API_KEY` | 없음 | openai 백엔드 선택 시 필수 |
| `OPENAI_REALTIME_MODEL` | `gpt-realtime-mini` | 데모 시 `gpt-realtime` 승급 가능 |
| `OPENAI_VOICE` | `marin` | OpenAI 보이스 목록 내에서 선택 |

한국어 데모 구성은 `.env.example`에 주석 블록으로 안내한다:
`CONVERSATION_BACKEND=openai` + `REALTIME_TRANSCRIPTION_LANGUAGE=ko` +
`REACHY_MINI_CUSTOM_PROFILE=desk_companion_ko`.

### openai_realtime.py (신규) — 오버라이드 4지점

`OpenAIRealtimeHandler(HuggingFaceRealtimeHandler)`:

1. **`_build_realtime_client()`** — HF 세션 allocator 경로 전체 생략.
   `AsyncOpenAI(api_key=OPENAI_API_KEY)` + `wss://api.openai.com/v1/realtime`,
   connect query `{"model": OPENAI_REALTIME_MODEL}`
2. **`_get_session_config()`** — 오디오 포맷을 HF 전용 `rate=None`(네이티브 16 kHz)에서
   OpenAI 표준 `audio/pcm` 24 kHz로 교체. 전사는 기존과 동일하게 `gpt-4o-transcribe` +
   `REALTIME_TRANSCRIPTION_LANGUAGE` 재사용
3. **샘플레이트** — `SAMPLE_RATE = 24000` + `receive()` 오버라이드: 마이크 프레임
   (로봇 미디어 계층 네이티브, 통상 16 kHz)을 24 kHz로 리샘플 후 전송. 출력 오디오는
   `emit()` 오버라이드에서 재생 장치 샘플레이트(통상 16 kHz)로 다운샘플 후 전달
   — 로봇 재생 파이프라인이 16 kHz 고정이라 24 kHz를 그대로 보내면 1.5배 느리게 재생됨
   (구현 중 발견되어 최초 가정을 수정)
4. **보이스 목록** — OpenAI 보이스(marin, cedar, alloy 등)로 교체. UI 보이스 선택·
   `change_voice` 흐름은 부모 로직 그대로 동작

### main.py — 핸들러 팩토리 분기

기존 팩토리에 `CONVERSATION_BACKEND=openai` → `OpenAIRealtimeHandler` 분기 추가.
키 누락 시 기동 단계에서 명확한 한 줄 에러로 즉시 실패한다 (런타임 중 조용한 무응답 금지).

### profiles/desk_companion_ko/ (신규)

새 `profile.md` 형식(upstream #484 반영) 기준 최소 한국어 페르소나:
한국어로만 응답, 존댓말 기본, 데스크 동반자 톤. 아침 브리핑·집중 모드 멘트 등
본격 페르소나는 범위 외.

## 데이터 흐름 (변경점만)

```
마이크(네이티브 16k) → receive(): 16k→24k 리샘플
  → OpenAI Realtime (ko 전사, 한국어 응답)
  → output_queue(24k) → emit(): 24k→재생 장치 레이트(16k) 다운샘플 → 스피커
```

도구 호출·인터럽트·응답 큐잉·유휴 정책은 부모 클래스 로직을 그대로 사용한다.

## 오류 처리

- `OPENAI_API_KEY` 누락 + openai 백엔드 → 기동 즉시 실패, 원인 명시
- 429/네트워크 단절 → 부모의 기존 재연결·프레임 드롭 로직 재사용 (신규 코드 없음)
- 미지원 보이스 요청 → 기존 `_resolve_backend_voice` 패턴대로 기본값 폴백 + 경고 로그

## 테스트

- **유닛 (API 호출 없음)**: 세션 config의 24 kHz·보이스·모델 반영 검증, 팩토리의
  백엔드별 핸들러 선택 검증, 리샘플 함수의 출력 길이·dtype 검증.
  `tests/test_huggingface_realtime.py` 패턴을 따른다
- **수동 체크리스트**: 시뮬 데몬 기동 → 한국어 인사 → 도구 호출 유도("고개 들어봐")
  → 발화 중 인터럽트 → 전사 로그 확인
- **게이트**: `ruff check . --fix && ruff format . && mypy --pretty --show-error-codes && pytest tests/ -v`

## 범위 외 (YAGNI)

UI의 백엔드 전환 토글, 웨이크 워드/DoA, 본격 데스크 컴패니언 페르소나(브리핑·뽀모도로 멘트),
비용 모니터링, HF 백엔드 한국어 개선.
