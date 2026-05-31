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

# This file tests the real bodies of run_startup_attestation and
# _attestation_refresh_loop, which the global autouse fixture in
# tests/conftest.py would otherwise stub out for performance/safety.
pytestmark = pytest.mark.real_attestation


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


# ---------------------------------------------------------------------------
# await_attestation_ready — block-until-ready contract
# ---------------------------------------------------------------------------
#
# Why these exist: ciris_verify is a hard runtime dependency. The previous
# pattern launched run_startup_attestation as a fire-and-forget background
# task with a test-mode skip; thoughts could fire before attestation
# completed and emit null verify_attestation fields to Lens. The new
# contract is a background task captured on `_attestation_task` plus an
# `await_attestation_ready()` gate that any consumer must call before
# reading the cache. These tests pin every branch of that gate.


class TestAwaitAttestationReady:
    """Pin the await_attestation_ready() contract surface."""

    def _make_bare_service(self):
        """Build a service instance without running __init__ (no DB, no FFI)."""
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService.__init__",
            lambda self_inner, *a, **kw: None,
        ):
            from ciris_engine.logic.services.infrastructure.authentication.service import (
                AuthenticationService,
            )

            svc = AuthenticationService.__new__(AuthenticationService)
            svc._attestation_task = None
            return svc

    @pytest.mark.asyncio
    async def test_raises_when_start_never_ran(self):
        """If _attestation_task is None (start() never called), raise.

        This is the wedge that catches consumers running before the
        service has been properly started — they should not silently
        proceed with a null attestation context.
        """
        svc = self._make_bare_service()
        with pytest.raises(RuntimeError, match="start.* has not been called"):
            await svc.await_attestation_ready()

    @pytest.mark.asyncio
    async def test_returns_immediately_when_task_already_done(self):
        """If the attestation task already finished cleanly, await is a no-op."""
        svc = self._make_bare_service()

        async def already_done() -> None:
            return None

        svc._attestation_task = asyncio.create_task(already_done())
        await svc._attestation_task  # Drive it to completion
        # Second await — should return immediately without raising
        await svc.await_attestation_ready()

    @pytest.mark.asyncio
    async def test_blocks_until_running_task_completes(self):
        """If the task is in flight, await blocks until it finishes.

        Concretely: kick off a task that sleeps briefly, then assert the
        gate doesn't return until the sleep is done.
        """
        svc = self._make_bare_service()
        completed = False

        async def slow_attestation() -> None:
            nonlocal completed
            await asyncio.sleep(0.05)
            completed = True

        svc._attestation_task = asyncio.create_task(slow_attestation())
        # Gate must not return until the task finished
        assert completed is False
        await svc.await_attestation_ready()
        assert completed is True

    @pytest.mark.asyncio
    async def test_reraises_task_failure(self):
        """If the attestation task raised, the exception is re-raised here.

        This is the load-bearing assertion: there is no path that swallows
        attestation failures. Lens should never see null verify fields
        because the agent crashed before it could emit them.
        """
        svc = self._make_bare_service()

        class FFIUnloadable(RuntimeError):
            pass

        async def failing_attestation() -> None:
            raise FFIUnloadable("libtss2-tctildr.so.0 not loadable")

        svc._attestation_task = asyncio.create_task(failing_attestation())
        with pytest.raises(FFIUnloadable, match="tctildr"):
            await svc.await_attestation_ready()

    @pytest.mark.asyncio
    async def test_test_mode_env_vars_no_longer_skip_attestation(self, monkeypatch):
        """Confirm CIRIS_IMPORT_MODE / CIRIS_MOCK_LLM no longer bypass.

        The previous start() had:
            if CIRIS_IMPORT_MODE or CIRIS_MOCK_LLM: return
        which left _attestation_task == None and let consumers proceed
        with no attestation. We removed that skip; setting the env vars
        must have no effect on whether the task gets created.
        """
        monkeypatch.setenv("CIRIS_IMPORT_MODE", "true")
        monkeypatch.setenv("CIRIS_MOCK_LLM", "true")

        # Read the source of start() and confirm the skip block is gone.
        # Source-level assertion is the right shape: a behavioral test
        # would need a fully-wired service which is far out of scope here.
        import inspect

        from ciris_engine.logic.services.infrastructure.authentication.service import (
            AuthenticationService,
        )

        src = inspect.getsource(AuthenticationService.start)
        assert "skipping attestation in test mode" not in src, (
            "Test-mode attestation-skip reintroduced. ciris_verify is a hard "
            "runtime dependency; CIRIS_IMPORT_MODE / CIRIS_MOCK_LLM must NOT "
            "bypass startup attestation."
        )
        assert "self._attestation_task = asyncio.create_task" in src, (
            "start() should kick off run_startup_attestation as a captured "
            "background task on self._attestation_task so "
            "await_attestation_ready() can gate on it."
        )


