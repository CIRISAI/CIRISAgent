"""The processor gate must outlast the degrade it is waiting for.

verifier_runner already promises that an attestation is always produced within
the budget: it bounds its own run at ``attestation_deadline_seconds()`` and
hands back a degraded ``level=0, binary=FAIL`` result rather than hanging. The
gate in ``await_attestation_ready`` exists to wait for exactly that result.

Both used to be bounded by the SAME budget from (within milliseconds of) the
same instant, so the gate expired while the runner was still assembling its
degraded result — and lost the race every time.

Field report (2.9.37, Windows 11 / py3.14): one ``ciris_verify_tree`` call,
``elapsed=20.0s`` dead on the budget, ``attestation_task_done: False``,
``stage_timings_seconds: {}``. The runtime aborted 22 seconds after boot, with
no UI and no way into the setup wizard.
"""

import asyncio

import pytest

from ciris_engine.logic.services.infrastructure.authentication.attestation.verifier_runner import (
    attestation_deadline_seconds,
)
from ciris_engine.logic.services.infrastructure.authentication.service import (
    ATTESTATION_GATE_GRACE_SECONDS,
    AuthenticationService,
    _attestation_gate_deadline,
)


def test_gate_deadline_outlasts_the_runner_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole defect in one assertion."""
    monkeypatch.delenv("CIRIS_STARTUP_ATTESTATION_BUDGET_SECONDS", raising=False)
    assert _attestation_gate_deadline() > attestation_deadline_seconds(), (
        "the gate must not expire while the runner is still producing the "
        "degraded result it was told to wait for"
    )


def test_grace_is_enough_to_assemble_a_result() -> None:
    """Grace covers result assembly + cache population, not a slow verifier."""
    assert ATTESTATION_GATE_GRACE_SECONDS >= 1.0


def test_gate_deadline_tracks_a_late_budget_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read at call time. A value frozen at import discards the override
    mobile_main sets during startup — the Android log read 'exceeded the 20s
    budget' on a runtime that had explicitly asked for 45."""
    monkeypatch.setenv("CIRIS_STARTUP_ATTESTATION_BUDGET_SECONDS", "45")
    assert _attestation_gate_deadline() == 45.0 + ATTESTATION_GATE_GRACE_SECONDS
    monkeypatch.setenv("CIRIS_STARTUP_ATTESTATION_BUDGET_SECONDS", "7")
    assert _attestation_gate_deadline() == 7.0 + ATTESTATION_GATE_GRACE_SECONDS


class _Svc:
    """Minimal stand-in carrying only what await_attestation_ready touches."""

    def __init__(self, task: asyncio.Task, started_at: float) -> None:
        self._attestation_task = task
        self._attestation_started_at = started_at
        self._attestation_stage_timings: dict = {}
        self._attestation_slo_breach_logged = False

    # The real reporter, so the stand-in exercises the shipped logging path.
    _log_attestation_slo_breach = AuthenticationService._log_attestation_slo_breach


@pytest.mark.asyncio
async def test_a_late_degrade_is_still_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    """A runner that degrades just past the budget must still be observed.

    This is Francesco's boot: the result lands microseconds after the budget.
    The old gate raised at exactly 20.0s and threw that result away.
    """
    monkeypatch.setenv("CIRIS_STARTUP_ATTESTATION_BUDGET_SECONDS", "1")
    delivered = []

    async def _degrades_just_past_the_budget() -> str:
        await asyncio.sleep(1.05)  # budget is 1.0s — lands inside the grace
        delivered.append("degraded-result")
        return "degraded-result"

    loop = asyncio.get_event_loop()
    task = loop.create_task(_degrades_just_past_the_budget())
    svc = _Svc(task, loop.time())

    await AuthenticationService.await_attestation_ready(svc)  # must not raise

    assert delivered == ["degraded-result"], "the gate discarded a result that did arrive"


@pytest.mark.asyncio
async def test_breach_does_not_poison_later_callers(monkeypatch: pytest.MonkeyPatch) -> None:
    """A breach must not be permanent for the process.

    ``remaining`` is measured from task-creation time, so once elapsed passed
    the deadline every later caller computed ``max(0.0, ...) == 0.0`` and timed
    out instantly. batch_context calls this same method per thought, so one
    slow boot meant the agent could never think again.
    """
    monkeypatch.setenv("CIRIS_STARTUP_ATTESTATION_BUDGET_SECONDS", "1")

    async def _never_finishes_in_time() -> str:
        await asyncio.sleep(30)
        return "late"

    loop = asyncio.get_event_loop()
    task = loop.create_task(_never_finishes_in_time())
    svc = _Svc(task, loop.time() - 600)  # deadline long gone

    # Every subsequent caller degrades quietly rather than raising.
    for _ in range(3):
        await AuthenticationService.await_attestation_ready(svc)

    task.cancel()


@pytest.mark.asyncio
async def test_slow_but_successful_attestation_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow filesystem does not make the tree hash wrong."""
    monkeypatch.setenv("CIRIS_STARTUP_ATTESTATION_BUDGET_SECONDS", "1")

    async def _done() -> str:
        return "ok"

    loop = asyncio.get_event_loop()
    task = loop.create_task(_done())
    await task
    svc = _Svc(task, loop.time())
    svc._attestation_stage_timings = {"run_attestation_total_seconds": 99.0}

    await AuthenticationService.await_attestation_ready(svc)  # must not raise
    assert svc._attestation_slo_breach_logged, "a breach must still be reported"
