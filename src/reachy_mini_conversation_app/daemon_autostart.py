"""Optional auto-start of a stopped remote Reachy Mini daemon backend.

Used only for network connections (REACHY_MINI_HOST=<ip>). Starting the daemon
powers the motors, so it is opt-in via REACHY_MINI_AUTO_START_DAEMON=1.
All failures are logged and reported as a state string — never raised — so the
regular connection flow keeps its existing error handling.
"""

import time
import logging

import httpx


logger = logging.getLogger(__name__)

STATUS_TIMEOUT_S = 3.0
START_POLL_INTERVAL_S = 2.0
DEFAULT_START_TIMEOUT_S = 45.0


def get_daemon_state(host: str, port: int) -> str | None:
    """Return the remote daemon backend state, or None when unreachable."""
    try:
        response = httpx.get(f"http://{host}:{port}/api/daemon/status", timeout=STATUS_TIMEOUT_S)
        response.raise_for_status()
        state = response.json().get("state")
        return state if isinstance(state, str) else None
    except Exception as e:
        logger.debug("Daemon status check failed for %s:%d: %s", host, port, e)
        return None


def ensure_remote_daemon_running(
    host: str,
    port: int,
    *,
    auto_start: bool,
    start_timeout_s: float = DEFAULT_START_TIMEOUT_S,
) -> str:
    """Start a stopped remote daemon backend when auto-start is enabled.

    Returns the final state label: "running", "stopped", "timeout", "unknown",
    or the daemon's own state string for anything else (e.g. "starting").
    """
    state = get_daemon_state(host, port)
    if state is None:
        return "unknown"
    if state == "running":
        return "running"
    if state != "stopped":
        logger.info("Remote daemon state is %r; attempting to connect as-is.", state)
        return state

    if not auto_start:
        logger.warning(
            "Remote daemon at %s:%d is stopped. Start it from the dashboard (http://%s:%d) "
            "or set REACHY_MINI_AUTO_START_DAEMON=1 to start it automatically.",
            host,
            port,
            host,
            port,
        )
        return "stopped"

    logger.info("Remote daemon is stopped; starting it (REACHY_MINI_AUTO_START_DAEMON=1)...")
    try:
        response = httpx.post(
            f"http://{host}:{port}/api/daemon/start",
            params={"wake_up": "false"},
            timeout=STATUS_TIMEOUT_S,
        )
        response.raise_for_status()
    except Exception as e:
        logger.warning("Failed to request daemon start: %s", e)
        return "stopped"

    deadline = time.monotonic() + start_timeout_s
    while time.monotonic() < deadline:
        if get_daemon_state(host, port) == "running":
            logger.info("Remote daemon is running.")
            return "running"
        time.sleep(START_POLL_INTERVAL_S)

    logger.warning("Remote daemon did not reach running state within %.0f s.", start_timeout_s)
    return "timeout"
