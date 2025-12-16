"""
Unit tests for local_shutdown helper functions in system.py.

These tests cover the extracted helper functions to reduce cognitive complexity
and improve test coverage.
"""

import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.adapters.api.routes.system import (
    _RESUME_TIMEOUT_SECONDS,
    _check_resume_blocking,
    _check_shutdown_already_in_progress,
    _determine_server_state,
    _get_server_state,
    _is_localhost_request,
)


class TestIsLocalhostRequest:
    """Tests for _is_localhost_request helper."""

    def test_localhost_ipv4(self) -> None:
        """Test 127.0.0.1 is recognized as localhost."""
        request = MagicMock()
        request.client.host = "127.0.0.1"
        assert _is_localhost_request(request) is True

    def test_localhost_ipv6(self) -> None:
        """Test ::1 is recognized as localhost."""
        request = MagicMock()
        request.client.host = "::1"
        assert _is_localhost_request(request) is True

    def test_localhost_name(self) -> None:
        """Test 'localhost' string is recognized."""
        request = MagicMock()
        request.client.host = "localhost"
        assert _is_localhost_request(request) is True

    def test_no_client(self) -> None:
        """Test None client is treated as localhost (internal call)."""
        request = MagicMock()
        request.client = None
        assert _is_localhost_request(request) is True

    def test_remote_ip(self) -> None:
        """Test remote IP is rejected."""
        request = MagicMock()
        request.client.host = "192.168.1.100"
        assert _is_localhost_request(request) is False

    def test_external_ip(self) -> None:
        """Test external IP is rejected."""
        request = MagicMock()
        request.client.host = "8.8.8.8"
        assert _is_localhost_request(request) is False


class TestDetermineServerState:
    """Tests for _determine_server_state helper."""

    def test_shutting_down_takes_priority(self) -> None:
        """Test SHUTTING_DOWN state takes priority over others."""
        runtime = MagicMock()
        runtime._initialized = True
        result = _determine_server_state(runtime, shutdown_in_progress=True, resume_in_progress=True)
        assert result == "SHUTTING_DOWN"

    def test_resuming_state(self) -> None:
        """Test RESUMING state when resume in progress."""
        runtime = MagicMock()
        runtime._initialized = True
        result = _determine_server_state(runtime, shutdown_in_progress=False, resume_in_progress=True)
        assert result == "RESUMING"

    def test_ready_state(self) -> None:
        """Test READY state when initialized."""
        runtime = MagicMock()
        runtime._initialized = True
        result = _determine_server_state(runtime, shutdown_in_progress=False, resume_in_progress=False)
        assert result == "READY"

    def test_initializing_state(self) -> None:
        """Test INITIALIZING state when not initialized."""
        runtime = MagicMock()
        runtime._initialized = False
        result = _determine_server_state(runtime, shutdown_in_progress=False, resume_in_progress=False)
        assert result == "INITIALIZING"

    def test_no_runtime(self) -> None:
        """Test INITIALIZING state when runtime is None."""
        result = _determine_server_state(None, shutdown_in_progress=False, resume_in_progress=False)
        assert result == "INITIALIZING"


class TestGetServerState:
    """Tests for _get_server_state helper."""

    def test_no_runtime(self) -> None:
        """Test server state when runtime is None."""
        result = _get_server_state(None)
        assert result["server_state"] == "STARTING"
        assert result["uptime_seconds"] == 0
        assert result["resume_in_progress"] is False
        assert result["resume_elapsed_seconds"] is None

    def test_ready_runtime(self) -> None:
        """Test server state for ready runtime."""
        runtime = MagicMock()
        runtime._startup_time = time.time() - 100  # 100 seconds ago
        runtime._resume_in_progress = False
        runtime._resume_started_at = None
        runtime._shutdown_in_progress = False
        runtime._initialized = True

        result = _get_server_state(runtime)
        assert result["server_state"] == "READY"
        assert 99 <= result["uptime_seconds"] <= 101  # Allow small timing variance
        assert result["resume_in_progress"] is False
        assert result["resume_elapsed_seconds"] is None

    def test_resuming_runtime(self) -> None:
        """Test server state when resume in progress."""
        runtime = MagicMock()
        runtime._startup_time = time.time() - 10
        runtime._resume_in_progress = True
        runtime._resume_started_at = time.time() - 5  # 5 seconds ago
        runtime._shutdown_in_progress = False
        runtime._initialized = False

        result = _get_server_state(runtime)
        assert result["server_state"] == "RESUMING"
        assert result["resume_in_progress"] is True
        assert 4 <= result["resume_elapsed_seconds"] <= 6

    def test_shutting_down_runtime(self) -> None:
        """Test server state when shutdown in progress."""
        runtime = MagicMock()
        runtime._startup_time = time.time() - 50
        runtime._resume_in_progress = False
        runtime._resume_started_at = None
        runtime._shutdown_in_progress = True
        runtime._initialized = True

        result = _get_server_state(runtime)
        assert result["server_state"] == "SHUTTING_DOWN"


