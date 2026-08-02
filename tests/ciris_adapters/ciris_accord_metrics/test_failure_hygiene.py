"""Repeated-failure log hygiene (#933) — the post-fold surface.

The 2.7.x-era defect was an HTTP flush loop retrying a permanently-failing
401 (`verify_unknown_key`) on a fixed ~20s cadence forever, one full
traceback per attempt. The 2.9.6 LensCore fold (#857) removed that HTTP
shipping path wholesale, so on 2.9.7 the failure class manifests
differently — and these tests pin the hygiene contract on what remains:

* Per-event capture failures (``LensClient.capture_event`` — including the
  ``verify_unknown_key`` ValueError that ``Engine.receive_and_persist``
  raises while the backend does not know the signer key, i.e. the lens
  collector migration window): ONE ERROR at the state transition naming
  the key-registration remedy, steady-state failures to counters, a failed
  event is dropped (never re-queued/retried), recovery logged once at INFO
  and automatic — the next reasoning event is the re-probe.
* The one remaining timer-driven loop (``_periodic_sweep``): exponential
  backoff (base = configured interval, ×2 per consecutive failure, capped
  at SWEEP_BACKOFF_MAX_SECONDS, never below the configured base) with
  transition-only logging and reset-on-success.
* The degraded condition is adapter STATE (get_metrics), not a log stream.
* Buffer policy: the only agent-side buffer is the bounded reasoning-stream
  queue (REASONING_QUEUE_MAXSIZE); on overflow the publisher drops the new
  update with a warning (step_streaming.py, drop-newest) — nothing grows
  without bound and nothing is re-queued on failure.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

import pytest

from ciris_adapters.ciris_accord_metrics.services import (
    REASONING_QUEUE_MAXSIZE,
    SWEEP_BACKOFF_MAX_SECONDS,
    SWEEP_BACKOFF_MULTIPLIER,
    AccordMetricsService,
    CaptureHealthState,
    FailureStreak,
)

SERVICES_LOGGER = "ciris_adapters.ciris_accord_metrics.services"

AUTH_ERROR_TEXT = "receive_and_persist: verify_unknown_key"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class ScriptedLens:
    """LensClient capture/sweep stand-in driven by scripted steps.

    Each script entry is either an Exception instance (raised) or a return
    value (capture: outcome dict; sweep: purged count). When a script is
    exhausted, capture returns {"outcome": "appended"} and sweep returns 0.
    """

    capture_script: List[Any] = field(default_factory=list)
    sweep_script: List[Any] = field(default_factory=list)
    capture_calls: int = 0
    sweep_calls: int = 0

    def capture_event(self, component: Dict[str, Any]) -> Dict[str, Any]:
        self.capture_calls += 1
        step = self.capture_script.pop(0) if self.capture_script else {"outcome": "appended"}
        if isinstance(step, BaseException):
            raise step
        return step

    def orphan_sweep(self, max_age_secs: int) -> int:
        self.sweep_calls += 1
        step = self.sweep_script.pop(0) if self.sweep_script else 0
        if isinstance(step, BaseException):
            raise step
        return step


def _make_service() -> AccordMetricsService:
    svc = AccordMetricsService(
        config={
            "consent_given": True,
            "consent_timestamp": "2026-01-01T00:00:00Z",
            "trace_level": "generic",
        }
    )
    # Skip the engine-derived hash lookup on every event.
    svc._agent_id_hash = "testhash0000000"
    return svc


def _event(thought_id: str, event_type: str = "THOUGHT_START") -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "thought_id": thought_id,
        "task_id": "task-1",
        "timestamp": "2026-07-30T00:00:00Z",
    }


async def _feed(svc: AccordMetricsService, events: List[Dict[str, Any]]) -> None:
    """Feed events through the per-event-isolated stream handler."""
    await svc._handle_reasoning_event({"events": events})


def _health_records(caplog: pytest.LogCaptureFixture, level: int) -> List[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno == level and "[ACCORD_HEALTH]" in r.getMessage()]


@pytest.fixture(autouse=True)
def _clean_metrics_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep service construction deterministic regardless of the host env."""
    for name in (
        "CONSENT",
        "CONSENT_TIMESTAMP",
        "TRACE_LEVEL",
        "LOCAL_COPY_DIR",
        "FLUSH_INTERVAL",
        "ORPHAN_MAX_AGE",
        "CAPTURE_DEFERRALS",
    ):
        monkeypatch.delenv(f"CIRIS_ACCORD_METRICS_{name}", raising=False)
        monkeypatch.delenv(f"CIRIS_COVENANT_METRICS_{name}", raising=False)
    monkeypatch.delenv("CIRIS_SHARE_LOCATION_IN_TRACES", raising=False)


