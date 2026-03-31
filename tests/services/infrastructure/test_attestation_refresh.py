"""
Tests for attestation periodic refresh and integrity degradation detection.

Covers:
- Periodic attestation refresh loop (_attestation_refresh_loop)
- Integrity degradation detection (_check_integrity_degradation)
- Stale-while-revalidate on the /auth/attestation endpoint
- Emergency shutdown on L1/L2/L4 degradation
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.schemas.services.attestation import AttestationResult


def _make_result(
    binary_ok: bool = True,
    env_ok: bool = True,
    file_integrity_ok: bool = True,
    max_level: int = 4,
    cached_at: datetime | None = None,
    cache_ttl_seconds: int = 3600,
) -> AttestationResult:
    """Build an AttestationResult with controllable integrity flags."""
    return AttestationResult(
        loaded=True,
        key_status="ephemeral",
        attestation_status="verified" if max_level > 0 else "partial",
        binary_ok=binary_ok,
        env_ok=env_ok,
        file_integrity_ok=file_integrity_ok,
        max_level=max_level,
        cached_at=cached_at or datetime.now(timezone.utc),
        cache_ttl_seconds=cache_ttl_seconds,
    )


# ---------------------------------------------------------------------------
# _check_integrity_degradation tests
# ---------------------------------------------------------------------------


class TestCheckIntegrityDegradation:
    """Unit tests for AuthenticationService._check_integrity_degradation."""

    def _make_service(self):
        """Create an AuthenticationService with mocked internals."""
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService.__init__",
            lambda self_inner, *a, **kw: None,
        ):
            from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService

            svc = AuthenticationService.__new__(AuthenticationService)
            svc._baseline_attestation = None
            return svc

    def test_no_baseline_stores_current(self):
        svc = self._make_service()
        current = _make_result()
        svc._check_integrity_degradation(current)
        assert svc._baseline_attestation is current

    def test_no_degradation(self):
        svc = self._make_service()
        svc._baseline_attestation = _make_result()
        current = _make_result()

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.request_global_shutdown"
        ) as mock_shutdown:
            svc._check_integrity_degradation(current)
            mock_shutdown.assert_not_called()

    def test_l1_binary_degradation_triggers_shutdown(self):
        svc = self._make_service()
        svc._baseline_attestation = _make_result(binary_ok=True)
        current = _make_result(binary_ok=False)

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.request_global_shutdown"
        ) as mock_shutdown:
            svc._check_integrity_degradation(current)
            mock_shutdown.assert_called_once()
            call_arg = mock_shutdown.call_args[0][0]
            assert "INTEGRITY DEGRADATION" in call_arg
            assert "L1 binary_ok" in call_arg

    def test_l2_env_degradation_triggers_shutdown(self):
        svc = self._make_service()
        svc._baseline_attestation = _make_result(env_ok=True)
        current = _make_result(env_ok=False)

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.request_global_shutdown"
        ) as mock_shutdown:
            svc._check_integrity_degradation(current)
            mock_shutdown.assert_called_once()
            call_arg = mock_shutdown.call_args[0][0]
            assert "L2 env_ok" in call_arg

    def test_l4_file_integrity_degradation_triggers_shutdown(self):
        svc = self._make_service()
        svc._baseline_attestation = _make_result(file_integrity_ok=True)
        current = _make_result(file_integrity_ok=False)

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.request_global_shutdown"
        ) as mock_shutdown:
            svc._check_integrity_degradation(current)
            mock_shutdown.assert_called_once()
            call_arg = mock_shutdown.call_args[0][0]
            assert "L4 file_integrity_ok" in call_arg

    def test_multiple_degradations_reported(self):
        svc = self._make_service()
        svc._baseline_attestation = _make_result(binary_ok=True, env_ok=True, file_integrity_ok=True)
        current = _make_result(binary_ok=False, env_ok=False, file_integrity_ok=False)

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.request_global_shutdown"
        ) as mock_shutdown:
            svc._check_integrity_degradation(current)
            mock_shutdown.assert_called_once()
            call_arg = mock_shutdown.call_args[0][0]
            assert "L1" in call_arg
            assert "L2" in call_arg
            assert "L4" in call_arg

    def test_baseline_false_to_current_false_no_degradation(self):
        """If baseline was already failing, same failure is NOT degradation."""
        svc = self._make_service()
        svc._baseline_attestation = _make_result(binary_ok=False)
        current = _make_result(binary_ok=False)

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.request_global_shutdown"
        ) as mock_shutdown:
            svc._check_integrity_degradation(current)
            mock_shutdown.assert_not_called()

    def test_improvement_does_not_trigger_shutdown(self):
        """If integrity improves (False -> True), no shutdown."""
        svc = self._make_service()
        svc._baseline_attestation = _make_result(binary_ok=False)
        current = _make_result(binary_ok=True)

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.request_global_shutdown"
        ) as mock_shutdown:
            svc._check_integrity_degradation(current)
            mock_shutdown.assert_not_called()

    def test_network_fields_ignored(self):
        """DNS/HTTPS failures should NOT trigger shutdown (network only)."""
        svc = self._make_service()
        baseline = _make_result()
        baseline.dns_us_ok = True
        baseline.dns_eu_ok = True
        baseline.https_us_ok = True
        svc._baseline_attestation = baseline

        current = _make_result()
        current.dns_us_ok = False
        current.dns_eu_ok = False
        current.https_us_ok = False

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.request_global_shutdown"
        ) as mock_shutdown:
            svc._check_integrity_degradation(current)
            mock_shutdown.assert_not_called()


# ---------------------------------------------------------------------------
# Stale-while-revalidate on get_cached_attestation tests
# ---------------------------------------------------------------------------


class TestGetCachedAttestationStale:
    """Test allow_stale=True returns data during TTL gap."""

    def _make_service(self):
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService.__init__",
            lambda self_inner, *a, **kw: None,
        ):
            from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService

            svc = AuthenticationService.__new__(AuthenticationService)
            svc._attestation_cache = None
            svc._last_known_attestation = None
            svc._attestation_cache_ttl = 3600
            svc._attestation_stale_ttl = 7200
            return svc

    def test_fresh_cache_returned(self):
        svc = self._make_service()
        result = _make_result(cached_at=datetime.now(timezone.utc))
        svc._attestation_cache = result
        svc._get_current_time = lambda: datetime.now(timezone.utc)
        assert svc.get_cached_attestation() is result

    def test_expired_cache_returns_none_without_stale(self):
        svc = self._make_service()
        old_time = datetime.now(timezone.utc) - timedelta(seconds=4000)
        result = _make_result(cached_at=old_time)
        svc._attestation_cache = result
        svc._get_current_time = lambda: datetime.now(timezone.utc)
        assert svc.get_cached_attestation(allow_stale=False) is None

    def test_expired_cache_returns_stale_within_stale_ttl(self):
        svc = self._make_service()
        # 90 minutes old — past 1h TTL but within 2h stale TTL
        old_time = datetime.now(timezone.utc) - timedelta(seconds=5400)
        result = _make_result(cached_at=old_time)
        svc._attestation_cache = result
        svc._get_current_time = lambda: datetime.now(timezone.utc)
        assert svc.get_cached_attestation(allow_stale=True) is result

    def test_past_stale_ttl_returns_none(self):
        svc = self._make_service()
        # 3 hours old — past both TTLs
        old_time = datetime.now(timezone.utc) - timedelta(seconds=10800)
        result = _make_result(cached_at=old_time)
        svc._attestation_cache = result
        svc._get_current_time = lambda: datetime.now(timezone.utc)
        assert svc.get_cached_attestation(allow_stale=True) is None

    def test_none_cache_returns_last_known_when_stale(self):
        svc = self._make_service()
        svc._attestation_cache = None
        svc._last_known_attestation = _make_result()
        assert svc.get_cached_attestation(allow_stale=True) is svc._last_known_attestation


# ---------------------------------------------------------------------------
# Periodic refresh loop tests
# ---------------------------------------------------------------------------


class TestAttestationRefreshLoop:
    """Tests for _attestation_refresh_loop scheduling and error handling."""

    @pytest.mark.asyncio
    async def test_refresh_loop_calls_run_attestation(self):
        """Loop should call run_attestation with force_refresh=True."""
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService.__init__",
            lambda self_inner, *a, **kw: None,
        ):
            from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService

            svc = AuthenticationService.__new__(AuthenticationService)
            svc._attestation_in_progress = False
            svc._started = True
            svc._attestation_refresh_interval = 0.01  # 10ms for test speed
            svc._baseline_attestation = _make_result()

            call_count = 0
            original_started = True

            async def mock_run_attestation(mode="partial", force_refresh=False, **kw):
                nonlocal call_count, original_started
                call_count += 1
                if call_count >= 2:
                    svc._started = False  # Stop after 2 refreshes
                return _make_result()

            svc.run_attestation = mock_run_attestation
            svc._check_integrity_degradation = Mock()

            await svc._attestation_refresh_loop()

            assert call_count >= 2
            assert svc._check_integrity_degradation.call_count >= 2

    @pytest.mark.asyncio
    async def test_refresh_loop_survives_transient_errors(self):
        """Loop should continue after exceptions (not CancelledError)."""
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService.__init__",
            lambda self_inner, *a, **kw: None,
        ):
            from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService

            svc = AuthenticationService.__new__(AuthenticationService)
            svc._attestation_in_progress = False
            svc._started = True
            svc._attestation_refresh_interval = 0.01
            svc._baseline_attestation = _make_result()

            call_count = 0

            async def mock_run_attestation(**kw):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("Transient network error")
                if call_count >= 3:
                    svc._started = False
                return _make_result()

            svc.run_attestation = mock_run_attestation
            svc._check_integrity_degradation = Mock()

            await svc._attestation_refresh_loop()

            # Should have survived the error and continued
            assert call_count >= 3

    @pytest.mark.asyncio
    async def test_refresh_loop_waits_for_in_progress(self):
        """Loop should wait until _attestation_in_progress is False."""
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService.__init__",
            lambda self_inner, *a, **kw: None,
        ):
            from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService

            svc = AuthenticationService.__new__(AuthenticationService)
            svc._attestation_in_progress = True  # Simulate startup in progress
            svc._started = True
            svc._attestation_refresh_interval = 0.01
            svc._baseline_attestation = _make_result()

            call_count = 0

            async def clear_in_progress():
                await asyncio.sleep(0.05)
                svc._attestation_in_progress = False

            async def mock_run_attestation(**kw):
                nonlocal call_count
                call_count += 1
                svc._started = False
                return _make_result()

            svc.run_attestation = mock_run_attestation
            svc._check_integrity_degradation = Mock()

            # Run both concurrently
            await asyncio.gather(
                svc._attestation_refresh_loop(),
                clear_in_progress(),
            )

            assert call_count >= 1

    @pytest.mark.asyncio
    async def test_refresh_loop_cancellation(self):
        """Loop should cleanly exit on CancelledError."""
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService.__init__",
            lambda self_inner, *a, **kw: None,
        ):
            from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService

            svc = AuthenticationService.__new__(AuthenticationService)
            svc._attestation_in_progress = False
            svc._started = True
            svc._attestation_refresh_interval = 100  # Long interval
            svc._baseline_attestation = _make_result()

            async def mock_run_attestation(**kw):
                return _make_result()

            svc.run_attestation = mock_run_attestation
            svc._check_integrity_degradation = Mock()

            task = asyncio.create_task(svc._attestation_refresh_loop())
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


# ---------------------------------------------------------------------------
# Startup baseline capture test
# ---------------------------------------------------------------------------


class TestStartupBaselineCapture:
    @pytest.mark.asyncio
    async def test_run_startup_attestation_sets_baseline(self):
        """run_startup_attestation should store result as _baseline_attestation."""
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService.__init__",
            lambda self_inner, *a, **kw: None,
        ):
            from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService

            svc = AuthenticationService.__new__(AuthenticationService)
            svc._attestation_cache = None
            svc._baseline_attestation = None

            result = _make_result()

            async def mock_run_attestation(**kw):
                return result

            svc.run_attestation = mock_run_attestation

            await svc.run_startup_attestation()

            assert svc._baseline_attestation is result
