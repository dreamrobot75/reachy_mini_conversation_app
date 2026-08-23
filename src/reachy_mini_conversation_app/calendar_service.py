"""Google Calendar OAuth service and event fetching."""

import logging
import datetime
from typing import Any, Optional
from pathlib import Path


logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CREDENTIALS_PATHS = [
    Path("credentials.json"),
    Path("google_credentials.json"),
    Path("client_secret.json"),
]
TOKEN_PATH = Path(".google_token.json")


class GoogleCalendarService:
    """Singleton service for Google Calendar OAuth 2.0 authentication and event retrieval."""

    _instance: Optional["GoogleCalendarService"] = None

    def __init__(self) -> None:
        """Initialize GoogleCalendarService instance."""
        self._service: Any = None

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
        return self._get_credentials_path() is not None

    def save_client_credentials(self, client_id: str, client_secret: str) -> None:
        """Save Client ID and Client Secret into credentials.json."""
        import json

        data = {
            "installed": {
                "client_id": client_id,
                "project_id": "reachy-mini-app",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": client_secret,
                "redirect_uris": [
                    "http://localhost",
                    "http://localhost:7860/api/calendar/oauth2callback",
                ],
            }
        }
        Path("credentials.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _get_credentials_path(self) -> Optional[Path]:
        """Find existing credentials file."""
        for p in CREDENTIALS_PATHS:
            if p.exists():
                return p
        return None

    def get_auth_url(
        self, redirect_uri: str = "http://localhost:7860/api/calendar/oauth2callback"
    ) -> tuple[Optional[str], Optional[str]]:
        """Generate OAuth 2.0 authorization URL for browser flow."""
        cred_file = self._get_credentials_path()
        if cred_file is None:
            return None, "credentials.json 파일이 필요합니다. Client ID와 Secret을 먼저 입력해 주세요."
        try:
            import importlib

            flow_mod = importlib.import_module("google_auth_oauthlib.flow")
            installed_flow_cls = getattr(flow_mod, "InstalledAppFlow")
            flow = installed_flow_cls.from_client_secrets_file(str(cred_file), SCOPES, redirect_uri=redirect_uri)
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
            return str(auth_url), None
        except Exception as e:
            logger.error("Failed generating OAuth URL: %s", e)
            return None, str(e)

    def exchange_code(
        self, code: str, redirect_uri: str = "http://localhost:7860/api/calendar/oauth2callback"
    ) -> bool:
        """Exchange authorization code for token and persist."""
        cred_file = self._get_credentials_path()
        if cred_file is None:
            return False
        try:
            import importlib

            flow_mod = importlib.import_module("google_auth_oauthlib.flow")
            installed_flow_cls = getattr(flow_mod, "InstalledAppFlow")
            flow = installed_flow_cls.from_client_secrets_file(str(cred_file), SCOPES, redirect_uri=redirect_uri)
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

    def get_events(
        self,
        target_date: str = "today",
        calendar_id: str = "primary",
        max_results: int = 10,
    ) -> dict[str, Any]:
        """Fetch calendar events for the specified date."""
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
            return {
                "authenticated": False,
                "date": query_date.isoformat(),
                "event_count": 0,
                "events": [],
                "message": "구글 캘린더 OAuth 인증이 필요합니다. Settings 화면에서 'Google 계정 로그인' 버튼을 눌러 연동해 주세요.",
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
                return {
                    "authenticated": False,
                    "date": query_date.isoformat(),
                    "event_count": 0,
                    "events": [],
                    "message": "구글 인증 토큰이 만료되었습니다. Settings 화면에서 다시 로그인해 주세요.",
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
            return {
                "authenticated": True,
                "error": str(e),
                "date": query_date.isoformat(),
                "event_count": 0,
                "events": [],
                "message": f"구글 캘린더 일정을 조회하는 중 오류가 발생했습니다: {e}",
            }
