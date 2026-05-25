"""
Tests for CIRISRuntime._await_attestation_ready and the budget-breach
receipts logger.

The gate sits between "all services ready" and "agent_processor.start_
processing()". If it lets a thought through before the attestation cache
is populated, the first thought absorbs the full 60-120s attestation
latency and downstream timing assertions blow their budgets (the
context_enrichment / air QA flakes are the canonical symptom).

These tests pin every observable surface of the gate, including the
receipts logger that captures stage timings + exception chain on a
budget breach so the failure becomes a fileable ciris_verify issue
instead of a flake-of-the-week.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime


def _bare_runtime() -> CIRISRuntime:
    """Build a CIRISRuntime instance without running __init__. The gate
    code under test only touches self.service_initializer, so we don't
    need a real runtime — just enough surface to drive the method."""
    runtime = CIRISRuntime.__new__(CIRISRuntime)
    runtime.service_initializer = None  # type: ignore[assignment]
    return runtime


def _make_auth_service(*, await_side_effect=None) -> MagicMock:
    """Build a fake auth service that satisfies the gate's capability
    sniff (`hasattr(svc, "await_attestation_ready")`)."""
    svc = MagicMock()
    if await_side_effect is None:
        svc.await_attestation_ready = AsyncMock(return_value=None)
    else:
        svc.await_attestation_ready = AsyncMock(side_effect=await_side_effect)
    # Mirrors fields the failure-receipt logger reads.
    svc._attestation_started_at = 1.0
    svc._attestation_task = MagicMock()
    svc._attestation_task.done.return_value = True
    svc._attestation_cache = MagicMock()
    svc._baseline_attestation = MagicMock()
    svc._attestation_in_progress = False
    svc._attestation_stage_timings = {
        "run_attestation_total_seconds": 16.42,
        "binary_ok": True,
        "function_integrity": "verified",
        "python_integrity_ok": True,
        "registry_ok": True,
        "audit_ok": True,
        "max_level": 4,
        "level_pending": False,
    }
    return svc


class TestAwaitAttestationGate:
    """The happy/normal-failure paths of CIRISRuntime._await_attestation_ready."""

    @pytest.mark.asyncio
    async def test_gate_awaits_when_auth_service_present(self):
        """If the service initializer exposes an auth service with
        await_attestation_ready, the gate awaits it."""
        runtime = _bare_runtime()
        auth = _make_auth_service()
        runtime.service_initializer = MagicMock(auth_service=auth)

        await runtime._await_attestation_ready()
        auth.await_attestation_ready.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_gate_skips_with_warning_when_no_initializer(self, caplog):
        """If service_initializer is missing, the gate logs a warning
        and returns rather than crashing — startup can still proceed,
        though per-thought batch_context will absorb the latency."""
        runtime = _bare_runtime()
        runtime.service_initializer = None

        with caplog.at_level("WARNING"):
            await runtime._await_attestation_ready()
        msgs = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any("AuthenticationService unavailable" in m for m in msgs), msgs

    @pytest.mark.asyncio
    async def test_gate_skips_with_warning_when_no_auth_service(self, caplog):
        """If the initializer has no auth_service attribute or the
        attribute is None, the gate falls back to the warn-and-continue
        path rather than crashing."""
        runtime = _bare_runtime()
        runtime.service_initializer = MagicMock(auth_service=None)

        with caplog.at_level("WARNING"):
            await runtime._await_attestation_ready()
        msgs = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any("AuthenticationService unavailable" in m for m in msgs), msgs

    @pytest.mark.asyncio
    async def test_gate_skips_when_auth_service_lacks_method(self, caplog):
        """A service registered as auth but without
        await_attestation_ready (e.g., the wrong WiseAuthority impl)
        triggers the warn-and-continue branch. Same pattern batch_context
        uses to disambiguate."""
        runtime = _bare_runtime()

        class NoBudgetAuth:
            pass

        runtime.service_initializer = MagicMock(auth_service=NoBudgetAuth())

        with caplog.at_level("WARNING"):
            await runtime._await_attestation_ready()
        msgs = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any("AuthenticationService unavailable" in m for m in msgs), msgs

    @pytest.mark.asyncio
    async def test_gate_reraises_attestation_failure(self):
        """An exception from await_attestation_ready propagates so
        startup fails loudly — the whole point of the gate is to refuse
        to start the processor on a broken attestation."""
        runtime = _bare_runtime()
        auth = _make_auth_service(
            await_side_effect=RuntimeError(
                "Startup attestation exceeded the 15s budget (elapsed=18.4s)"
            )
        )
        runtime.service_initializer = MagicMock(auth_service=auth)

        with pytest.raises(RuntimeError, match="exceeded the 15s budget"):
            await runtime._await_attestation_ready()

    @pytest.mark.asyncio
    async def test_gate_dumps_receipts_on_failure(self, caplog):
        """On budget breach, the gate must log a structured receipts dump
        at ERROR level so the failure is fileable as a ciris_verify
        issue. The dump includes:
          - exception type + message
          - stage_timings from the auth service
          - cache + baseline + task-done flags
          - the verifier issue tracker URL
        """
        runtime = _bare_runtime()
        breach = RuntimeError(
            "Startup attestation exceeded the 15s budget (elapsed=18.42s)"
        )
        auth = _make_auth_service(await_side_effect=breach)
        runtime.service_initializer = MagicMock(auth_service=auth)

        with caplog.at_level("ERROR"):
            with pytest.raises(RuntimeError):
                await runtime._await_attestation_ready()

        joined = "\n".join(r.getMessage() for r in caplog.records if r.levelname == "ERROR")

        # Banner present
        assert "ATTESTATION GATE BUDGET BREACH" in joined
        # Exception identity captured
        assert "RuntimeError" in joined
        assert "exceeded the 15s budget" in joined
        # Stage timings surfaced (so a maintainer sees what stage ate the budget)
        assert "run_attestation_total_seconds" in joined
        assert "16.42" in joined
        # Cache + task state surfaced
        assert "attestation_cache_populated" in joined
        assert "baseline_attestation_populated" in joined
        assert "attestation_task_done" in joined
        # Filing URL surfaced
        assert "CIRISVerify/issues" in joined or "github.com/CIRISAI/CIRISVerify" in joined

    @pytest.mark.asyncio
    async def test_receipts_handles_partially_initialized_auth_service(self, caplog):
        """Receipts capture must never crash, even on a service that's
        missing the diagnostic attributes. Each getter is wrapped in a
        try/except so partial state still produces a useful dump."""
        runtime = _bare_runtime()
        # Auth service that has the method but is missing every
        # diagnostic attribute the receipts logger reads.
        auth = MagicMock(spec=["await_attestation_ready"])
        auth.await_attestation_ready = AsyncMock(
            side_effect=RuntimeError("attestation budget exceeded")
        )
        runtime.service_initializer = MagicMock(auth_service=auth)

        with caplog.at_level("ERROR"):
            with pytest.raises(RuntimeError):
                await runtime._await_attestation_ready()

        joined = "\n".join(r.getMessage() for r in caplog.records if r.levelname == "ERROR")
        assert "ATTESTATION GATE BUDGET BREACH" in joined
        # Even with no diagnostic attrs, the failure still files cleanly
        assert "attestation budget exceeded" in joined

    @pytest.mark.asyncio
    async def test_receipts_include_exception_traceback(self, caplog):
        """The traceback must be in the receipts so a maintainer can
        pin the failure to the exact verifier callsite. Without this
        the issue body is "it timed out" with no actionable signal."""
        runtime = _bare_runtime()

        def _make_chained_breach() -> RuntimeError:
            try:
                raise ValueError("verifier walked a stale fs cache")
            except ValueError as inner:
                outer = RuntimeError("Startup attestation exceeded budget")
                outer.__cause__ = inner
                return outer

        auth = _make_auth_service(await_side_effect=_make_chained_breach())
        runtime.service_initializer = MagicMock(auth_service=auth)

        with caplog.at_level("ERROR"):
            with pytest.raises(RuntimeError):
                await runtime._await_attestation_ready()

        joined = "\n".join(r.getMessage() for r in caplog.records if r.levelname == "ERROR")
        assert "Exception chain" in joined
        assert "RuntimeError" in joined


class TestProcessorGateOrdering:
    """The gate is load-bearing only if it runs BEFORE
    agent_processor.start_processing(). A regression that reorders these
    two would silently re-introduce the 60-120s first-thought stall."""

    def test_gate_call_precedes_start_processing_in_source(self):
        """Static check: confirm the source of
        _create_agent_processor_when_ready calls _await_attestation_ready
        before start_processing. A behavioral test would need a full
        runtime which is out of scope here, so we pin the ordering at
        the source level — same shape as the existing test_test_mode_
        env_vars_no_longer_skip_attestation assertion in the auth
        service tests."""
        import inspect

        src = inspect.getsource(CIRISRuntime._create_agent_processor_when_ready)
        idx_gate = src.index("await self._await_attestation_ready()")
        idx_start = src.index("self.agent_processor.start_processing(")
        assert idx_gate < idx_start, (
            "_await_attestation_ready must precede start_processing in "
            "_create_agent_processor_when_ready — otherwise the first "
            "thought absorbs the full attestation latency and the gate "
            "is pointless."
        )

    def test_gate_method_is_async(self):
        """The gate must be an async method — sync would block the
        event loop while awaiting the attestation task."""
        import inspect

        assert inspect.iscoroutinefunction(CIRISRuntime._await_attestation_ready), (
            "_await_attestation_ready must be a coroutine — awaiting "
            "the attestation task synchronously would freeze the runtime."
        )
