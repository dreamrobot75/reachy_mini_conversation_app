"""Google Calendar OAuth service and event fetching."""

import os
import logging
import datetime
from typing import Any, Optional
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
GOOGLE_OAUTH_CLIENT_ID_ENV = "GOOGLE_OAUTH_CLIENT_ID"
GOOGLE_OAUTH_CLIENT_SECRET_ENV = "GOOGLE_OAUTH_CLIENT_SECRET"
CREDENTIALS_PATHS = [
    Path("credentials.json"),
    Path("google_credentials.json"),
    Path("client_secret.json"),
]
TOKEN_PATH = Path(".google_token.json")

DEFAULT_SCHEDULE_EVENTS: list[dict[str, str]] = [
    {
        "summary": "팀 데일리 스크럼",
        "start_time": "10:00",
        "end_time": "10:30",
        "location": "온라인 (Google Meet)",
        "description": "어제 진행 상황 공유, 오늘 목표 설정 및 블로커 점검",
    },
    {
        "summary": "Reachy Mini AI 대화 모델 기술 리뷰",
        "start_time": "13:30",
        "end_time": "14:30",
        "location": "회의실 A",
        "description": "실시간 음성 대화 지연시간 개선 및 신규 도구(Tool) 동작 데모",
    },
    {
        "summary": "신규 인터랙션 기획 브레인스토밍",
        "start_time": "15:00",
        "end_time": "16:00",
        "location": "라운지",
        "description": "로봇 감정 표현 및 제스처 동작 추가 아이디어 회의",
    },
    {
        "summary": "리치 미니와 함께하는 스트레칭 & 티타임",
        "start_time": "16:30",
        "end_time": "17:00",
        "location": "휴게실",
        "description": "뽀모도로 타이머 휴식 및 가벼운 대화 시간",
    },
    {
        "summary": "오픈소스 출품 보고서 작성 및 최종 점검",
        "start_time": "18:00",
        "end_time": "19:00",
        "location": "연구실",
        "description": "중복수혜 확인서 및 프로젝트 산출물 문서 마무리",
    },
]