# ---------------------------------------------------------------------------
# Capture domain: the 401-analog (verify_unknown_key) and transient failures
# ---------------------------------------------------------------------------


class TestCaptureAuthFailure:
    """The post-fold 401: verify_unknown_key from Engine.receive_and_persist."""

    async def test_persistent_auth_failure_logs_one_error_and_degrades(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=SERVICES_LOGGER)
        svc = _make_service()
        lens = ScriptedLens(capture_script=[ValueError(AUTH_ERROR_TEXT) for _ in range(5)])
        svc._lens = lens

        await _feed(svc, [_event(f"th-{i}") for i in range(5)])

        errors = _health_records(caplog, logging.ERROR)
        assert len(errors) == 1, [r.getMessage() for r in errors]
        msg = errors[0].getMessage()
        assert "DEGRADED (auth)" in msg
        assert "verify_unknown_key" in msg
        assert "register" in msg.lower()  # names the remedy
        assert errors[0].exc_info is None  # no traceback for the known auth class

        metrics = svc.get_metrics()
        assert metrics["capture_state"] == CaptureHealthState.DEGRADED_AUTH.value
        assert metrics["capture_consecutive_failures"] == 5
        assert metrics["capture_failures_total"] == 5
        assert metrics["capture_last_error_class"] == "ValueError"
        assert metrics["failure_logs_suppressed"] == 4
        assert metrics["events_failed"] == 5

        # One attempt per event — a failed event is dropped, never re-queued.
        assert lens.capture_calls == 5

    async def test_transient_failure_transition_carries_traceback(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG, logger=SERVICES_LOGGER)
        svc = _make_service()
        svc._lens = ScriptedLens(capture_script=[RuntimeError("substrate db locked") for _ in range(3)])

        await _feed(svc, [_event(f"th-{i}") for i in range(3)])

        errors = _health_records(caplog, logging.ERROR)
        assert len(errors) == 1
        assert "DEGRADED —" in errors[0].getMessage()
        assert errors[0].exc_info is not None  # first failure keeps its traceback

        metrics = svc.get_metrics()
        assert metrics["capture_state"] == CaptureHealthState.DEGRADED.value
        assert metrics["capture_consecutive_failures"] == 3
        assert metrics["failure_logs_suppressed"] == 2

    async def test_failure_class_change_is_a_logged_transition(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG, logger=SERVICES_LOGGER)
        svc = _make_service()
        svc._lens = ScriptedLens(
            capture_script=[
                RuntimeError("substrate db locked"),
                ValueError(AUTH_ERROR_TEXT),
                RuntimeError("substrate db locked again"),
            ]
        )

        await _feed(svc, [_event(f"th-{i}") for i in range(3)])

        errors = _health_records(caplog, logging.ERROR)
        # DEGRADED -> DEGRADED_AUTH -> DEGRADED: each class change is a transition.
        assert len(errors) == 3
        assert svc.get_metrics()["capture_state"] == CaptureHealthState.DEGRADED.value


class TestCaptureRecovery:
    async def test_success_after_failure_logs_recovery_once_and_resets(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=SERVICES_LOGGER)
        svc = _make_service()
        svc._lens = ScriptedLens(
            capture_script=[
                ValueError(AUTH_ERROR_TEXT),
                ValueError(AUTH_ERROR_TEXT),
                {"outcome": "appended"},
                {"outcome": "appended"},
            ]
        )

        await _feed(svc, [_event(f"th-{i}") for i in range(4)])

        assert len(_health_records(caplog, logging.ERROR)) == 1
        recoveries = [r for r in _health_records(caplog, logging.INFO) if "RECOVERED" in r.getMessage()]
        assert len(recoveries) == 1
        assert "after 2 consecutive failure(s)" in recoveries[0].getMessage()

        metrics = svc.get_metrics()
        assert metrics["capture_state"] == CaptureHealthState.HEALTHY.value
        assert metrics["capture_consecutive_failures"] == 0
        assert metrics["capture_failures_total"] == 2  # lifetime counter survives recovery
        assert metrics["failure_logs_suppressed"] == 0  # streak gauges reset

    async def test_happy_path_emits_no_health_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG, logger=SERVICES_LOGGER)
        svc = _make_service()
        svc._lens = ScriptedLens(
            capture_script=[
                {"outcome": "opened"},
                {
                    "outcome": "sealed_and_persisted",
                    "trace_id": "tr-1",
                    "trace_events_inserted": 3,
                    "signatures_verified": 1,
                },
            ]
        )

        await _feed(svc, [_event("th-1"), _event("th-1", "ACTION_RESULT")])

        assert not [r for r in caplog.records if "[ACCORD_HEALTH]" in r.getMessage()]
        metrics = svc.get_metrics()
        assert metrics["capture_state"] == CaptureHealthState.HEALTHY.value
        assert metrics["sweep_state"] == CaptureHealthState.HEALTHY.value
        assert metrics["traces_completed"] == 1
        assert metrics["events_failed"] == 0


