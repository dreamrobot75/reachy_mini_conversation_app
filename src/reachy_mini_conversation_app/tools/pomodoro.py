"""Pomodoro focus/break phase timer, run through the background tool manager."""

import asyncio
import logging
from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies


logger = logging.getLogger(__name__)

# --- tuning constants ---------------------------------------------------------
DEFAULT_FOCUS_MINUTES = 25
DEFAULT_BREAK_MINUTES = 5
MIN_MINUTES = 1
MAX_MINUTES = 120


class PomodoroTimer(Tool):
    """Run one pomodoro phase (focus or break) and instruct the next step."""

    name = "pomodoro_timer"
    description = (
        "Start one pomodoro phase timer for focused work. phase='focus' runs a work "
        "period (default 25 min), phase='break' a rest period (default 5 min). The tool "
        "completes when the phase ends and its result tells you exactly what to do next "
        "(announce, auto-start the break, or ask about the next set). Use task_status to "
        "report remaining time and task_cancel to stop the timer."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "phase": {
                "type": "string",
                "enum": ["focus", "break"],
                "description": "Which pomodoro phase to time.",
            },
            "minutes": {
                "type": "number",
                "description": "Phase length in minutes. Defaults to 25 for focus, 5 for break.",
            },
            "cycle": {
                "type": "integer",
                "description": "Current set number, starting at 1.",
            },
            "total_cycles": {
                "type": "integer",
                "description": "Total number of sets the user asked for. Defaults to 1.",
            },
        },
        "required": ["phase"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Sleep through one phase and return the follow-up instruction."""
        phase = kwargs.get("phase")
        if phase not in ("focus", "break"):
            return {"error": "phase must be 'focus' or 'break'"}

        raw_minutes = kwargs.get("minutes")
        if raw_minutes is None:
            minutes = DEFAULT_FOCUS_MINUTES if phase == "focus" else DEFAULT_BREAK_MINUTES
        else:
            try:
                minutes = int(round(float(raw_minutes)))
            except (TypeError, ValueError):
                return {"error": f"minutes must be a number, got {raw_minutes!r}"}
        minutes = max(MIN_MINUTES, min(MAX_MINUTES, minutes))

        cycle = max(1, int(kwargs.get("cycle") or 1))
        total_cycles = max(cycle, int(kwargs.get("total_cycles") or 1))

        logger.info("Pomodoro %s phase started: %d min (set %d/%d)", phase, minutes, cycle, total_cycles)
        # Cancellable by task_cancel; CancelledError must propagate to the manager.
        await asyncio.sleep(minutes * 60)

        if phase == "focus":
            return {
                "status": "focus_complete",
                "cycle": cycle,
                "total_cycles": total_cycles,
                "minutes": minutes,
                "next_action": (
                    "집중 시간이 끝났다. 사용자에게 수고했다고 명확히 알리고, 즉시 "
                    f"pomodoro_timer(phase='break', cycle={cycle}, total_cycles={total_cycles})를 "
                    "호출해 휴식 타이머를 시작하라."
                ),
            }

        if cycle < total_cycles:
            return {
                "status": "break_complete",
                "cycle": cycle,
                "total_cycles": total_cycles,
                "minutes": minutes,
                "next_action": (
                    f"휴식이 끝났다. 다음 세트({cycle + 1}/{total_cycles})를 시작할지 사용자에게 "
                    f"물어보고, 동의하면 pomodoro_timer(phase='focus', cycle={cycle + 1}, "
                    f"total_cycles={total_cycles})를 호출하라."
                ),
            }

        return {
            "status": "pomodoro_done",
            "cycle": cycle,
            "total_cycles": total_cycles,
            "minutes": minutes,
            "next_action": f"뽀모도로 {total_cycles}세트를 모두 마쳤다. 사용자에게 완주를 축하하고 마무리 인사를 하라.",
        }
