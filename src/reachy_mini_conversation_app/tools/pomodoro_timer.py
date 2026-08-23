"""Pomodoro focus/break phase timer, run through the background tool manager.

The model-facing call returns immediately with a start announcement, so the
"지금부터 X분간 집중 시작!" line is always spoken. The countdown itself runs as a
detached background task (call id prefixed with DETACHED_CALL_ID_PREFIX); its
completion is announced by the realtime handler via a plain message item.
"""

import json
import uuid
import asyncio
import logging
from typing import Any, ClassVar

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.tool_constants import DETACHED_CALL_ID_PREFIX
from reachy_mini_conversation_app.tools.background_tool_manager import ToolCallRoutine


logger = logging.getLogger(__name__)

# --- tuning constants ---------------------------------------------------------
DEFAULT_FOCUS_MINUTES = 25
DEFAULT_BREAK_MINUTES = 5
MIN_MINUTES = 1
MAX_MINUTES = 120


class PomodoroTimer(Tool):
    """Start one pomodoro phase (focus or break) and instruct the next step."""

    name = "pomodoro_timer"
    needs_tool_manager: ClassVar[bool] = True
    description = (
        "Start one pomodoro phase timer for focused work. phase='focus' runs a work "
        "period (default 25 min), phase='break' a rest period (default 5 min). "
        "When the user names a duration (e.g. '1분간 집중', '10분만 집중할게'), pass it as "
        "minutes; when they name a break length, pass break_minutes. Omit both for the "
        "25/5 defaults. The call returns immediately with an 'announce' line — say it "
        "verbatim (e.g. '지금부터 1분간 집중 시작!'). The countdown runs in the background "
        "and a separate completion notification will tell you exactly what to say and do "
        "next. Use task_status to report remaining time and task_cancel to stop the timer."
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
            "break_minutes": {
                "type": "number",
                "description": (
                    "Only with phase='focus': the break length in minutes the user asked for, "
                    "used in the end-of-focus announcement and the follow-up break call. Defaults to 5."
                ),
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
        """Start the phase (immediate return) or run the detached countdown (_wait)."""
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

        raw_break_minutes = kwargs.get("break_minutes")
        if raw_break_minutes is None:
            break_minutes = DEFAULT_BREAK_MINUTES
        else:
            try:
                break_minutes = int(round(float(raw_break_minutes)))
            except (TypeError, ValueError):
                return {"error": f"break_minutes must be a number, got {raw_break_minutes!r}"}
        break_minutes = max(MIN_MINUTES, min(MAX_MINUTES, break_minutes))

        cycle = max(1, int(kwargs.get("cycle") or 1))
        total_cycles = max(cycle, int(kwargs.get("total_cycles") or 1))

        tool_manager = kwargs.get("tool_manager")
        if not kwargs.get("_wait") and tool_manager is not None:
            return await self._start_detached_countdown(
                tool_manager, deps, phase, minutes, break_minutes, cycle, total_cycles
            )

        # Detached countdown (or inline fallback when no manager is available).
        logger.info("Pomodoro %s phase started: %d min (set %d/%d)", phase, minutes, cycle, total_cycles)
        # Cancellable by task_cancel; CancelledError must propagate to the manager.
        await asyncio.sleep(minutes * 60)
        return self._completion_result(phase, minutes, break_minutes, cycle, total_cycles)

    async def _start_detached_countdown(
        self,
        tool_manager: Any,
        deps: ToolDependencies,
        phase: str,
        minutes: int,
        break_minutes: int,
        cycle: int,
        total_cycles: int,
    ) -> dict[str, Any]:
        """Spawn the countdown as detached background work and confirm the start."""
        countdown_args = {
            "phase": phase,
            "minutes": minutes,
            "break_minutes": break_minutes,
            "cycle": cycle,
            "total_cycles": total_cycles,
            "_wait": True,
        }
        await tool_manager.start_tool(
            call_id=f"{DETACHED_CALL_ID_PREFIX}{uuid.uuid4().hex}",
            tool_call_routine=ToolCallRoutine(
                tool_name=self.name,
                args_json_str=json.dumps(countdown_args),
                deps=deps,
            ),
            is_idle_tool_call=False,
        )

        if phase == "focus":
            announce = f"지금부터 {minutes}분간 집중 시작!"
            next_action = (
                f'사용자에게 "{announce}"라고 그대로 말하라. 다른 말은 덧붙이지 말라. '
                "집중이 끝나면 별도의 완료 알림이 온다."
            )
        else:
            announce = f"{minutes}분 휴식 시작!"
            next_action = (
                "휴식 타이머가 시작되었다. 직전에 휴식 안내(스트레칭 등)를 이미 했다면 "
                f'아무 말도 덧붙이지 말고, 안 했다면 "{announce}"라고만 짧게 말하라.'
            )

        return {
            "status": f"{phase}_started",
            "cycle": cycle,
            "total_cycles": total_cycles,
            "minutes": minutes,
            "break_minutes": break_minutes,
            "announce": announce,
            "next_action": next_action,
        }

    @staticmethod
    def _completion_result(
        phase: str,
        minutes: int,
        break_minutes: int,
        cycle: int,
        total_cycles: int,
    ) -> dict[str, Any]:
        """Build the end-of-phase payload with the exact announcement to speak."""
        if phase == "focus":
            announce = f"집중 시간 {minutes}분이 끝났어요! {break_minutes}분간 가볍게 스트레칭하세요."
            return {
                "status": "focus_complete",
                "cycle": cycle,
                "total_cycles": total_cycles,
                "minutes": minutes,
                "break_minutes": break_minutes,
                "announce": announce,
                "next_action": (
                    f'집중 시간이 끝났다. 사용자에게 "{announce}"라고 그대로 말하고, 즉시 '
                    f"pomodoro_timer(phase='break', minutes={break_minutes}, cycle={cycle}, "
                    f"total_cycles={total_cycles})를 호출해 휴식 타이머를 시작하라."
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