# ---------------------------------------------------------------------------
# Sweep domain: exponential backoff with cap, reset on success
# ---------------------------------------------------------------------------


async def _run_sweep_with_fake_sleep(
    svc: AccordMetricsService, monkeypatch: pytest.MonkeyPatch, max_sleeps: int
) -> List[float]:
    """Drive _periodic_sweep, recording every requested sleep delay.

    The fake sleep returns immediately and cancels the loop (the same way
    stop() would) after max_sleeps iterations.
    """
    delays: List[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) >= max_sleeps:
            raise asyncio.CancelledError
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    await svc._periodic_sweep()  # exits cleanly on CancelledError
    return delays


class TestSweepBackoff:
    async def test_backoff_doubles_and_caps(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=SERVICES_LOGGER)
        svc = _make_service()
        svc._sweep_interval = 60.0
        svc._sweep_interval_current = 60.0
        svc._lens = ScriptedLens(sweep_script=[RuntimeError("orphan sweep broken") for _ in range(6)])

        delays = await _run_sweep_with_fake_sleep(svc, monkeypatch, max_sleeps=7)

        # base, then x2 per consecutive failure, capped at 900s.
        assert delays == [60.0, 120.0, 240.0, 480.0, 900.0, 900.0, 900.0]
        assert len(_health_records(caplog, logging.ERROR)) == 1  # transition only

        metrics = svc.get_metrics()
        assert metrics["sweep_state"] == CaptureHealthState.DEGRADED.value
        assert metrics["sweep_consecutive_failures"] == 6
        assert metrics["sweep_interval_current_seconds"] == SWEEP_BACKOFF_MAX_SECONDS

    async def test_success_resets_interval_and_logs_recovery_once(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=SERVICES_LOGGER)
        svc = _make_service()
        svc._sweep_interval = 60.0
        svc._sweep_interval_current = 60.0
        svc._lens = ScriptedLens(
            sweep_script=[RuntimeError("orphan sweep broken"), RuntimeError("orphan sweep broken")]
        )

        delays = await _run_sweep_with_fake_sleep(svc, monkeypatch, max_sleeps=5)

        # Two failures back off, first success snaps back to the base cadence.
        assert delays == [60.0, 120.0, 240.0, 60.0, 60.0]
        recoveries = [r for r in _health_records(caplog, logging.INFO) if "RECOVERED" in r.getMessage()]
        assert len(recoveries) == 1

        metrics = svc.get_metrics()
        assert metrics["sweep_state"] == CaptureHealthState.HEALTHY.value
        assert metrics["sweep_consecutive_failures"] == 0
        assert metrics["sweep_interval_current_seconds"] == 60.0

    async def test_backoff_never_drops_below_configured_interval(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An operator interval above the cap must not be reduced by the cap."""
        svc = _make_service()
        svc._sweep_interval = 1200.0
        svc._sweep_interval_current = 1200.0
        svc._lens = ScriptedLens(sweep_script=[RuntimeError("orphan sweep broken") for _ in range(2)])

        delays = await _run_sweep_with_fake_sleep(svc, monkeypatch, max_sleeps=2)

        assert delays == [1200.0, 1200.0]
        assert svc.get_metrics()["sweep_interval_current_seconds"] == 1200.0


# ---------------------------------------------------------------------------
# Policy constants + classifier
# ---------------------------------------------------------------------------


class TestPolicy:
    def test_buffer_policy_is_explicit_and_bounded(self) -> None:
        """The only agent-side buffer is the bounded subscription queue.

        On overflow the publisher (step_streaming.py) drops the NEW update
        with a warning (drop-newest); a failed capture is dropped, never
        re-queued (asserted in TestCaptureAuthFailure via capture_calls).
        """
        assert REASONING_QUEUE_MAXSIZE == 1000

    def test_backoff_constants(self) -> None:
        assert SWEEP_BACKOFF_MULTIPLIER == 2.0
        assert SWEEP_BACKOFF_MAX_SECONDS == 900.0  # the ~15 min slow re-probe cadence

    def test_classifier_maps_verify_unknown_key_to_auth(self) -> None:
        assert (
            AccordMetricsService._classify_failure(ValueError(AUTH_ERROR_TEXT)) is CaptureHealthState.DEGRADED_AUTH
        )
        assert AccordMetricsService._classify_failure(RuntimeError("timeout")) is CaptureHealthState.DEGRADED

    def test_streak_defaults_are_healthy(self) -> None:
        streak = FailureStreak("capture")
        assert streak.state is CaptureHealthState.HEALTHY
        assert streak.consecutive_failures == 0
        assert streak.total_failures == 0
