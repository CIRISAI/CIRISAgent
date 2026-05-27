"""Tests for QA Runner authenticate-with-retry behavior.

Pin the contract added in fix for the postgres-resume race: when
/v1/setup/complete returns 200, the server still spends 10+ seconds
finishing its RESUME cycle on the postgres backend before /v1/auth/login
is reachable. The pre-fix single-shot timeout=5 call always tripped that
race and declared the backend failed.

These tests pin the retry behavior at the unit level so the race fix
can't silently regress. They're fast (no network, no real server).
"""

from typing import List
from unittest.mock import MagicMock, patch

import pytest
import requests

from tools.qa_runner.config import QAConfig
from tools.qa_runner.server import APIServerManager

pytestmark = pytest.mark.timeout(30)


def _make_manager(*, startup_timeout: float = 30.0) -> APIServerManager:
    config = QAConfig(
        base_url="http://localhost:18080",
        api_port=18080,
        mock_llm=True,
        admin_username="admin",
        admin_password="testpw",
        server_startup_timeout=startup_timeout,
    )
    manager = APIServerManager(config, modules=[])
    return manager


def _make_response(status_code: int, json_body: dict | None = None, text: str = ""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = text
    return resp


class TestAuthenticateWithRetry:
    """The retry contract: keep trying while the runtime resume is in
    flight; fail fast on real auth errors; respect the budget."""

    def test_immediate_success_returns_token(self):
        manager = _make_manager()
        ok = _make_response(200, json_body={"access_token": "abc123"})
        with patch("tools.qa_runner.server.requests.post", return_value=ok) as mock_post, patch(
            "tools.qa_runner.server.time.time", side_effect=[0.0, 0.0]
        ):
            token = manager._authenticate_with_retry("testpw", start_time=0.0)
        assert token == "abc123"
        assert mock_post.call_count == 1

    def test_recovers_after_timeout(self):
        """The race fix's load-bearing test: first call times out (postgres
        resume blocking auth), retry succeeds. Pre-fix this was a hard
        failure; the postgres backend never recovered."""
        manager = _make_manager()
        ok = _make_response(200, json_body={"access_token": "after-retry"})
        responses: List = [
            requests.exceptions.Timeout("Read timed out"),
            ok,
        ]
        with patch(
            "tools.qa_runner.server.requests.post", side_effect=responses
        ) as mock_post, patch(
            "tools.qa_runner.server.time.sleep"
        ), patch(
            "tools.qa_runner.server.time.time", side_effect=[0.0, 1.0, 2.0, 2.0, 2.0]
        ):
            token = manager._authenticate_with_retry("testpw", start_time=0.0)
        assert token == "after-retry"
        assert mock_post.call_count == 2

    def test_recovers_after_connection_error(self):
        """Postgres backend can briefly stop accepting connections during
        the resume phase swap — retry should ride through."""
        manager = _make_manager()
        ok = _make_response(200, json_body={"access_token": "after-conn-err"})
        with patch(
            "tools.qa_runner.server.requests.post",
            side_effect=[
                requests.exceptions.ConnectionError("connection reset"),
                requests.exceptions.ConnectionError("connection refused"),
                ok,
            ],
        ) as mock_post, patch("tools.qa_runner.server.time.sleep"), patch(
            "tools.qa_runner.server.time.time",
            side_effect=[0.0, 1.0, 2.0, 3.0, 3.0, 3.0],
        ):
            token = manager._authenticate_with_retry("testpw", start_time=0.0)
        assert token == "after-conn-err"
        assert mock_post.call_count == 3

    def test_recovers_after_5xx(self):
        """5xx (e.g. 503 service-not-ready-yet) is the documented
        transient signature — retry."""
        manager = _make_manager()
        ok = _make_response(200, json_body={"access_token": "after-503"})
        with patch(
            "tools.qa_runner.server.requests.post",
            side_effect=[
                _make_response(503, text="service unavailable"),
                _make_response(503, text="service unavailable"),
                ok,
            ],
        ) as mock_post, patch("tools.qa_runner.server.time.sleep"), patch(
            "tools.qa_runner.server.time.time",
            side_effect=[0.0, 1.0, 2.0, 3.0, 3.0, 3.0],
        ):
            token = manager._authenticate_with_retry("testpw", start_time=0.0)
        assert token == "after-503"
        assert mock_post.call_count == 3

    @pytest.mark.parametrize("status", [401, 403, 422])
    def test_fail_fast_on_real_auth_error(self, status):
        """401 / 403 / 422 are NOT transient — they don't become 200 by
        retrying. The race fix must not paper over genuine credential
        problems with infinite retries."""
        manager = _make_manager()
        bad = _make_response(status, text="bad creds")
        with patch(
            "tools.qa_runner.server.requests.post", return_value=bad
        ) as mock_post, patch("tools.qa_runner.server.time.sleep"), patch(
            "tools.qa_runner.server.time.time", side_effect=[0.0, 0.0, 0.0]
        ), patch.object(
            manager, "_report_first_run_diagnostics"
        ) as mock_diag:
            token = manager._authenticate_with_retry("testpw", start_time=0.0)
        assert token is None
        assert mock_post.call_count == 1  # MUST be one — no retry on real errors
        mock_diag.assert_called_once()

    def test_budget_exhausted_returns_none(self):
        """When server_startup_timeout passes without success, give up
        rather than spin forever."""
        manager = _make_manager(startup_timeout=2.0)
        time_iter = iter([0.0, 0.5, 1.0, 1.5, 2.5, 2.5, 2.5])
        with patch(
            "tools.qa_runner.server.requests.post",
            side_effect=requests.exceptions.Timeout("timeout"),
        ) as mock_post, patch("tools.qa_runner.server.time.sleep"), patch(
            "tools.qa_runner.server.time.time", side_effect=lambda: next(time_iter)
        ), patch.object(
            manager, "_report_first_run_diagnostics"
        ) as mock_diag:
            token = manager._authenticate_with_retry("testpw", start_time=0.0)
        assert token is None
        # Budget = 2s, we tried at least once before time exceeded.
        assert mock_post.call_count >= 1
        # Diagnostics emitted on final failure
        mock_diag.assert_called_once()

    def test_unexpected_exception_keeps_retrying(self):
        """Belt-and-suspenders defensiveness: unexpected exceptions
        within the budget shouldn't kill the retry loop. The transient
        envelope is wide on purpose (SSL flakes, weird DNS, etc.)."""
        manager = _make_manager()
        ok = _make_response(200, json_body={"access_token": "after-weirdness"})
        with patch(
            "tools.qa_runner.server.requests.post",
            side_effect=[
                RuntimeError("something weird"),
                ok,
            ],
        ) as mock_post, patch("tools.qa_runner.server.time.sleep"), patch(
            "tools.qa_runner.server.time.time", side_effect=[0.0, 1.0, 2.0, 2.0, 2.0]
        ):
            token = manager._authenticate_with_retry("testpw", start_time=0.0)
        assert token == "after-weirdness"
        assert mock_post.call_count == 2

    def test_per_attempt_timeout_at_least_10s(self):
        """Each retry attempt uses a per-request timeout that's larger
        than the original buggy timeout=5 — otherwise the race still
        loses on a single attempt that happens to land mid-resume."""
        manager = _make_manager()
        ok = _make_response(200, json_body={"access_token": "ok"})
        with patch(
            "tools.qa_runner.server.requests.post", return_value=ok
        ) as mock_post, patch(
            "tools.qa_runner.server.time.time", side_effect=[0.0, 0.0]
        ):
            manager._authenticate_with_retry("testpw", start_time=0.0)
        kwargs = mock_post.call_args.kwargs
        assert kwargs.get("timeout", 0) >= 10, (
            f"per-attempt timeout {kwargs.get('timeout')!r} is too tight; "
            "the original timeout=5 raced the postgres resume cycle"
        )
