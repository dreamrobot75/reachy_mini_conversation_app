"""Tests for REACHY_MINI_HOST/PORT daemon connection resolution."""

import pytest

from reachy_mini_conversation_app.config import (
    DEFAULT_DAEMON_PORT,
    DaemonConnection,
    resolve_daemon_connection,
)


@pytest.mark.parametrize("host_value", [None, "", "   "])
def test_unset_host_keeps_sdk_auto(host_value: str | None) -> None:
    """No REACHY_MINI_HOST keeps the SDK's auto connection behavior."""
    result = resolve_daemon_connection(host_value, None)
    assert result == DaemonConnection(host=None, port=DEFAULT_DAEMON_PORT, connection_mode=None)


@pytest.mark.parametrize("host_value", ["sim", "SIM", "localhost", "127.0.0.1"])
def test_local_aliases_force_localhost_only(host_value: str) -> None:
    """sim/localhost aliases must never fall back to a network robot."""
    result = resolve_daemon_connection(host_value, None)
    assert result.connection_mode == "localhost_only"
    assert result.host is None


def test_ip_host_uses_network_mode() -> None:
    """An IP/hostname targets the remote daemon explicitly."""
    result = resolve_daemon_connection("192.168.0.144", "8000")
    assert result == DaemonConnection(host="192.168.0.144", port=8000, connection_mode="network")


@pytest.mark.parametrize("port_value", ["abc", "-1", "0", "70000"])
def test_invalid_port_falls_back_to_default(port_value: str) -> None:
    """Bad port values warn and fall back instead of blocking startup."""
    result = resolve_daemon_connection("192.168.0.144", port_value)
    assert result.port == DEFAULT_DAEMON_PORT


def test_custom_port_is_used() -> None:
    """A valid custom port is honored."""
    assert resolve_daemon_connection("sim", "8123").port == 8123
