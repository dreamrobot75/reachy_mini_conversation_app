"""Google Calendar schedule and event retrieval tool for Reachy Mini."""

import logging
from typing import Any

from reachy_mini_conversation_app.calendar_service import GoogleCalendarService
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)


class GetSchedule(Tool):
    """Retrieve upcoming schedule and events from Google Calendar via OAuth."""

    name = "get_schedule"
    description = (
        "Get upcoming schedule, meetings, calendar events, and appointments from Google Calendar. "
        "Call this directly whenever the user asks for today's schedule, tomorrow's plan, "
        "upcoming meetings, or what is on their calendar."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "target_date": {
                "type": "string",
                "description": (
                    "Target date to query: 'today' for today's events, 'tomorrow' for tomorrow, "
                    "or an ISO date string 'YYYY-MM-DD'. Defaults to 'today'."
                ),
                "default": "today",
            },
            "calendar_id": {
                "type": "string",
                "description": "Google Calendar ID to query. Defaults to 'primary'.",
                "default": "primary",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of events to retrieve. Defaults to 10.",
                "default": 10,
            },
        },
        "required": [],
    }

    def __init__(self) -> None:
        """Initialize Google Calendar schedule tool."""
        self._service = GoogleCalendarService.get_instance()

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Fetch and return calendar schedule."""
        target_date = str(kwargs.get("target_date") or "today").strip()
        calendar_id = str(kwargs.get("calendar_id") or "primary").strip()
        max_results = int(kwargs.get("max_results") or 10)

        logger.info("Tool call: get_schedule target_date=%s calendar_id=%s", target_date, calendar_id)
        result = self._service.get_events(
            target_date=target_date,
            calendar_id=calendar_id,
            max_results=max_results,
        )
        return result
