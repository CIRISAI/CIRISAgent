"""Every DMA failure is retried unless a fresh request cannot help (Eric, 2026-11-13).

The executor used to retry only an allow-list (timeout, transport, schema), so a
failure it could not name got one attempt: the es safety battery (run
43522397191) lost q06's answer to one ethical-DMA reply cut off at max_tokens,
and RATCHET Market 4 ac-21 a whole task to one dropped connection.
"""

import pytest

from ciris_engine.logic.dma.dma_executor import run_dma_with_retries
from ciris_engine.logic.dma.exceptions import DMAFailure


class _Flaky:
    __name__ = "run_pdma"  # the executor logs by the DMA function's name

    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "answered"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "LLM call failed (IncompleteOutputException): The output is incomplete due to a max_tokens length limit.",
        "LLM API call failed - circuit breaker activated for failover",
        "something we have never seen",
    ],
)
async def test_an_unrecognised_failure_gets_another_attempt(message: str) -> None:
    flaky = _Flaky(RuntimeError(message))
    assert await run_dma_with_retries(flaky, retry_limit=3, timeout_seconds=5.0) == "answered"
    assert flaky.calls == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "Error code: 401 - Invalid API Key",
        "Error code: 400 - Input too long: 55321 input tokens, limit is 32768",
        "HTTP 500 Insufficient credits: 0 available",
    ],
)
async def test_a_failure_a_fresh_request_cannot_fix_fails_fast(message: str) -> None:
    flaky = _Flaky(RuntimeError(message), RuntimeError(message), RuntimeError(message))
    with pytest.raises(DMAFailure):
        await run_dma_with_retries(flaky, retry_limit=3, timeout_seconds=5.0)
    assert flaky.calls == 1