# ---------------------------------------------------------------------------
# Startup attestation budget (20s end-to-end ceiling, 15s contract)
# ---------------------------------------------------------------------------
#
# The auth service exposes STARTUP_ATTESTATION_BUDGET_SECONDS = 20.0. The
# contract is 15s — we sit at 20.0 with 5s headroom while CIRISVerify ships
# the verifier-side fix in CIRISAgent#843 (10s network-probe timeout blows
# 15s under CI's offline egress + parallel-backend CPU contention). Once
# the verifier short-circuits offline probes, drop back to 15.0.
#
# await_attestation_ready() enforces the budget by measuring from task
# creation, not from when the caller started awaiting — so a caller
# arriving 19s late only gets 1s of budget.
#
# Budget breach is not a tuning knob beyond the documented headroom; it
# is a defect that must be filed against ciris_verify with receipts.


class TestStartupAttestationBudget:
    """Pin the 20s end-to-end attestation budget enforcement."""

    def _make_bare_service(self):
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService.__init__",
            lambda self_inner, *a, **kw: None,
        ):
            from ciris_engine.logic.services.infrastructure.authentication.service import (
                AuthenticationService,
            )

            svc = AuthenticationService.__new__(AuthenticationService)
            svc._attestation_task = None
            svc._attestation_started_at = None
            svc._attestation_stage_timings = {}
            return svc

    def test_budget_constant_value(self):
        """The contract value is 15s but we currently sit at 20.0 (5s
        headroom while CIRISVerify ships CIRISAgent#843). Flipping this
        without thought weakens the gate that prevents 60-120s first-thought
        stalls; raising past 20.0 requires a new issue against ciris_verify.
        """
        from ciris_engine.logic.services.infrastructure.authentication.service import (
            STARTUP_ATTESTATION_BUDGET_SECONDS,
        )

        assert STARTUP_ATTESTATION_BUDGET_SECONDS == 20.0

    @pytest.mark.asyncio
    async def test_returns_immediately_within_budget(self):
        """Fast attestation (well under budget) returns clean."""
        svc = self._make_bare_service()

        async def fast_attestation() -> None:
            await asyncio.sleep(0.01)

        loop = asyncio.get_event_loop()
        svc._attestation_started_at = loop.time()
        svc._attestation_task = asyncio.create_task(fast_attestation())

        await svc.await_attestation_ready(budget_seconds=15.0)
        assert svc._attestation_task.done()

    @pytest.mark.asyncio
    async def test_fast_path_raises_when_completed_run_exceeded_budget(self):
        """Codex P1: a caller arriving AFTER the task already finished
        must still see the budget breach. Without this check, a 20s
        attestation that completed before the gate ran would silently
        pass — defeating the contract for any caller that observed it.

        The check uses `_attestation_stage_timings["run_attestation_
        total_seconds"]` (recorded by run_startup_attestation on
        completion) rather than elapsed-since-task-start, because the
        latter inflates with caller arrival time and would
        false-positive on a fast run with a late observer.
        """
        svc = self._make_bare_service()

        async def already_done() -> None:
            return None

        svc._attestation_task = asyncio.create_task(already_done())
        await svc._attestation_task  # drive to completion
        # Simulate the receipts that run_startup_attestation would have
        # recorded for a 20s run — well past the 15s budget.
        svc._attestation_stage_timings = {
            "run_attestation_total_seconds": 20.0,
            "binary_ok": True,
            "function_integrity": "verified",
        }

        with pytest.raises(RuntimeError, match="completed but exceeded"):
            await svc.await_attestation_ready(budget_seconds=15.0)

    @pytest.mark.asyncio
    async def test_fast_path_passes_when_completed_run_within_budget(self):
        """The fast-path budget check must only fire on overshoot — a
        clean 10s run with the cache populated should still pass through
        cleanly even though stage_timings has a real number."""
        svc = self._make_bare_service()

        async def already_done() -> None:
            return None

        svc._attestation_task = asyncio.create_task(already_done())
        await svc._attestation_task
        svc._attestation_stage_timings = {
            "run_attestation_total_seconds": 10.0,
            "binary_ok": True,
        }

        # Should not raise.
        await svc.await_attestation_ready(budget_seconds=15.0)

    @pytest.mark.asyncio
    async def test_fast_path_passes_when_stage_timings_unrecorded(self):
        """Bare-service fixtures don't populate stage_timings. The
        fast-path budget check must degrade gracefully (no raise) when
        the recorded total is absent — otherwise legitimate test setups
        would false-positive without ever having observed a real run.
        """
        svc = self._make_bare_service()

        async def already_done() -> None:
            return None

        svc._attestation_task = asyncio.create_task(already_done())
        await svc._attestation_task
        # No stage_timings set — bare service.

        # Should not raise.
        await svc.await_attestation_ready(budget_seconds=15.0)

    @pytest.mark.asyncio
    async def test_raises_runtime_error_on_budget_breach(self):
        """A task that exceeds the budget raises RuntimeError with the
        contract message — not a TimeoutError or a silent stall."""
        svc = self._make_bare_service()

        async def slow_attestation() -> None:
            # Longer than test budget; we cancel out via the gate.
            await asyncio.sleep(5)

        loop = asyncio.get_event_loop()
        svc._attestation_started_at = loop.time()
        svc._attestation_task = asyncio.create_task(slow_attestation())

        # Use a tiny budget so the test stays fast. The behavior under 15s
        # and 0.1s is identical — both surface a RuntimeError on overshoot.
        with pytest.raises(RuntimeError, match=r"exceeded the .* budget"):
            await svc.await_attestation_ready(budget_seconds=0.1)

        # Clean up the lingering task to keep the test loop tidy.
        svc._attestation_task.cancel()
        try:
            await svc._attestation_task
        except asyncio.CancelledError:
            # Expected after task.cancel(); drain so pytest doesn't warn
            # about an un-awaited cancelled task at teardown.
            pass

    @pytest.mark.asyncio
    async def test_budget_message_names_verifier_as_owner(self):
        """The error message must point at the verifier as the thing to
        fix, not at the budget itself. This is the "do not raise the
        budget" load-bearing assertion."""
        svc = self._make_bare_service()

        async def slow_attestation() -> None:
            await asyncio.sleep(5)

        loop = asyncio.get_event_loop()
        svc._attestation_started_at = loop.time()
        svc._attestation_task = asyncio.create_task(slow_attestation())

        try:
            await svc.await_attestation_ready(budget_seconds=0.05)
        except RuntimeError as exc:
            msg = str(exc)
            assert "verifier" in msg.lower(), msg
            assert "budget" in msg.lower(), msg
            # No "increase the timeout" framing.
            assert "raise the budget" in msg.lower() or "investigate" in msg.lower(), msg
        else:  # pragma: no cover
            pytest.fail("await_attestation_ready did not raise on overshoot")

        svc._attestation_task.cancel()
        try:
            await svc._attestation_task
        except asyncio.CancelledError:
            # Expected after task.cancel(); drain so pytest doesn't warn
            # about an un-awaited cancelled task at teardown.
            pass

    @pytest.mark.asyncio
    async def test_budget_measured_from_task_start_not_call_time(self):
        """A caller arriving 0.4s after start with a 0.5s budget has only
        0.1s of remaining budget, not 0.5s. This guards against callers
        accidentally being granted a full budget by reaching the gate
        late."""
        svc = self._make_bare_service()

        async def slow_attestation() -> None:
            await asyncio.sleep(5)

        loop = asyncio.get_event_loop()
        # Pretend the task started 0.4s ago.
        svc._attestation_started_at = loop.time() - 0.4
        svc._attestation_task = asyncio.create_task(slow_attestation())

        gate_start = loop.time()
        with pytest.raises(RuntimeError, match="budget"):
            await svc.await_attestation_ready(budget_seconds=0.5)
        gate_elapsed = loop.time() - gate_start
        # Only ~0.1s remained when the gate ran. Generous upper bound for
        # CI jitter, but well below the 0.5s caller-time budget.
        assert gate_elapsed < 0.4, (
            f"Gate waited {gate_elapsed:.3f}s — should have honored remaining "
            f"budget after task-start offset, not the full caller budget."
        )

        svc._attestation_task.cancel()
        try:
            await svc._attestation_task
        except asyncio.CancelledError:
            # Expected after task.cancel(); drain so pytest doesn't warn
            # about an un-awaited cancelled task at teardown.
            pass

    @pytest.mark.asyncio
    async def test_late_caller_times_out_immediately(self):
        """A caller that arrives AFTER the budget has already elapsed
        gets zero remaining time and surfaces the breach right away.
        This is the "first thought arrives 20s after start" scenario."""
        svc = self._make_bare_service()

        async def slow_attestation() -> None:
            await asyncio.sleep(5)

        loop = asyncio.get_event_loop()
        # Pretend the task started 1.0s ago — already past a 0.1s budget.
        svc._attestation_started_at = loop.time() - 1.0
        svc._attestation_task = asyncio.create_task(slow_attestation())

        with pytest.raises(RuntimeError, match="budget"):
            await svc.await_attestation_ready(budget_seconds=0.1)

        svc._attestation_task.cancel()
        try:
            await svc._attestation_task
        except asyncio.CancelledError:
            # Expected after task.cancel(); drain so pytest doesn't warn
            # about an un-awaited cancelled task at teardown.
            pass

    @pytest.mark.asyncio
    async def test_budget_overshoot_does_not_cancel_task(self):
        """When the budget is breached, we surface the breach but let the
        task continue running so refresh/audit paths can still benefit
        from an eventual result. Cancelling would forfeit attestation
        data already in flight."""
        svc = self._make_bare_service()

        async def slow_attestation() -> None:
            await asyncio.sleep(5)

        loop = asyncio.get_event_loop()
        svc._attestation_started_at = loop.time()
        svc._attestation_task = asyncio.create_task(slow_attestation())

        try:
            await svc.await_attestation_ready(budget_seconds=0.05)
        except RuntimeError:
            pass

        assert not svc._attestation_task.done(), (
            "Gate must not cancel the in-flight attestation task on a budget "
            "breach — the refresh loop still benefits from its eventual result."
        )

        svc._attestation_task.cancel()
        try:
            await svc._attestation_task
        except asyncio.CancelledError:
            # Expected after task.cancel(); drain so pytest doesn't warn
            # about an un-awaited cancelled task at teardown.
            pass


