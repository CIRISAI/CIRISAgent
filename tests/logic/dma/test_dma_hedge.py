"""A slow DMA attempt is hedged, not abandoned (2.18.0).

The retry used to start only after the slow attempt was cancelled, so a reply
that arrived a moment later was thrown away and paid for twice. Now the next
attempt starts beside the slow one and the first answer wins; the other is
cancelled.
"""

import asyncio
import time
from typing import List

import pytest

from ciris_engine.logic.dma.dma_executor import run_dma_with_retries
from ciris_engine.logic.utils import hedging


@pytest.fixture(autouse=True)
def _fast_hedge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hedging, "hedge_after_s", lambda name: 0.1)
    hedging.reset()


class Attempts:
    """Each call takes the next scripted (delay, outcome); records what was cancelled."""

    def __init__(self, *script: tuple) -> None:
        self.script = list(script)
        self.started = 0
        self.cancelled: List[int] = []

    async def __call__(self) -> str:
        self.started += 1
        n = self.started
        delay, outcome = self.script[n - 1]
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            self.cancelled.append(n)
            raise
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_a_late_first_answer_wins_and_the_hedge_is_cancelled() -> None:
    attempts = Attempts((0.3, "first"), (5.0, "second"))
    attempts.__name__ = "run_slow"  # type: ignore[attr-defined]
    began = time.monotonic()
    assert await run_dma_with_retries(attempts, retry_limit=2, timeout_seconds=5.0) == "first"
    assert time.monotonic() - began < 1.0, "the first reply was not taken when it arrived"
    assert attempts.started == 2 and attempts.cancelled == [2]


@pytest.mark.asyncio
async def test_the_hedge_answers_and_the_hung_attempt_is_cancelled() -> None:
    attempts = Attempts((5.0, "first"), (0.05, "second"))
    attempts.__name__ = "run_hung"  # type: ignore[attr-defined]
    assert await run_dma_with_retries(attempts, retry_limit=2, timeout_seconds=5.0) == "second"
    assert attempts.cancelled == [1]


@pytest.mark.asyncio
async def test_a_single_attempt_profile_never_hedges() -> None:
    attempts = Attempts((0.3, "only"))
    attempts.__name__ = "run_single"  # type: ignore[attr-defined]
    assert await run_dma_with_retries(attempts, retry_limit=1, timeout_seconds=5.0) == "only"
    assert attempts.started == 1


@pytest.mark.asyncio
async def test_a_hedge_that_fails_outright_does_not_end_the_slow_attempt() -> None:
    attempts = Attempts((0.3, "first"), (0.0, ValueError("not a transport failure")))
    attempts.__name__ = "run_mixed"  # type: ignore[attr-defined]
    assert await run_dma_with_retries(attempts, retry_limit=2, timeout_seconds=5.0) == "first"


def test_the_hedge_point_is_the_recent_p95_and_needs_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()  # the real hedge_after_s
    hedging.reset()
    assert hedging.hedge_after_s("run_x") is None, "no history: no hedge"
    for seconds in range(1, 41):
        hedging.record_latency("run_x", float(seconds))
    assert hedging.hedge_after_s("run_x") == 39.0
    for _ in range(30):
        hedging.record_latency("run_y", 2.0)
    assert hedging.hedge_after_s("run_y") == hedging.HEDGE_FLOOR_S


@pytest.mark.asyncio
async def test_without_history_a_slow_attempt_is_not_hedged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()
    hedging.reset()
    attempts = Attempts((0.3, "only"), (0.0, "never"))
    attempts.__name__ = "run_cold"  # type: ignore[attr-defined]
    assert await run_dma_with_retries(attempts, retry_limit=2, timeout_seconds=5.0) == "only"
    assert attempts.started == 1


@pytest.mark.asyncio
async def test_a_spent_hedge_budget_stops_hedging() -> None:
    """When most calls are slow together (a degraded provider), hedging stops
    instead of doubling the load: at most HEDGE_BUDGET of recent attempts."""
    first = Attempts((0.3, "a"), (5.0, "hedge"))
    first.__name__ = "run_budget"  # type: ignore[attr-defined]
    assert await run_dma_with_retries(first, retry_limit=2, timeout_seconds=5.0) == "a"
    assert first.started == 2, "the first slow call may hedge"
    second = Attempts((0.3, "b"), (5.0, "hedge"))
    second.__name__ = "run_budget"  # type: ignore[attr-defined]
    assert await run_dma_with_retries(second, retry_limit=2, timeout_seconds=5.0) == "b"
    assert second.started == 1, "the budget (5% of recent attempts) is spent"
