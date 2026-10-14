"""The CIRISVerify mandatory disclosure reaches the trace row and the API (CIRISAgent#804, D17).

`VerifyAttestationContext.disclosure_text` is documented as "MUST be visible in
all contexts" (FSD-001): the agent's LLM context, the accord trace shipped to
CIRISLens, and API responses. Until this file, nothing asserted the trace or
API legs; the projection was implicit and could drop the text with every test
still green.

This drives the real path end to end, starting from a `VerifyAttestationContext`
with a known disclosure:

    VerifyAttestationContext
      -> SystemSnapshot.verify_attestation
      -> SNAPSHOT_AND_CONTEXT reasoning event (step_decorators)
      -> reasoning_event_stream.broadcast_reasoning_event
         |-> AccordMetricsService._handle_reasoning_event
         |     -> _extract_component_data -> egress schema -> LensClient.capture_event
         |        (the component the substrate seals and persists as the trace row)
         `-> GET /v1/system/runtime/reasoning-stream SSE frame
               (admin, and an OBSERVER through the redaction path)

The substrate (LensClient) is a recording fake: these tests own the agent-side
projection, not lens-core's persistence, and nothing here opens a socket.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, List, cast
from unittest.mock import patch

import pytest

from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService, TraceDetailLevel
from ciris_engine.logic.adapters.api.routes.system_extensions import _process_stream_event
from ciris_engine.logic.infrastructure.step_streaming import ReasoningEventStream
from ciris_engine.logic.processors.core.step_decorators import _create_snapshot_and_context_event
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.runtime.system_context import SystemSnapshot
from ciris_engine.schemas.services.attestation import VerifyAttestationContext
from ciris_engine.schemas.streaming.reasoning_stream import create_reasoning_event

#: Distinctive, so a substring hit cannot be a coincidence.
DISCLOSURE = "D17-PROBE-804: community agent, not professionally licensed. Do not rely on it for licensed advice."
THOUGHT_ID = "th_disclosure_804"
TASK_ID = "task_disclosure_804"


@dataclass
class _RecordingLens:
    """Stand-in for ciris_lens_core.LensClient: records every component."""

    captured: List[Dict[str, Any]] = field(default_factory=list)

    def capture_event(self, component: Dict[str, Any]) -> Dict[str, Any]:
        self.captured.append(component)
        return {"outcome": "appended"}

    def orphan_sweep(self, max_age_secs: int) -> int:
        return 0


@pytest.fixture(autouse=True)
def _deterministic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("CONSENT", "CONSENT_TIMESTAMP", "TRACE_LEVEL", "LOCAL_COPY_DIR"):
        monkeypatch.delenv(f"CIRIS_ACCORD_METRICS_{name}", raising=False)
        monkeypatch.delenv(f"CIRIS_COVENANT_METRICS_{name}", raising=False)
    # Same rationale as tests/adapters/accord_metrics/conftest.py: without a
    # scrubbable substrate the service downgrades full_traces -> detailed, and
    # this file asserts each level as requested.
    import ciris_adapters.ciris_accord_metrics.services as svc

    monkeypatch.setattr(svc, "substrate_can_scrub", lambda: True, raising=True)


def _attestation(severity: str = "warning") -> VerifyAttestationContext:
    return VerifyAttestationContext(
        attestation_level=2,
        attestation_status="verified",
        attestation_summary="Level 2/5 | ✓Binary ✓Environment ✗Registry",
        disclosure_text=DISCLOSURE,
        disclosure_severity=severity,
        key_status="ephemeral",
        binary_ok=True,
        env_ok=True,
    )


def _snapshot_event(attestation: VerifyAttestationContext) -> Any:
    """The SNAPSHOT_AND_CONTEXT event exactly as the pipeline builds it."""
    snapshot = SystemSnapshot(verify_attestation=attestation)
    thought_item = SimpleNamespace(initial_context={"system_snapshot": snapshot})
    # The builder reads only thought_id / task_id off the step data.
    step_data = cast(Any, SimpleNamespace(thought_id=THOUGHT_ID, task_id=TASK_ID))
    return _create_snapshot_and_context_event(
        step_data, "2026-10-14T00:00:00Z", create_reasoning_event, thought_item=thought_item
    )


async def _broadcast(attestation: VerifyAttestationContext) -> Dict[str, Any]:
    """Broadcast through a fresh stream (not the global singleton) and return the update."""
    stream = ReasoningEventStream()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    stream.subscribe(queue)
    await stream.broadcast_reasoning_event(_snapshot_event(attestation))
    update: Dict[str, Any] = queue.get_nowait()
    return update


def test_the_event_itself_carries_the_disclosure() -> None:
    """Leg 0: the typed event holds the disclosure before anything serializes it."""
    event = _snapshot_event(_attestation())
    assert event.system_snapshot.verify_attestation is not None
    assert event.system_snapshot.verify_attestation.disclosure_text == DISCLOSURE


# --- the trace row ---------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("level", list(TraceDetailLevel))
async def test_disclosure_text_reaches_the_trace_component_at_every_level(level: TraceDetailLevel) -> None:
    """The component handed to the substrate for sealing carries the disclosure.

    `attestation_context` is the GENERIC-tier text field the egress schema
    allows precisely for this (egress_schema.py "agent-authored attestation
    disclosure"); FSD-001 requires it at all three levels, so all three are
    asserted -- GENERIC is the default and the one most likely to be trimmed.
    """
    service = AccordMetricsService(
        config={"consent_given": True, "consent_timestamp": "2026-01-01T00:00:00Z", "trace_level": level.value}
    )
    lens = _RecordingLens()
    service._lens = lens

    update = await _broadcast(_attestation())
    await service._handle_reasoning_event(update)

    assert len(lens.captured) == 1, "the SNAPSHOT_AND_CONTEXT event never reached the substrate"
    component = lens.captured[0]
    assert component["event_type"] == "SNAPSHOT_AND_CONTEXT"
    assert component["thought_id"] == THOUGHT_ID
    data = component["data"]
    assert DISCLOSURE in (data.get("attestation_context") or ""), (
        f"disclosure_text dropped from the {level.value} trace row: "
        f"attestation_context={data.get('attestation_context')!r}"
    )
    assert "⚠️ WARNING" in data["attestation_context"], "severity prefix lost"
    assert data["disclosure_severity"] == "warning"
    # The signed bytes are JSON; the disclosure must survive that encoding.
    assert DISCLOSURE in json.dumps(component, ensure_ascii=False)


@pytest.mark.asyncio
async def test_an_empty_disclosure_adds_no_notice_line() -> None:
    """Negative control: the assertion above is not satisfied by some other
    text that happens to land in attestation_context."""
    service = AccordMetricsService(
        config={"consent_given": True, "consent_timestamp": "2026-01-01T00:00:00Z", "trace_level": "generic"}
    )
    lens = _RecordingLens()
    service._lens = lens
    empty = _attestation().model_copy(update={"disclosure_text": ""})

    await service._handle_reasoning_event(await _broadcast(empty))

    context = lens.captured[0]["data"]["attestation_context"] or ""
    assert DISCLOSURE not in context
    assert "WARNING" not in context and "NOTICE" not in context


# --- the API response ------------------------------------------------------


def _sse_payload(frame: str) -> Dict[str, Any]:
    assert frame.startswith("event: step_update\n"), frame[:80]
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    payload: Dict[str, Any] = json.loads(data_line[len("data: ") :])
    return payload


def _disclosure_in(payload: Dict[str, Any]) -> str:
    (event,) = payload["events"]
    assert event["event_type"] == "snapshot_and_context"
    verify = event["system_snapshot"]["verify_attestation"]
    assert verify is not None, "verify_attestation stripped from the API payload"
    text: str = verify["disclosure_text"]
    return text


@pytest.mark.asyncio
async def test_disclosure_text_reaches_the_reasoning_stream_response_for_an_admin() -> None:
    """GET /v1/system/runtime/reasoning-stream: the SSE frame the client receives."""
    queue: asyncio.Queue[Any] = asyncio.Queue()
    await queue.put(await _broadcast(_attestation()))

    frame = await _process_stream_event(queue, True, UserRole.ADMIN, set(), set(), {})

    assert frame is not None
    payload = _sse_payload(frame)
    assert _disclosure_in(payload) == DISCLOSURE
    assert payload["events"][0]["system_snapshot"]["verify_attestation"]["disclosure_severity"] == "warning"


@pytest.mark.asyncio
async def test_observer_redaction_keeps_the_disclosure() -> None:
    """OBSERVERs get a redacted snapshot (task summaries, other users'
    profiles). The mandatory disclosure is not theirs to lose."""
    queue: asyncio.Queue[Any] = asyncio.Queue()
    await queue.put(await _broadcast(_attestation()))

    async def _channels(task_ids: List[str]) -> Dict[str, str]:
        return {TASK_ID: "api_observer_channel"}

    with patch(
        "ciris_engine.logic.adapters.api.routes.system_extensions._batch_fetch_task_channel_ids",
        side_effect=_channels,
    ):
        frame = await _process_stream_event(
            queue, False, UserRole.OBSERVER, {"api_observer_channel"}, {"observer-user"}, {}
        )

    assert frame is not None, "the observer's own event was filtered out; the test proves nothing"
    assert _disclosure_in(_sse_payload(frame)) == DISCLOSURE
