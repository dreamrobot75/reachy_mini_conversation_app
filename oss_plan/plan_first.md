# OSS Reachy Mini — AI 스마트 데스크 동반자 🤖

[Reachy Mini](https://huggingface.co/docs/reachy_mini/index)(Pollen Robotics × Hugging Face의 오픈소스 데스크톱 로봇)를 **개인 방·홈 오피스의 지능형 동반자**로 만드는 프로젝트입니다.

## 프로젝트 비전

> **AI 기반 감정 반응형 스마트 데스크 동반자**
>
> 사용자가 컴퓨터 앞에 앉거나 로봇을 부르면 소리를 감지해 시선을 맞추고,
> 일정 브리핑·스케줄 관리·날씨 확인과 대화를 나누며, 사용자의 작업 상태에 맞춰
> 안테나와 고개 모션으로 상호작용하고 감정을 교류합니다.

Reachy Mini의 하드웨어 특성(스튜어트 플랫폼 9-DOF 기구, reSpeaker 마이크 어레이, CSI 카메라)과 대화형 AI(VAD·STT·LLM·TTS 파이프라인)를 결합하는 것이 목표이며, 시나리오는 4단계 흐름으로 설계되어 있습니다.

| 단계 | 동작 |
| :--- | :--- |
| **1. 슬립/대기** | 고개를 숙이고 안테나를 눕힌 채 웨이크 워드 대기 |
| **2. 웨이크업** | 음성 방향(DoA)·카메라로 사용자를 감지하고 기지개 켜듯 일어나 시선 고정 |
| **3. 데스크 파트너** | 일정 브리핑, 뽀모도로 집중 모드(안테나 내림), 날씨·대화 지원 |
| **4. 수면 복귀** | 종료 인사 후 안전 토크 홀드와 함께 슬립 모드 전환 |

전체 시나리오 정의서(필수 기술 체크리스트, 하드웨어 매핑, 안전 장치 포함)는
[interactive_ai_guide_scenario.md](https://github.com/orocapangyo/reachy-mini/blob/main/study/robert/interactive_ai_guide_scenario.md)를 참고하세요.

## 첫 데모 앱 — Peekaboo 🙈 (까꿍)

이 저장소에는 위 시나리오의 기초가 되는 모션 제어(슬립 자세, 머리 궤적 제어)를 연습하는 **첫 번째 데모 앱 Peekaboo**가 들어 있습니다.

로봇이 전원 OFF 때처럼 머리를 완전히 숙여 **숨었다가**, 언제 나올지 모르는 랜덤 타이밍에 **"까꿍!" 하고 고개를 들며** 매번 랜덤하게 **왼쪽/오른쪽으로 갸웃**합니다. 소리 감지 없는 타이머 기반 동작이라 마이크 없이 어디서나 잘 동작합니다.

## 저장소 구성

```
oss_reachymini/
├── reachy_mini_peekaboo/          # 배포용 앱 패키지 (HF Space로 그대로 게시됨)
│   ├── pyproject.toml             #   패키지 정의 + reachy_mini_apps entry point
│   ├── README.md                  #   HF Space 카드(메타데이터) + 앱 설명
│   ├── index.html / style.css     #   Space 랜딩 페이지 (루트 필수 파일)
│   └── reachy_mini_peekaboo/
│       ├── __init__.py
│       └── main.py                #   앱 본체 (ReachyMiniApp 상속, run() 루프)
└── app/peekaboo/
    ├── peekaboo_demo.py           # 학습용 플랫 스크립트 (클래스 없음, 배포 대상 아님)
    └── DEPLOY_peekaboo.md         # HF Spaces 배포 가이드 + 트러블슈팅
```

| 경로 | 용도 |
| :--- | :--- |
| [`reachy_mini_peekaboo/`](reachy_mini_peekaboo/) | Hugging Face Spaces 앱 스토어에 게시되는 실제 앱. 자세한 동작·튜닝 설명은 [앱 README](reachy_mini_peekaboo/README.md) 참고 |
| [`app/peekaboo/peekaboo_demo.py`](app/peekaboo/peekaboo_demo.py) | 같은 동작을 클래스/함수 없이 흐름이 한눈에 보이게 쓴 공부·실험용 단일 스크립트 |
| [`app/peekaboo/DEPLOY_peekaboo.md`](app/peekaboo/DEPLOY_peekaboo.md) | 검증(`check`)부터 게시(`publish`)까지 배포 전 과정과 실제 겪은 함정·해결법 |

## 요구 사항

- Python ≥ 3.10
- `reachy-mini` SDK — **로봇 데몬과 같은 버전**이어야 합니다 (버전이 다르면 연결은 되지만 로봇이 움직이지 않습니다)
- 실행 중인 Reachy Mini 데몬 (실물 로봇 또는 MuJoCo 시뮬레이터 — [SIM.md](SIM.md) 참고)

## 빠른 시작

데몬이 실행 중인 상태에서:

```bash
# 앱 설치 (editable)
pip install -e ./reachy_mini_peekaboo

# 직접 실행
python -m reachy_mini_peekaboo.main
```

또는 로봇 대시보드(<http://localhost:8000>)의 **Apps** 탭에서 실행할 수 있습니다.

학습용 데모는 스크립트 상단의 `ROBOT_HOST`를 자신의 로봇 IP로 바꾼 뒤:

```bash
python app/peekaboo/peekaboo_demo.py
```

## 동작 튜닝

머리 높이, 갸웃 각도 범위, 숨어 있는 시간 등 모든 파라미터는
[`reachy_mini_peekaboo/main.py`](reachy_mini_peekaboo/reachy_mini_peekaboo/main.py) 상단 상수로 모아 두었습니다.
자세한 표는 [앱 README](reachy_mini_peekaboo/README.md#튜닝)를 참고하세요.

## 배포 (Hugging Face Spaces)

```powershell
# 검증 — 구조·메타데이터·entry point 검사
$env:PYTHONUTF8 = "1"
reachy-mini-app-assistant check .\reachy_mini_peekaboo

# 게시 (hf auth login 선행)
$env:PYTHONUTF8 = "1"
reachy-mini-app-assistant publish .\reachy_mini_peekaboo "커밋 메시지"
```

> ⚠️ Windows에서는 SDK가 한글 소스를 cp949로 읽다 깨질 수 있으므로 `check`/`publish` 전에 반드시 `$env:PYTHONUTF8 = "1"`을 설정하세요.

단계별 상세 절차(토큰 발급, 로그인, 재배포)와 트러블슈팅은 [DEPLOY_peekaboo.md](app/peekaboo/DEPLOY_peekaboo.md)를 참고하세요.

## 기능 개발 구조 (팀 분업)

최종 통합 앱 **desk companion**의 기능들을 팀원별로 나누어 개발합니다.
로봇이 HF 앱 스토어에서 앱을 설치할 때 **해당 앱 패키지 하나만 pip 설치**되므로,
기능 코드는 처음부터 통합 앱 패키지 안(`features/`)에서 개발합니다.
(통합 시점에 import 경로가 바뀌지 않습니다.)

```
oss_reachymini/
├── apps/
│   └── reachy_mini_desk_companion/              # 최종 통합 앱 (배포 단위)
│       ├── pyproject.toml                       # 패키지 정의 + entry point
│       ├── README.md                            # HF Space 카드
│       ├── index.html / style.css               # Space 랜딩 페이지 (루트 필수)
│       └── reachy_mini_desk_companion/          # 파이썬 패키지
│           ├── main.py                          # ReachyMiniDeskCompanion — 상태 머신
│           │                                    #  (슬립 → 웨이크업 → 데스크 파트너 → 수면 복귀)
│           └── features/
│               ├── perception/                  # 🧠 인지·감지 (TODO Phase 1)
│               │   ├── wake_word/               #   웨이크 워드 감지
│               │   ├── sound_doa/               #   음원 방향 추적 (reSpeaker 마이크 어레이)
│               │   └── face_tracking/           #   안면 인식·3D 좌표화, 착석 감지 (CSI 카메라)
│               ├── motion/                      # 🦾 기구 제어·모션 (TODO Phase 2)
│               │   ├── look_at/                 #   타겟 추적 시선 제어 (부드러운 궤적)
│               │   ├── gestures/                #   끄덕임, 기지개 웨이크업, 인사 모션
│               │   └── emotion_antenna/         #   감정별 안테나 제어 (기쁨·집중·수면)
│               ├── conversation/                # 🗣️ 대화형 AI (TODO Phase 3)
│               │   ├── speech/                  #   VAD → STT → TTS 파이프라인
│               │   └── llm_agent/               #   LLM 응답 생성·대화 관리
│               ├── services/                    # 🔌 외부 연동 (TODO Phase 3)
│               │   ├── calendar/                #   구글 캘린더 일정 브리핑
│               │   ├── weather/                 #   날씨·온습도 추천 멘트
│               │   └── pomodoro/                #   뽀모도로 집중 모드 타이머
│               └── safety/                      # 🛡️ 안전 장치 (TODO Phase 5)
│                                                #   안전 토크, 충돌 감지, 부재 시 자동 슬립
├── reachy_mini_peekaboo/                        # 첫 데모 앱 (배포 완료, 그대로 유지)
├── study/<이름>/                                # 개인 학습·실험 공간 (자유 형식)
└── docs/                                        # 시나리오·설계 문서
```

### 기능 폴더 내부 규칙

각 기능 폴더(예: `features/motion/look_at/`)는 아래 형태를 지킵니다:

```
look_at/
├── README.md          # 담당자, 사용법, 의존성, 진행 상태
├── __init__.py        # 공개 API 노출
├── look_at.py         # 모듈 본체 — 통합 앱(main.py)이 import
└── demo.py            # 단독 실행 데모 — 시뮬 데몬만 띄우면 바로 확인
```

### 협업 규칙

| 규칙 | 내용 |
| :--- | :--- |
| **담당 단위** | `features/` 하위 폴더 1개 = 팀원 1명(팀). 다른 사람 폴더는 PR 없이 수정하지 않는다 |
| **브랜치** | 기능 폴더 단위로 브랜치 생성 (`feature/motion-look-at` 형식) → `develop`으로 PR |
| **모듈 형태** | 본체는 import 가능한 클래스/함수로 작성. `main.py`(상태 머신)가 가져다 쓴다 |
| **단독 데모** | 기능마다 `demo.py` 필수 — 시뮬에서 단독 실행되어야 리뷰·시연 가능 ([SIM.md](SIM.md) 참고) |
| **시뮬 기준 개발** | 실물 로봇 없이도 개발 가능하게 시뮬레이터 기준으로 작성. 하드웨어 의존 기능(마이크 어레이 DoA 등)은 mock 인터페이스를 함께 제공 |
| **공유 상수** | 자세·타이밍 파라미터는 각 모듈 상단 상수로 모은다 (Peekaboo `main.py` 스타일) |
| **인터페이스 합의** | 기능 간 연동(예: perception → motion 시선 전달)은 구현 전에 함수 시그니처를 PR/이슈로 합의 |
| **진행 관리** | 완료 시 [TODO.md](TODO.md) 체크박스 갱신을 PR에 포함 |
| **배포 검증** | 통합 앱 변경 후 `reachy-mini-app-assistant check` 통과 확인 (`PYTHONUTF8=1` 필수) |

## 참고 자료

- Reachy Mini 공식 문서: <https://huggingface.co/docs/reachy_mini/index>
- 앱 제작·배포 블로그: <https://huggingface.co/blog/pollen-robotics/make-and-publish-your-reachy-mini-apps>

## License

Apache-2.0