class GoogleCalendarService:
    """Singleton service for Google Calendar OAuth 2.0 authentication and event retrieval."""

    _instance: Optional["GoogleCalendarService"] = None

    def __init__(self) -> None:
        """Initialize GoogleCalendarService instance."""
        self._service: Any = None
        self._pending_flow: tuple[str, InstalledAppFlow] | None = None

    @classmethod
    def get_instance(cls) -> "GoogleCalendarService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_authenticated(self) -> bool:
        """Check if valid Google Calendar OAuth token exists."""
        return TOKEN_PATH.exists()

    def has_credentials(self) -> bool:
        """Check if client credentials JSON exists."""
        return self._get_credentials_path() is not None or self._get_environment_credentials() is not None

    def _get_credentials_path(self) -> Optional[Path]:
        """Find existing credentials file."""
        for p in CREDENTIALS_PATHS:
            if p.exists():
                return p
        return None

    def _get_environment_credentials(self) -> tuple[str, str] | None:
        """Return server-managed Google OAuth credentials when configured."""
        client_id = (os.getenv(GOOGLE_OAUTH_CLIENT_ID_ENV) or "").strip()
        client_secret = (os.getenv(GOOGLE_OAUTH_CLIENT_SECRET_ENV) or "").strip()
        if client_id and client_secret:
            return client_id, client_secret
        return None

    def get_auth_url(
        self, redirect_uri: str = "http://localhost:7860/api/calendar/oauth2callback"
    ) -> tuple[Optional[str], Optional[str]]:
        """Generate OAuth 2.0 authorization URL for browser flow."""
        credentials_path = self._get_credentials_path()
        environment_credentials = self._get_environment_credentials()
        if credentials_path is None and environment_credentials is None:
            return (
                None,
                "서버에 Google OAuth 설정이 없습니다. GOOGLE_OAUTH_CLIENT_ID와 GOOGLE_OAUTH_CLIENT_SECRET을 설정해 주세요.",
            )
        try:
            if credentials_path is not None:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_path),
                    SCOPES,
                    redirect_uri=redirect_uri,
                )
            else:
                assert environment_credentials is not None
                client_id, client_secret = environment_credentials
                flow = InstalledAppFlow.from_client_config(
                    {
                        "web": {
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                            "redirect_uris": [redirect_uri],
                        }
                    },
                    SCOPES,
                    redirect_uri=redirect_uri,
                )
            auth_url, state = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
            self._pending_flow = state, flow
            return str(auth_url), None
        except Exception as e:
            logger.error("Failed generating OAuth URL: %s", e)
            return None, str(e)

    def exchange_code(self, code: str, state: str) -> bool:
        """Exchange authorization code for token and persist."""
        if self._pending_flow is None or self._pending_flow[0] != state:
            logger.warning("Rejected Google OAuth callback with unknown state")
            return False
        _, flow = self._pending_flow
        self._pending_flow = None
        try:
            flow.fetch_token(code=code)
            creds = flow.credentials
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            logger.info("Successfully saved Google OAuth token to %s", TOKEN_PATH)
            return True
        except Exception as e:
            logger.error("Failed exchanging authorization code: %s", e)
            return False

    def get_credentials(self) -> Any:
        """Load or refresh OAuth 2.0 credentials."""
        try:
            import importlib

            oauth_creds_mod = importlib.import_module("google.oauth2.credentials")
            flow_mod = importlib.import_module("google_auth_oauthlib.flow")
            req_mod = importlib.import_module("google.auth.transport.requests")

            credentials_cls = getattr(oauth_creds_mod, "Credentials")
            installed_flow_cls = getattr(flow_mod, "InstalledAppFlow")
            request_cls = getattr(req_mod, "Request")

            creds = None
            if TOKEN_PATH.exists():
                try:
                    creds = credentials_cls.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
                except Exception as e:
                    logger.warning("Error loading token file: %s", e)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(request_cls())
                    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
                else:
                    cred_file = self._get_credentials_path()
                    if cred_file is None:
                        return None
                    flow = installed_flow_cls.from_client_secrets_file(str(cred_file), SCOPES)
                    creds = flow.run_local_server(port=0)
                    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as e:
            logger.error("Failed obtaining Google Calendar credentials: %s", e)
            return None

    def set_access_token(self, token: str, expires_in: int = 3600) -> None:
        """Save access token received directly from browser OAuth."""
        import json

        data = {
            "token": token,
            "saved_at": datetime.datetime.now().isoformat(),
            "expires_in": expires_in,
            "scopes": SCOPES,
        }
        TOKEN_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Saved Google Calendar access token to %s", TOKEN_PATH)

    def logout(self) -> None:
        """Remove saved token and credentials."""
        if TOKEN_PATH.exists():
            try:
                TOKEN_PATH.unlink()
            except Exception as e:
                logger.warning("Failed deleting token file: %s", e)

    def get_access_token(self) -> Optional[str]:
        """Extract access token string from token file or credentials."""
        if TOKEN_PATH.exists():
            try:
                import json

                data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
                return str(data.get("token") or "")
            except Exception as e:
                logger.warning("Failed reading token file: %s", e)
        return None

    def get_default_events(self, query_date: datetime.date) -> list[dict[str, str]]:
        """Return fixed default schedule events for the specified date."""
        events: list[dict[str, str]] = []
        for item in DEFAULT_SCHEDULE_EVENTS:
            events.append(
                {
                    "summary": item["summary"],
                    "start": f"{query_date.isoformat()}T{item['start_time']}:00+09:00",
                    "end": f"{query_date.isoformat()}T{item['end_time']}:00+09:00",
                    "location": item["location"],
                    "description": item["description"],
                }
            )
        return events

    def get_events(
        self,
        target_date: str = "today",
        calendar_id: str = "primary",
        max_results: int = 10,
    ) -> dict[str, Any]:
        """Fetch calendar events for the specified date, falling back to default schedules."""
        today = datetime.date.today()
        if target_date.lower() == "today":
            query_date = today
        elif target_date.lower() == "tomorrow":
            query_date = today + datetime.timedelta(days=1)
        else:
            try:
                query_date = datetime.date.fromisoformat(target_date)
            except ValueError:
                query_date = today

        start_of_day = datetime.datetime.combine(query_date, datetime.time.min).isoformat() + "Z"
        end_of_day = datetime.datetime.combine(query_date, datetime.time.max).isoformat() + "Z"

        token = self.get_access_token()
        if not token:
            creds = self.get_credentials()
            if creds and hasattr(creds, "token") and creds.token:
                token = str(creds.token)

        if not token:
            default_events = self.get_default_events(query_date)[:max_results]
            date_str = "오늘" if query_date == today else f"{query_date.month}월 {query_date.day}일"
            event_summaries = [
                f"{e['summary']} ({e['start'][11:16] if 'T' in e['start'] else '종일'})" for e in default_events
            ]
            msg = f"{date_str} 총 {len(default_events)}건의 일정이 있습니다: {', '.join(event_summaries)}"
            return {
                "authenticated": False,
                "is_default": True,
                "date": query_date.isoformat(),
                "event_count": len(default_events),
                "events": default_events,
                "message": msg,
            }

        try:
            import httpx

            headers = {"Authorization": f"Bearer {token}"}
            params = {
                "timeMin": start_of_day,
                "timeMax": end_of_day,
                "maxResults": str(max_results),
                "singleEvents": "true",
                "orderBy": "startTime",
            }
            url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
            resp = httpx.get(url, headers=headers, params=params, timeout=10.0)

            if resp.status_code == 401:
                # Token expired
                self.logout()
                default_events = self.get_default_events(query_date)[:max_results]
                date_str = "오늘" if query_date == today else f"{query_date.month}월 {query_date.day}일"
                event_summaries = [
                    f"{e['summary']} ({e['start'][11:16] if 'T' in e['start'] else '종일'})" for e in default_events
                ]
                msg = f"{date_str} 총 {len(default_events)}건의 일정이 있습니다: {', '.join(event_summaries)}"
                return {
                    "authenticated": False,
                    "is_default": True,
                    "date": query_date.isoformat(),
                    "event_count": len(default_events),
                    "events": default_events,
                    "message": msg,
                }

            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            formatted_events = []
            for item in items:
                start = item.get("start", {}).get("dateTime", item.get("start", {}).get("date", ""))
                end = item.get("end", {}).get("dateTime", item.get("end", {}).get("date", ""))
                formatted_events.append(
                    {
                        "summary": item.get("summary", "제목 없음"),
                        "start": start,
                        "end": end,
                        "location": item.get("location", ""),
                        "description": item.get("description", ""),
                    }
                )

            date_str = "오늘" if query_date == today else f"{query_date.month}월 {query_date.day}일"
            if not formatted_events:
                msg = f"{date_str} 등록된 일정이 없습니다."
            else:
                event_summaries = [
                    f"{e['summary']} ({e['start'][11:16] if 'T' in e['start'] else '종일'})" for e in formatted_events
                ]
                msg = f"{date_str} 총 {len(formatted_events)}건의 일정이 있습니다: {', '.join(event_summaries)}"

            return {
                "authenticated": True,
                "date": query_date.isoformat(),
                "event_count": len(formatted_events),
                "events": formatted_events,
                "message": msg,
            }
        except Exception as e:
            logger.error("Failed fetching calendar events: %s", e)
            default_events = self.get_default_events(query_date)[:max_results]
            date_str = "오늘" if query_date == today else f"{query_date.month}월 {query_date.day}일"
            event_summaries = [
                f"{e['summary']} ({e['start'][11:16] if 'T' in e['start'] else '종일'})" for e in default_events
            ]
            msg = f"{date_str} 총 {len(default_events)}건의 일정이 있습니다: {', '.join(event_summaries)}"
            return {
                "authenticated": False,
                "error": str(e),
                "is_default": True,
                "date": query_date.isoformat(),
                "event_count": len(default_events),
                "events": default_events,
                "message": msg,
            }
