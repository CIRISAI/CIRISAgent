"""The memory benchmark yields to the agent's back-pressure instead of storming it.

Since the pressure ladder (8b664fb9a) the agent answers a burst with 503 +
Retry-After when ``thoughts_active`` crosses its SHED limit. That is correct
agent behaviour; the benchmark has to wait it out and resubmit the same
message, not drop it after three sub-second retries (which also tripped the
API rate limiter into 429s). These tests drive ``send_messages`` through an
``httpx.MockTransport`` with a fake clock, so no server and no real waiting.
"""

from __future__ import annotations

import asyncio
from typing import Callable, List

import httpx
import pytest

from tools import memory_benchmark as mb

BASE = "http://bench.test"


class FakeTime:
    """A clock that only moves when the code under test sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: List[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        # Concurrent sleepers overlap: each wakes at its own start + seconds,
        # and the clock never runs backwards.
        self.sleeps.append(seconds)
        wake = self.now + seconds
        await asyncio.sleep(0)
        self.now = max(self.now, wake)


def shed(retry_after: int = 30, header: bool = True) -> httpx.Response:
    """The 503 `_raise_if_shed` answers with (HTTPException → body nested under "detail")."""
    return httpx.Response(
        503,
        headers={"Retry-After": str(retry_after)} if header else {},
        json={
            "detail": {
                "error": "resource_shed",
                "reason": "resource_shed",
                "message": "The agent is not admitting new work while a resource is under pressure. Retry later.",
                "resources": ["thoughts_active"],
                "retry_after_seconds": retry_after,
            }
        },
    )


def rate_limited(retry_after: int = 5, header: bool = True) -> httpx.Response:
    """The 429 the rate-limit middleware answers with (top-level body)."""
    return httpx.Response(
        429,
        headers={"Retry-After": str(retry_after)} if header else {},
        json={"detail": "Too many requests.", "error": "rate_limit_exceeded", "retry_after": retry_after},
    )


def locked(error: str = "node_unclaimed") -> httpx.Response:
    return httpx.Response(423, json={"detail": {"error": error, "reason": error, "message": "locked"}})


def accepted(n: int) -> httpx.Response:
    return httpx.Response(200, json={"data": {"task_id": f"task-{n}"}})


def run(
    handler: Callable[[httpx.Request], httpx.Response],
    fake: FakeTime,
    messages: int = 1,
    concurrency: int = 1,
    **kwargs: float,
) -> mb.SendResult:
    return asyncio.run(
        mb.send_messages(
            BASE,
            messages,
            "token",
            concurrency,
            process_tasks=False,
            transport=httpx.MockTransport(handler),
            sleep=fake.sleep,
            clock=fake.clock,
            rng=lambda: 0.0,  # no jitter: waits are exactly Retry-After
            **kwargs,
        )
    )


def scripted(responses: List[httpx.Response], then: Callable[[int], httpx.Response] = accepted):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if responses:
            return responses.pop(0)
        return then(calls["n"])

    return handler, calls


def test_retry_after_header_is_honoured_and_same_message_resubmitted() -> None:
    fake = FakeTime()
    handler, calls = scripted([shed(7), shed(7)])
    result = run(handler, fake)

    assert (result.success, result.failed) == (1, 0)
    assert calls["n"] == 3
    assert fake.sleeps == [7.0, 7.0]
    assert result.retry_after_wait_total == pytest.approx(14.0)
    assert result.shed_refusals == 2
    assert result.shed_resources == {"thoughts_active": 2}
    assert result.response_reasons == {"http_503_resource_shed": 2}


def test_retry_after_from_body_when_header_absent() -> None:
    fake = FakeTime()
    handler, _ = scripted([shed(11, header=False), rate_limited(4, header=False)])
    result = run(handler, fake)

    assert result.success == 1
    assert fake.sleeps == [11.0, 4.0]
    assert result.response_reasons == {"http_503_resource_shed": 1, "http_429_rate_limit_exceeded": 1}


def test_default_wait_when_no_retry_after_anywhere() -> None:
    fake = FakeTime()
    handler, _ = scripted([httpx.Response(503, text="busy")])
    result = run(handler, fake)

    assert result.success == 1
    assert fake.sleeps == [mb.DEFAULT_RETRY_AFTER_S]


def test_jitter_is_added_on_top_of_retry_after() -> None:
    fake = FakeTime()
    handler, _ = scripted([shed(30)])
    result = asyncio.run(
        mb.send_messages(
            BASE, 1, "t", 1, False,
            transport=httpx.MockTransport(handler), sleep=fake.sleep, clock=fake.clock, rng=lambda: 1.0,
        )
    )
    assert result.success == 1
    assert fake.sleeps == [pytest.approx(36.0)]  # 30 + 20% of 30, never earlier than asked


def test_no_message_dropped_while_within_its_deadline() -> None:
    """A sustained SHED burst: each worker is refused 4 times running (120 s of waits), none is lost."""
    fake = FakeTime()
    refusals = {"left": 20, "accepted": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if refusals["left"] > 0:
            refusals["left"] -= 1
            return shed(30)
        refusals["accepted"] += 1
        return accepted(refusals["accepted"])

    result = run(handler, fake, messages=20, concurrency=5, per_message_deadline=180, overall_deadline=900)

    assert (result.success, result.failed) == (20, 0)
    assert result.shed_refusals == 20
    assert result.retry_after_wait_total == pytest.approx(20 * 30.0)
    assert len(set(result.task_ids)) == 20


def test_message_past_its_deadline_fails_with_reason() -> None:
    fake = FakeTime()
    result = run(lambda r: shed(30), fake, per_message_deadline=100, overall_deadline=900)

    assert (result.success, result.failed) == (0, 1)
    assert result.failure_reasons == {"deadline_message:http_503_resource_shed": 1}
    # 3 waits of 30 s fit in 100 s; the 4th would end past it and is not slept.
    assert fake.sleeps == [30.0, 30.0, 30.0]


def test_overall_deadline_stops_the_burst() -> None:
    fake = FakeTime()
    result = run(lambda r: shed(30), fake, messages=4, concurrency=1, per_message_deadline=500, overall_deadline=60)

    assert result.success == 0
    assert result.failed == 4
    assert result.failure_reasons["deadline_overall:http_503_resource_shed"] == 1
    assert result.failure_reasons["deadline_overall:not_started"] == 3


def test_423_is_retried_inside_the_startup_grace() -> None:
    fake = FakeTime()
    handler, _ = scripted([locked(), locked("accord_halt")])
    result = run(handler, fake, locked_grace=30)

    assert result.success == 1
    assert fake.sleeps == [mb.LOCKED_RETRY_S, mb.LOCKED_RETRY_S]
    assert result.retry_after_wait_total == 0.0  # not a Retry-After wait


def test_423_after_the_grace_is_fatal_and_stops_the_burst() -> None:
    fake = FakeTime()
    result = run(lambda r: locked(), fake, messages=5, concurrency=1, locked_grace=10)

    assert result.success == 0 and result.failed == 5
    assert result.aborted == "http_423_node_unclaimed"
    assert result.failure_reasons["http_423_node_unclaimed"] == 1
    assert result.failure_reasons["aborted:http_423_node_unclaimed"] == 4


def test_other_errors_get_a_small_bounded_retry() -> None:
    fake = FakeTime()
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={"detail": "boom"})

    result = run(handler, fake)

    assert result.failed == 1
    assert calls["n"] == mb.OTHER_FAILURE_ATTEMPTS
    assert result.failure_reasons == {"http_500": 1}
    assert sum(fake.sleeps) < 1.0


def test_parse_retry_after_http_date() -> None:
    response = httpx.Response(503, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:30 GMT"})
    now = 1445412480.0  # 07:28:00 GMT that day
    assert mb.parse_retry_after(response, None, now_epoch=now) == pytest.approx(30.0)


def _report(processed: int, messages: int = 100, rate: float = 0.99, **kw: int) -> int:
    return mb.report_results(
        messages=messages,
        adapter="api",
        concurrency=20,
        initial_mem=kw.get("initial", 100 * 1024 * 1024),
        final_mem=kw.get("final", 110 * 1024 * 1024),
        peak_mem=kw.get("final", 110 * 1024 * 1024),
        send=mb.SendResult(success=processed, failed=messages - processed, shed_refusals=7),
        processed=processed,
        min_success_rate=rate,
    )


def test_growth_is_reported_per_processed_and_per_submitted(capsys: pytest.CaptureFixture[str]) -> None:
    _report(processed=50)
    out = capsys.readouterr().out
    # 10 MB growth: / 50 processed = 204.8 KB, / 100 submitted = 102.4 KB
    assert "Per Processed:  204.8 KB" in out
    assert "Per Submitted:  102.4 KB" in out
    assert "Shed refusals:  7" in out
    assert "Retry-After waits (total s):" in out


def test_exit_code_non_zero_below_threshold(capsys: pytest.CaptureFixture[str]) -> None:
    assert _report(processed=98) == 1
    assert _report(processed=99) == 0
    assert _report(processed=100) == 0
    assert _report(processed=50, rate=0.5) == 0
    assert _report(processed=0, messages=0) == 1  # nothing measured is not a pass
    assert "Result:         FAIL" in capsys.readouterr().out


def test_a_423_reports_the_halt_or_ownership_reading() -> None:
    """A fail-closed read timeout is not a halt: the reason names the reading."""
    from tools.memory_benchmark import _refusal_reason

    halt_timeout = {"detail": {"error": "accord_halt_in_effect", "halt": {"reading": "node_timeout"}}}
    assert _refusal_reason(423, halt_timeout) == "http_423_accord_halt_in_effect[node_timeout]"
    unclaimed = {"detail": {"error": "node_unclaimed", "message": "This node has no owner (read_timeout: no answer in 2.0s). An agent ..."}}
    assert _refusal_reason(423, unclaimed) == "http_423_node_unclaimed[read_timeout]"
    assert _refusal_reason(503, {"detail": {"error": "resource_shed"}}) == "http_503_resource_shed"