class TestStartupAttestationReceipts:
    """The processor gate's failure logger expects stage_timings populated
    by run_startup_attestation. Verify the receipts pipeline produces
    actionable data for ciris_verify bug reports."""

    def _make_bare_service(self):
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService.__init__",
            lambda self_inner, *a, **kw: None,
        ):
            from ciris_engine.logic.services.infrastructure.authentication.service import (
                AuthenticationService,
            )

            svc = AuthenticationService.__new__(AuthenticationService)
            svc._attestation_cache = None
            svc._baseline_attestation = None
            svc._attestation_stage_timings = {}
            return svc

    @pytest.mark.asyncio
    async def test_success_path_records_total_and_per_bool(self):
        """A clean run populates total wall-clock + every per-bool stage
        outcome. These are the fields the gate's logger reads when
        building a ciris_verify issue body."""
        svc = self._make_bare_service()
        result = _make_result()

        async def mock_run_attestation(**kw):
            await asyncio.sleep(0.01)
            return result

        svc.run_attestation = mock_run_attestation
        await svc.run_startup_attestation()

        st = svc._attestation_stage_timings
        # Total wall-clock recorded
        assert "run_attestation_total_seconds" in st
        assert isinstance(st["run_attestation_total_seconds"], (int, float))
        assert st["run_attestation_total_seconds"] >= 0.0
        # Per-stage booleans recorded
        assert "binary_ok" in st
        assert "function_integrity" in st
        assert "python_integrity_ok" in st
        assert "registry_ok" in st
        assert "audit_ok" in st
        assert "max_level" in st
        assert "level_pending" in st

    @pytest.mark.asyncio
    async def test_overshoot_logs_warning_and_records_total(self, caplog):
        """When the verifier takes >15s, the service logs a warning naming
        the budget and the actual elapsed time so the failure is grep-able
        in incidents_latest.log even before the gate's receipts dump."""
        svc = self._make_bare_service()
        result = _make_result()

        async def slow_run_attestation(**kw):
            # Simulate a 0.02s slow verifier using a 0.01s test budget by
            # patching the constant down inside the test.
            await asyncio.sleep(0.02)
            return result

        svc.run_attestation = slow_run_attestation

        from ciris_engine.logic.services.infrastructure.authentication import service as svc_mod

        with caplog.at_level("WARNING"):
            with patch.object(svc_mod, "STARTUP_ATTESTATION_BUDGET_SECONDS", 0.01):
                await svc.run_startup_attestation()

        # Warning fires, names the budget, names the elapsed time
        warnings_msgs = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any("exceeded" in m and "budget" in m for m in warnings_msgs), warnings_msgs
        # Per-stage timings still populated
        assert svc._attestation_stage_timings["run_attestation_total_seconds"] > 0.01

    @pytest.mark.asyncio
    async def test_failure_path_records_exception_receipts(self):
        """When run_attestation raises, stage_timings still gets populated
        with the exception type/message so the gate's failure logger has
        receipts to file. Best-effort: a raise here must never be swallowed
        by the receipt-capture code."""
        svc = self._make_bare_service()

        class FakeVerifierError(RuntimeError):
            pass

        async def failing_run_attestation(**kw):
            await asyncio.sleep(0.005)
            raise FakeVerifierError("libtss2 unloadable")

        svc.run_attestation = failing_run_attestation
        # run_startup_attestation catches and logs, doesn't re-raise.
        await svc.run_startup_attestation()

        st = svc._attestation_stage_timings
        assert st.get("raised") is True
        assert st.get("exception_type") == "FakeVerifierError"
        assert "libtss2 unloadable" in st.get("exception_message", "")
        assert st["run_attestation_total_seconds"] > 0.0

    @pytest.mark.asyncio
    async def test_start_records_attestation_started_at_timestamp(self):
        """The end-to-end budget is meaningless without a task-creation
        timestamp. Confirm the source of start() pins
        _attestation_started_at adjacent to task creation so the two
        always move together.
        """
        import inspect

        from ciris_engine.logic.services.infrastructure.authentication.service import (
            AuthenticationService,
        )

        src = inspect.getsource(AuthenticationService.start)
        # Both lines present
        assert "self._attestation_started_at = asyncio.get_event_loop().time()" in src, (
            "start() must record _attestation_started_at adjacent to task "
            "creation so await_attestation_ready can enforce the budget "
            "from a real baseline."
        )
        assert "self._attestation_task = asyncio.create_task(self.run_startup_attestation())" in src
        # And the timestamp line comes BEFORE the task creation, not after
        idx_ts = src.index("self._attestation_started_at = asyncio.get_event_loop().time()")
        idx_task = src.index(
            "self._attestation_task = asyncio.create_task(self.run_startup_attestation())"
        )
        assert idx_ts < idx_task, (
            "_attestation_started_at must be set BEFORE the task is "
            "scheduled — otherwise a fast verifier could finish before the "
            "timestamp is recorded and budget arithmetic would underflow."
        )
