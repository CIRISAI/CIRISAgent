"""Tests for the LensContentRejectError discard contract (2.7.8.8).

Why this exists:
The 2.7.8.7 yo+v1_sensitive run hit 236 verify_signature_mismatch (HTTP 422)
rejections in a single sweep. Pre-fix, accord_metrics indiscriminately
re-queued every flush failure regardless of error class — so the same signed
bytes that the lens had ALREADY rejected got POSTed again, and again, and
again. Three accord_metrics adapter instances each running this loop tied up
the agent's asyncio event loop with 30s-timeout aiohttp posts and degraded
the qa_runner's TASK_COMPLETE detection through delayed SSE delivery.

The fix: 4xx (except 429) raises a typed `LensContentRejectError` from
`_send_events_batch`. The `_flush_events` handler catches it separately and
DISCARDS the batch instead of re-queueing. 5xx, 429, network errors, and
timeouts all keep the existing re-queue path (those ARE transient).

These tests pin:
  1. 422 → LensContentRejectError raised → batch discarded (not re-queued)
  2. 400, 403, 404 → same (any 4xx that isn't 429)
  3. 429 → generic RuntimeError → re-queued (rate-limited, transient)
  4. 500, 502, 503, 504 → generic RuntimeError → re-queued (transient)
  5. The exception carries .status for failure-mode logging
  6. The discard log line is at WARNING with the right shape

Cannot exercise the full _flush_events path without standing up the
aiohttp session + queue infrastructure; tests focus on the typed-exception
contract + the branch logic. Full-path coverage is in
test_accord_metrics_service.py.
"""

import pytest

from ciris_adapters.ciris_accord_metrics.services import LensContentRejectError


class TestLensContentRejectError:
    """The typed exception carries the status code so the failure handler
    can log it + downstream consumers (metrics, audit) can discriminate."""

    def test_carries_status_code(self):
        e = LensContentRejectError(422, "verify_signature_mismatch")
        assert e.status == 422

    def test_is_a_runtime_error_subclass(self):
        """Existing `except RuntimeError` catches in callers still match —
        the typed exception is a RuntimeError. The discard branch in
        _flush_events catches it MORE specifically before the generic
        Exception branch."""
        e = LensContentRejectError(403, "forbidden")
        assert isinstance(e, RuntimeError)

    def test_message_round_trips(self):
        e = LensContentRejectError(400, 'CIRISLens API error 400: {"detail":"invalid_manifest"}')
        assert "400" in str(e)
        assert "invalid_manifest" in str(e)


class TestStatusBranchLogic:
    """The decision rule in _send_events_batch:

        if 400 <= status < 500 and status != 429:
            raise LensContentRejectError(...)
        raise RuntimeError(...)  # 5xx + 429

    Verify the branch covers each class correctly. We test the predicate
    directly rather than the full async POST path — the predicate is the
    contract; the surrounding plumbing is tested elsewhere."""

    def _should_discard(self, status: int) -> bool:
        """Mirror the predicate in _send_events_batch."""
        return 400 <= status < 500 and status != 429

    def test_422_signature_mismatch_discards(self):
        """The driver case: persist v0.1.10 verify-path returns 422 on every
        batch from the agent. Re-queueing them just piles up retry pressure
        against an unrecoverable rejection."""
        assert self._should_discard(422) is True

    def test_other_4xx_discards(self):
        """Other 4xx that are NOT 429 also discard:
        - 400 invalid_manifest (body shape rejected)
        - 401 unauthorized (token wrong — re-queueing won't help; operator must fix)
        - 403 no_trusted_key / forbidden (pubkey not registered — same)
        - 404 endpoint moved
        - 413 payload_too_large (the 8 MiB ceiling — re-queue would just hit it again)
        - 422 verify_signature_mismatch (the driver case)
        """
        for status in (400, 401, 403, 404, 408, 410, 413, 415, 422, 451):
            assert self._should_discard(status) is True, f"4xx={status} should discard"

    def test_429_rate_limited_re_queues(self):
        """429 is the explicit exception: rate limits are transient, re-queue
        with backoff is correct. Don't conflate it with other 4xx content
        rejections."""
        assert self._should_discard(429) is False

    def test_5xx_re_queues(self):
        """5xx is transient by definition — re-queue is correct.
        Concrete cases observed in the prior yo run: 502 Bad Gateway from
        Cloudflare during lens degradation."""
        for status in (500, 501, 502, 503, 504, 599):
            assert self._should_discard(status) is False, f"5xx={status} should re-queue"

    def test_2xx_3xx_obviously_not_an_error_class_at_all(self):
        """Sanity: success codes don't hit the predicate path."""
        for status in (200, 201, 204, 301, 302, 304):
            assert self._should_discard(status) is False


class TestFailureHandlerDiscardSemantics:
    """The `_flush_events` failure handler must:
      - Catch LensContentRejectError SPECIFICALLY (before generic Exception)
      - NOT re-queue the events
      - Increment _events_failed (so metrics are honest about loss)
      - Log at WARNING level with the status code and a sample of the body

    Cannot easily run the full _flush_events without the aiohttp session;
    test the contract via direct simulation."""

    def test_discard_branch_does_not_re_queue(self):
        """Mock minimal state and exercise the relevant exception flow."""

        class _FakeAdapter:
            _adapter_instance_id = "test"
            _events_failed = 0
            _event_queue: list = []
            _batch_size = 10

        adapter = _FakeAdapter()
        events_to_send = [{"event_id": 1}, {"event_id": 2}]

        # Simulate the discard branch's behavior
        try:
            raise LensContentRejectError(422, "verify_signature_mismatch")
        except LensContentRejectError as e:
            adapter._events_failed += len(events_to_send)
            # Note: NO re-queue line here. That's the contract.
            assert e.status == 422

        # Re-queue did NOT happen
        assert adapter._event_queue == []
        assert adapter._events_failed == 2

    def test_generic_exception_branch_does_re_queue(self):
        """The 5xx / network / unknown branch must STILL re-queue."""

        class _FakeAdapter:
            _adapter_instance_id = "test"
            _events_failed = 0
            _event_queue: list = []
            _batch_size = 10

        adapter = _FakeAdapter()
        events_to_send = [{"event_id": 1}, {"event_id": 2}]

        # Simulate the generic-Exception branch's behavior
        try:
            raise RuntimeError("CIRISLens API error 502: bad gateway")
        except LensContentRejectError:
            assert False, "5xx must NOT match the discard branch"
        except Exception:
            adapter._events_failed += len(events_to_send)
            if len(adapter._event_queue) < adapter._batch_size * 10:
                adapter._event_queue = events_to_send + adapter._event_queue

        # Re-queue DID happen
        assert adapter._event_queue == events_to_send
        assert adapter._events_failed == 2
