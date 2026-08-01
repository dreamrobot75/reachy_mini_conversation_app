# 로봇 데몬 연결 대상 .env 설정 — 설계 문서

- **작성일**: 2026-08-01
- **상태**: 설계 승인됨
- **배경**: 앱이 `ReachyMini()`를 인자 없이 호출해 SDK auto 모드(localhost 시도 →
  `reachy-mini.local` 폴백)에만 의존한다. 실물(192.168.0.144)과 시뮬레이터를
  오가는 팀 개발 환경에서 연결 대상을 `.env`로 명시할 수 있어야 한다.

## 결정

`REACHY_MINI_HOST` 단일 변수 중심 (승인된 A안):

| .env 설정 | ReachyMini 인자 | 동작 |
| :--- | :--- | :--- |
| (미설정/빈 값) | 기본값 그대로 | 기존과 동일 — SDK `auto` |
| `REACHY_MINI_HOST=sim` 또는 `localhost` | `connection_mode="localhost_only"` | 시뮬/로컬 데몬 전용. 네트워크 실물로 폴백하는 사고 방지 |
| `REACHY_MINI_HOST=<IP/호스트명>` | `connection_mode="network"`, `host=<값>` | 해당 주소의 실물 데몬 접속 |

- `REACHY_MINI_PORT` (선택, 기본 8000). 숫자가 아니거나 범위 밖이면 경고 후 8000.
- 미디어는 SDK `media_backend="default"`의 자동 감지(원격이면 WebRTC)를 그대로 사용.

## 컴포넌트

- **config.py**: `REACHY_MINI_HOST`/`REACHY_MINI_PORT` env 읽기 + 순수 함수
  `resolve_daemon_connection(host_value, port_value) -> DaemonConnection`
  (`host: str | None`, `port: int`, `connection_mode: str | None` — None이면 SDK 기본값 사용).
  `Config` 속성과 `refresh_runtime_config_from_env()` 갱신 포함.
- **main.py**: `robot_kwargs`에 resolve 결과를 반영하고
  "Connecting to Reachy Mini daemon: <mode> <host>:<port>" 한 줄 로그.
- **.env.example**: 실물/시뮬 두 가지 예시 주석 블록 (`192.168.0.144` 예시 포함).

## 오류 처리

- 접속 실패는 기존 main.py의 TimeoutError/ConnectionError 처리(로그 + 종료)를 그대로 사용.
- 포트 파싱 실패는 기동을 막지 않고 기본값 폴백 + 경고.

## 테스트

`resolve_daemon_connection` 순수 함수 유닛 테스트: 미설정/sim/localhost/IP/포트 파싱
실패 케이스. 로봇 연결 자체는 수동 확인 (시뮬 데몬, 실물 192.168.0.144).

## 범위 외

UI에서의 연결 대상 전환, 데몬 자동 기동(`spawn_daemon`), mDNS 탐색 개선.
