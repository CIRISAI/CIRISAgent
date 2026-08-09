"""An attestation is always produced within the budget. No exceptions.

Not "usually", and not "unless the build is unregistered". If the verifier
cannot produce one inside the budget, the caller gets a DEGRADED attestation —
never a hang.

THE INCIDENT

On Android the agent sat on the Interact screen with a typed question and never
answered it. The cognitive-state chip read "Setup" and the trust shield spun
forever. The log:

    [attestation] TIMEOUT: Thread still alive after 90 seconds!
    [attestation] Startup attestation exceeded the 20s budget: took 90.00s
    RuntimeError: Startup attestation exceeded the 20s budget (elapsed=65.2s)

Two independent defects, both fixed here:

1. THE WAIT WAS NOT BOUNDED BY THE BUDGET. ``ATTESTATION_TIMEOUT = 90`` was an
   unrelated constant, 4.5x the contract. When the verifier blocked on an HTTPS
   source-availability check with no network, 90s is what actually bounded it,
   the processor gate arrived 65s in to find the budget long gone, and the
   runtime never left Setup. The budget could only ever be violated and
   reported, never met.

2. THE OVERRIDE NEVER APPLIED. The budget was read into a module-level constant
   at import. mobile_main sets CIRIS_STARTUP_ATTESTATION_BUDGET_SECONDS=45
   during startup — after authentication.service is imported — so the value
   stayed 20.0 and the log said "20s budget" on a runtime that had asked for 45.
   An env var that only works if set before an unrelated import is a coin flip,
   not a knob.

CIRIS_ATTESTATION_SKIP_REGISTRY did not prevent any of this: it removes the
registry fetch (CIRISVerify#212), and the call that hung was a different one.
That is exactly why the bound belongs on the WAIT rather than on each known-slow
call — new slow paths must not be able to reintroduce the hang.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from ciris_engine.logic.services.infrastructure.authentication.attestation import verifier_runner
from ciris_engine.logic.services.infrastructure.authentication.attestation.verifier_runner import (
    ATTESTATION_TIMEOUT,
    attestation_deadline_seconds,
    startup_attestation_budget_seconds,
)

BUDGET_ENV = "CIRIS_STARTUP_ATTESTATION_BUDGET_SECONDS"


def test_default_budget_is_twenty_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    """The contract, stated once."""
    monkeypatch.delenv(BUDGET_ENV, raising=False)
    assert startup_attestation_budget_seconds() == 20.0
    assert attestation_deadline_seconds() == 20.0


def test_deadline_is_the_budget_not_the_backstop(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression: a 90s wait cannot honour a 20s promise."""
    monkeypatch.delenv(BUDGET_ENV, raising=False)
    assert attestation_deadline_seconds() < ATTESTATION_TIMEOUT, (
        f"the verifier wait ({attestation_deadline_seconds()}s) must be bounded by the "
        f"budget, not by the {ATTESTATION_TIMEOUT}s hang backstop — that is what let a "
        f"wedged verifier hold startup for 90s and strand the processor in Setup"
    )


def test_override_is_read_at_call_time_not_import_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """The defect that made mobile's 45 silently mean 20."""
    monkeypatch.setenv(BUDGET_ENV, "45")
    assert startup_attestation_budget_seconds() == 45.0
    assert attestation_deadline_seconds() == 45.0

    monkeypatch.setenv(BUDGET_ENV, "7")
    assert attestation_deadline_seconds() == 7.0, "a later change must also be seen"


def test_absurd_budget_still_capped_by_the_hang_backstop(monkeypatch: pytest.MonkeyPatch) -> None:
    """The backstop stays a backstop: nobody can configure an infinite wait."""
    monkeypatch.setenv(BUDGET_ENV, "99999")
    assert attestation_deadline_seconds() == float(ATTESTATION_TIMEOUT)


@pytest.mark.parametrize("bad", ["", "   ", "not-a-number", "abc"])
def test_garbage_override_falls_back_to_the_contract(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    monkeypatch.setenv(BUDGET_ENV, bad)
    assert startup_attestation_budget_seconds() == 20.0


def test_negative_or_zero_budget_cannot_disable_attestation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BUDGET_ENV, "-5")
    assert startup_attestation_budget_seconds() >= 1.0


@pytest.mark.asyncio
async def test_a_wedged_verifier_degrades_at_the_budget_instead_of_hanging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The end-to-end promise, against a verifier that never returns.

    This is the Android failure reproduced: a thread that blocks forever (there,
    on an HTTPS call with no network). The old code waited 90s; the contract
    says we degrade at the budget. A short budget keeps the test fast — the
    property under test is "bounded by the budget", not the specific number.
    """
    monkeypatch.setenv(BUDGET_ENV, "1")

    never_returns = threading.Event()  # never set: the thread hangs like verify did

    def _wedged_target() -> None:
        never_returns.wait()

    monkeypatch.setattr(
        verifier_runner,
        "create_verification_thread_target",
        lambda *a, **k: _wedged_target,
    )

    started = time.monotonic()
    result = await verifier_runner.run_verification_thread(
        get_verifier=lambda: object(),
        attestation_mode="partial",
    )
    elapsed = time.monotonic() - started

    assert elapsed < 10, (
        f"took {elapsed:.1f}s against a 1s budget — the wait is not bounded by the "
        f"budget, which is the defect that stranded the processor in Setup for 90s"
    )
    assert result.error is not None, "a wedged verifier must degrade, not look successful"
    assert "timed out" in result.error.lower()
