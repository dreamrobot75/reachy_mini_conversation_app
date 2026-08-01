"""Sound-direction (DoA) gaze support.

Polls the daemon's ``/api/state/doa`` endpoint (reSpeaker mic array) and
exposes the latest speech direction so the app can look toward the speaker.
Degrades silently on daemons without DoA hardware (e.g. the simulator): after
``DOA_FAILURE_LIMIT`` consecutive failed or empty reads the watcher disables
itself with a single warning.

reSpeaker DoA convention: 0 rad = left, pi/2 = front (front/back ambiguous on
the linear array), pi = right. Head yaw convention (``create_head_pose``):
positive = turn left.
"""

import math
import time
import logging
import threading
from typing import Any, Callable

import httpx


logger = logging.getLogger(__name__)

# --- tuning constants ---------------------------------------------------------
DOA_POLL_INTERVAL_S = 0.4
DOA_REQUEST_TIMEOUT_S = 2.0
DOA_FAILURE_LIMIT = 10
MAX_HEAD_YAW_RAD = math.radians(70.0)
DOA_TURN_THRESHOLD_RAD = 0.26  # ~15 deg — smaller changes are not worth a turn
DOA_TURN_COOLDOWN_S = 1.5
GAZE_TURN_DURATION_S = 0.8
WAKE_GAZE_MAX_AGE_S = 10.0


def doa_angle_to_head_yaw(angle: float) -> float:
    """Map a reSpeaker DoA angle onto a clamped head yaw (positive = left)."""
    yaw = math.pi / 2.0 - angle
    return max(-MAX_HEAD_YAW_RAD, min(MAX_HEAD_YAW_RAD, yaw))


def queue_gaze(movement_manager: Any, reachy_mini: Any, yaw: float, duration: float = GAZE_TURN_DURATION_S) -> None:
    """Queue a smooth head turn to the given yaw, reusing the sweep_look pattern."""
    from reachy_mini.utils import create_head_pose
    from reachy_mini_conversation_app.dance_emotion_moves import GotoQueueMove

    current_head_pose = reachy_mini.get_current_head_pose()
    head_joints, antenna_joints = reachy_mini.get_current_joint_positions()
    body_yaw = head_joints[0]
    antennas = (antenna_joints[0], antenna_joints[1])
    target_pose = create_head_pose(0, 0, 0, 0, 0, yaw, degrees=False)
    movement_manager.queue_move(
        GotoQueueMove(
            target_head_pose=target_pose,
            start_head_pose=current_head_pose,
            target_antennas=antennas,
            start_antennas=antennas,
            target_body_yaw=body_yaw,
            start_body_yaw=body_yaw,
            duration=duration,
        )
    )
    movement_manager.set_moving_state(duration)


class SoundDirectionWatcher(threading.Thread):
    """Background poller for the daemon's DoA endpoint."""

    def __init__(
        self,
        host: str,
        port: int,
        on_speech: "Callable[[float], None] | None" = None,
    ) -> None:
        """Initialize the watcher against ``http://{host}:{port}/api/state/doa``."""
        super().__init__(daemon=True, name="doa-watcher")
        self._url = f"http://{host}:{port}/api/state/doa"
        self._on_speech = on_speech
        self._stop_event = threading.Event()
        self._failures = 0
        self._last_speech_angle: "float | None" = None
        self._last_speech_time: "float | None" = None

    def recent_speech_angle(self, max_age_s: float) -> "float | None":
        """Return the last speech DoA angle when it is fresh enough, else None."""
        if self._last_speech_angle is None or self._last_speech_time is None:
            return None
        if time.monotonic() - self._last_speech_time > max_age_s:
            return None
        return self._last_speech_angle

    def stop(self) -> None:
        """Ask the polling loop to exit."""
        self._stop_event.set()

    def run(self) -> None:
        """Poll until stopped or the endpoint proves unavailable."""
        logger.info("Sound direction watcher started (%s)", self._url)
        while not self._stop_event.is_set():
            self._poll_once()
            if self._failures >= DOA_FAILURE_LIMIT:
                logger.warning(
                    "DoA endpoint unavailable after %d attempts; disabling sound-direction gaze.",
                    self._failures,
                )
                return
            self._stop_event.wait(DOA_POLL_INTERVAL_S)

    def _poll_once(self) -> None:
        """Read the endpoint once; record speech direction or count a failure."""
        try:
            response = httpx.get(self._url, timeout=DOA_REQUEST_TIMEOUT_S)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            self._failures += 1
            return

        # Daemons without DoA hardware answer 200 with a null body.
        if not isinstance(payload, dict):
            self._failures += 1
            return

        self._failures = 0
        angle = payload.get("angle")
        if not payload.get("speech_detected") or not isinstance(angle, (int, float)):
            return

        self._last_speech_angle = float(angle)
        self._last_speech_time = time.monotonic()
        if self._on_speech is not None:
            try:
                self._on_speech(float(angle))
            except Exception:
                logger.debug("on_speech callback failed", exc_info=True)


class SpeakerGaze:
    """Turns the head toward detected speech, with hysteresis and cooldown."""

    def __init__(
        self,
        movement_manager: Any,
        reachy_mini: Any,
        is_enabled: Callable[[], bool],
    ) -> None:
        """Wire the gaze controller to the motion system and an enable gate."""
        self._movement_manager = movement_manager
        self._reachy_mini = reachy_mini
        self._is_enabled = is_enabled
        self._last_yaw: "float | None" = None
        self._last_turn_time: "float | None" = None

    def on_speech(self, angle: float) -> None:
        """Queue a head turn toward the speech angle when all gates pass."""
        if not self._is_enabled():
            return
        if not self._movement_manager.is_idle():
            return
        # Face tracking owns the head when active; upstream exposes no public
        # getter, so read the private flag (accepted tradeoff, see design doc).
        if getattr(self._movement_manager, "_head_tracking", False):
            return

        yaw = doa_angle_to_head_yaw(angle)
        now = time.monotonic()
        if self._last_yaw is not None and abs(yaw - self._last_yaw) < DOA_TURN_THRESHOLD_RAD:
            return
        if self._last_turn_time is not None and now - self._last_turn_time < DOA_TURN_COOLDOWN_S:
            return

        try:
            queue_gaze(self._movement_manager, self._reachy_mini, yaw)
        except Exception as e:
            logger.warning("Failed to queue sound-direction gaze: %s", e)
            return
        logger.info("Speaker gaze: turning toward DoA %.2f rad (head yaw %.2f rad)", angle, yaw)
        self._last_yaw = yaw
        self._last_turn_time = now