class TestCheckResumeBlocking:
    """Tests for _check_resume_blocking helper."""

    def test_no_resume_in_progress(self) -> None:
        """Test returns None when no resume in progress."""
        runtime = MagicMock()
        runtime._resume_in_progress = False
        state_info = {"server_state": "READY"}

        result = _check_resume_blocking(runtime, state_info)
        assert result is None

    def test_resume_within_timeout(self) -> None:
        """Test returns 409 response when resume is active within timeout."""
        runtime = MagicMock()
        runtime._resume_in_progress = True
        runtime._resume_started_at = time.time() - 5  # 5 seconds ago
        state_info = {"server_state": "RESUMING"}

        result = _check_resume_blocking(runtime, state_info)
        assert result is not None
        assert result.status_code == 409
        # Check content contains expected fields
        import json

        content = json.loads(result.body)
        assert content["status"] == "busy"
        assert "retry_after_ms" in content
        assert content["resume_timeout_seconds"] == _RESUME_TIMEOUT_SECONDS

    def test_resume_exceeded_timeout(self) -> None:
        """Test returns None when resume exceeded timeout (stuck)."""
        runtime = MagicMock()
        runtime._resume_in_progress = True
        runtime._resume_started_at = time.time() - 60  # 60 seconds ago (> 30s timeout)
        state_info = {"server_state": "RESUMING"}

        result = _check_resume_blocking(runtime, state_info)
        assert result is None  # Allow shutdown

    def test_resume_no_start_time(self) -> None:
        """Test handles missing resume_started_at gracefully."""
        runtime = MagicMock()
        runtime._resume_in_progress = True
        runtime._resume_started_at = None
        state_info = {"server_state": "RESUMING"}

        result = _check_resume_blocking(runtime, state_info)
        # elapsed = 0, which is < timeout, so should block
        assert result is not None
        assert result.status_code == 409


class TestCheckShutdownAlreadyInProgress:
    """Tests for _check_shutdown_already_in_progress helper."""

    def test_no_shutdown_in_progress(self) -> None:
        """Test returns None when no shutdown in progress."""
        runtime = MagicMock()
        runtime._shutdown_in_progress = False
        runtime.shutdown_service = None
        state_info = {"server_state": "READY"}

        result = _check_shutdown_already_in_progress(runtime, state_info)
        assert result is None

    def test_shutdown_flag_set(self) -> None:
        """Test returns 202 when shutdown flag is set."""
        runtime = MagicMock()
        runtime._shutdown_in_progress = True
        runtime.shutdown_service = None
        state_info = {"server_state": "SHUTTING_DOWN"}

        result = _check_shutdown_already_in_progress(runtime, state_info)
        assert result is not None
        assert result.status_code == 202
        import json

        content = json.loads(result.body)
        assert content["status"] == "accepted"
        assert "already in progress" in content["reason"]

    def test_shutdown_service_requested(self) -> None:
        """Test returns 202 when shutdown service reports shutdown requested."""
        runtime = MagicMock()
        runtime._shutdown_in_progress = False
        runtime.shutdown_service.is_shutdown_requested.return_value = True
        runtime.shutdown_service.get_shutdown_reason.return_value = "User requested"
        state_info = {"server_state": "READY"}

        result = _check_shutdown_already_in_progress(runtime, state_info)
        assert result is not None
        assert result.status_code == 202
        import json

        content = json.loads(result.body)
        assert "User requested" in content["reason"]

    def test_no_shutdown_service(self) -> None:
        """Test handles missing shutdown service gracefully."""
        runtime = MagicMock()
        runtime._shutdown_in_progress = False
        runtime.shutdown_service = None
        state_info = {"server_state": "READY"}

        result = _check_shutdown_already_in_progress(runtime, state_info)
        assert result is None

    def test_shutdown_service_not_requested(self) -> None:
        """Test returns None when shutdown service says not requested."""
        runtime = MagicMock()
        runtime._shutdown_in_progress = False
        runtime.shutdown_service.is_shutdown_requested.return_value = False
        state_info = {"server_state": "READY"}

        result = _check_shutdown_already_in_progress(runtime, state_info)
        assert result is None


class TestResumeTimeoutConstant:
    """Tests for _RESUME_TIMEOUT_SECONDS constant."""

    def test_timeout_value(self) -> None:
        """Test the resume timeout is set to expected value."""
        assert _RESUME_TIMEOUT_SECONDS == 30.0

    def test_timeout_is_float(self) -> None:
        """Test timeout is a float for precise calculations."""
        assert isinstance(_RESUME_TIMEOUT_SECONDS, float)
