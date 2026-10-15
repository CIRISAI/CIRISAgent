"""Under the mock guard, the substrate's mock-LLM refusal is the design, not a capture failure (#1262).

Since ciris-server 0.5.226 lens-core tees a sealed mock trace to the local copy
and THEN refuses to persist it (`trace_mock_llm_refused`, CIRISServer#766/#767).
The adapter used to count that as a capture failure and log "[ACCORD_HEALTH]
capture DEGRADED" at ERROR on every mock trace, which tripped the staged-QA
incidents gate on every backend with all tests green.
"""

import logging
from typing import Any, Dict, List

import pytest

from ciris_adapters.ciris_accord_metrics.services import (
    MOCK_LLM_REFUSAL_TOKEN,
    AccordMetricsService,
    CaptureHealthState,
)

SERVICES_LOGGER = "ciris_adapters.ciris_accord_metrics.services"
REFUSAL = RuntimeError(f"{MOCK_LLM_REFUSAL_TOKEN}: this trace was produced by the mock LLM and is not persisted")


class RefusingLens:
    """lens-core under the 0.5.226 ingest guard: every seal is refused after the tee."""

    def __init__(self) -> None:
        self.calls = 0

    def capture_event(self, component: Dict[str, Any]) -> Dict[str, Any]:
        self.calls += 1
        if component.get("event_type") == "ACTION_RESULT":
            raise REFUSAL
        return {"outcome": "opened"}


def _service(mock_guard: bool) -> AccordMetricsService:
    svc = AccordMetricsService(
        config={"consent_given": True, "consent_timestamp": "2026-01-01T00:00:00Z", "trace_level": "generic"}
    )
    svc._agent_id_hash = "testhash0000000"
    svc._lens = RefusingLens()
    svc._lens_local_only = mock_guard
    return svc


def _events(n: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i in range(n):
        for event_type in ("THOUGHT_START", "ACTION_RESULT"):
            out.append(
                {"event_type": event_type, "thought_id": f"th-{i}", "task_id": "t", "timestamp": "2026-10-15T00:00:00Z"}
            )
    return out


def _errors(caplog: pytest.LogCaptureFixture) -> List[logging.LogRecord]:
    return [r for r in caplog.records if r.name == SERVICES_LOGGER and r.levelno >= logging.ERROR]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("CONSENT", "CONSENT_TIMESTAMP", "TRACE_LEVEL", "LOCAL_COPY_DIR", "FLUSH_INTERVAL"):
        monkeypatch.delenv(f"CIRIS_ACCORD_METRICS_{name}", raising=False)


@pytest.mark.asyncio
async def test_mock_refusal_under_the_guard_is_counted_not_an_error(caplog, monkeypatch):
    from ciris_engine.logic.utils import mock_llm_guard

    monkeypatch.setattr(mock_llm_guard, "is_mock_llm_active", lambda: True)
    caplog.set_level(logging.DEBUG, logger=SERVICES_LOGGER)
    svc = _service(mock_guard=True)
    await svc._handle_reasoning_event({"events": _events(5)})

    assert _errors(caplog) == []  # the QA incidents gate counts ERROR lines
    metrics = svc.get_metrics()
    assert metrics["traces_mock_refused"] == 5
    assert metrics["events_failed"] == 0
    assert metrics["capture_state"] == CaptureHealthState.HEALTHY.value
    assert not svc._open_thoughts  # each refused trace is closed, not left in flight
    infos = [r for r in caplog.records if r.levelno == logging.INFO and "mock-LLM trace teed" in r.getMessage()]
    assert len(infos) == 1  # said once, then counted


@pytest.mark.asyncio
async def test_the_same_refusal_with_a_real_llm_is_still_a_failure(caplog, monkeypatch):
    """Not a blanket suppression: a mock refusal of a real-LLM trace is an anomaly."""
    from ciris_engine.logic.utils import mock_llm_guard

    monkeypatch.setattr(mock_llm_guard, "is_mock_llm_active", lambda: False)
    caplog.set_level(logging.DEBUG, logger=SERVICES_LOGGER)
    svc = _service(mock_guard=False)
    await svc._handle_reasoning_event({"events": _events(2)})

    errors = _errors(caplog)
    assert errors and all(MOCK_LLM_REFUSAL_TOKEN in r.getMessage() for r in errors)
    metrics = svc.get_metrics()
    assert metrics["traces_mock_refused"] == 0
    assert metrics["events_failed"] == 2
    assert metrics["capture_state"] != CaptureHealthState.HEALTHY.value
