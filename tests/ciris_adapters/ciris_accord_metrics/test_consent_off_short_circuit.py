"""Without trace consent, reasoning events are not built at all (load-spike RCA).

The substrate client built without consent answers every seal consent_blocked,
so extracting, schema-filtering and building each event's component was pure
cost -- the largest single block of event-loop time under the memory
benchmark's burst. These tests pin the short-circuit, and that a grant landing
mid-run still arms the seal for the next thought.
"""

import logging
from typing import Any, Dict, List

import pytest

from ciris_adapters.ciris_accord_metrics import services as svc_module
from ciris_adapters.ciris_accord_metrics.services import SKIP_LOG_EVERY, AccordMetricsService

SERVICES_LOGGER = "ciris_adapters.ciris_accord_metrics.services"


class RecordingLens:
    """A LensClient double that seals on ACTION_RESULT (or blocks without consent)."""

    def __init__(self, consent: bool) -> None:
        self.consent = consent
        self.components: List[Dict[str, Any]] = []

    def capture_event(self, component: Dict[str, Any]) -> Dict[str, Any]:
        self.components.append(component)
        if component["event_type"] != "ACTION_RESULT":
            return {"outcome": "opened"}
        if not self.consent:
            return {"outcome": "consent_blocked", "reason": "no consent"}
        return {"outcome": "sealed_and_persisted", "trace_id": "t", "trace_events_inserted": 2}


def _service(consent: bool) -> AccordMetricsService:
    config: Dict[str, Any] = {"trace_level": "generic", "consent_given": consent}
    if consent:
        config["consent_timestamp"] = "2026-01-01T00:00:00Z"
    svc = AccordMetricsService(config=config)
    svc._agent_id_hash = "testhash0000000"
    return svc


def _wire(svc: AccordMetricsService, monkeypatch) -> List[RecordingLens]:
    """Make _build_lens_client produce RecordingLens with the service's consent, as the real one does."""
    built: List[RecordingLens] = []

    def _build() -> RecordingLens:
        svc._lens_local_only = False
        svc._lens_consent_armed = bool(svc._consent_given)
        lens = RecordingLens(consent=bool(svc._consent_given))
        built.append(lens)
        return lens

    monkeypatch.setattr(svc, "_build_lens_client", _build)
    svc._lens = svc._build_lens_client()
    return built


def _thought(i: int) -> List[Dict[str, Any]]:
    return [
        {"event_type": t, "thought_id": f"th-{i}", "task_id": "task", "timestamp": "2026-10-29T00:00:00Z"}
        for t in ("THOUGHT_START", "DMA_RESULTS", "ACTION_RESULT")
    ]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("CONSENT", "CONSENT_TIMESTAMP", "TRACE_LEVEL", "LOCAL_COPY_DIR", "FLUSH_INTERVAL"):
        monkeypatch.delenv(f"CIRIS_ACCORD_METRICS_{name}", raising=False)
    from ciris_engine.logic.utils import mock_llm_guard

    monkeypatch.setattr(mock_llm_guard, "is_mock_llm_active", lambda: False)


@pytest.fixture
def no_grant(monkeypatch):
    """No CEG community grant (the self-heal finds nothing)."""
    grant = {"id": None}
    from ciris_engine.logic.services.governance.consent import attestation

    monkeypatch.setattr(attestation, "current_community_grant_id", lambda: grant["id"])
    monkeypatch.setattr(attestation, "current_community_grant_asserted_at", lambda: "2026-10-29T00:00:00Z")
    return grant


@pytest.mark.asyncio
async def test_without_consent_nothing_is_built_or_captured(monkeypatch, no_grant, caplog):
    caplog.set_level(logging.WARNING, logger=SERVICES_LOGGER)
    svc = _service(consent=False)
    built = _wire(svc, monkeypatch)
    extracted: List[str] = []
    monkeypatch.setattr(svc, "_extract_component_data", lambda et, ev: extracted.append(et) or {})

    for i in range(3):
        await svc._handle_reasoning_event({"events": _thought(i)})

    assert built[0].components == []  # the substrate is never asked
    assert extracted == []  # nor is anything extracted
    metrics = svc.get_metrics()
    assert metrics["traces_consent_blocked"] == 3  # each would-be seal still counted
    assert metrics["events_skipped_no_consent"] == 9
    assert metrics["events_failed"] == 0
    # one [SEAL] SKIPPED line, not one per thought
    assert len([r for r in caplog.records if "[SEAL] SKIPPED" in r.getMessage()]) == 1


@pytest.mark.asyncio
async def test_skip_warning_is_rate_limited(monkeypatch, no_grant, caplog):
    caplog.set_level(logging.WARNING, logger=SERVICES_LOGGER)
    svc = _service(consent=False)
    _wire(svc, monkeypatch)
    for i in range(SKIP_LOG_EVERY):
        await svc._handle_reasoning_event({"events": _thought(i)})
    skipped = [r for r in caplog.records if "[SEAL] SKIPPED" in r.getMessage()]
    assert len(skipped) == 2  # the first, then the SKIP_LOG_EVERY-th
    assert f"{SKIP_LOG_EVERY} trace(s) so far" in skipped[-1].getMessage()


@pytest.mark.asyncio
async def test_with_consent_events_are_built_and_sealed(monkeypatch, no_grant):
    svc = _service(consent=True)
    built = _wire(svc, monkeypatch)
    await svc._handle_reasoning_event({"events": _thought(0)})
    assert [c["event_type"] for c in built[0].components] == ["THOUGHT_START", "DMA_RESULTS", "ACTION_RESULT"]
    assert svc.get_metrics()["traces_completed"] == 1
    assert svc.get_metrics()["events_skipped_no_consent"] == 0


@pytest.mark.asyncio
async def test_a_grant_mid_run_arms_the_next_thought(monkeypatch, no_grant):
    svc = _service(consent=False)
    built = _wire(svc, monkeypatch)
    await svc._handle_reasoning_event({"events": _thought(0)})
    assert built[0].components == []

    no_grant["id"] = "grant-1"  # the wizard writes the community grant
    svc._last_consent_recheck = None  # (throttle elapsed)
    await svc._handle_reasoning_event({"events": _thought(1)})

    assert len(built) == 2  # self-heal rebuilt the client with consent
    assert svc._lens_consent_armed is True
    assert [c["thought_id"] for c in built[1].components] == ["th-1", "th-1", "th-1"]
    assert svc.get_metrics()["traces_completed"] == 1


@pytest.mark.asyncio
async def test_self_heal_recheck_stays_throttled(monkeypatch, no_grant):
    svc = _service(consent=False)
    _wire(svc, monkeypatch)
    calls: List[int] = []
    monkeypatch.setattr(svc, "_derive_consent_from_ceg", lambda: calls.append(1) or None)
    for i in range(20):
        await svc._handle_reasoning_event({"events": _thought(i)})
    assert len(calls) == 1  # one re-check per interval, not one per event


@pytest.mark.asyncio
async def test_unbuilt_client_state_does_not_skip(monkeypatch):
    """A client injected without _build_lens_client (consent state unknown) still captures."""
    svc = _service(consent=False)
    lens = RecordingLens(consent=False)
    svc._lens = lens
    svc._lens_local_only = False
    assert svc._lens_consent_armed is None
    monkeypatch.setattr(svc, "_maybe_self_heal_consent", lambda: None)
    await svc._handle_reasoning_event({"events": _thought(0)})
    assert len(lens.components) == 3
    assert svc.get_metrics()["traces_consent_blocked"] == 1  # from the substrate's answer


@pytest.mark.asyncio
async def test_component_is_built_off_the_event_loop(monkeypatch, no_grant):
    import threading

    svc = _service(consent=True)
    _wire(svc, monkeypatch)
    threads: List[str] = []
    real = svc._extract_component_data

    def _spy(event_type: str, event: Dict[str, Any]) -> Dict[str, Any]:
        threads.append(threading.current_thread().name)
        return real(event_type, event)

    monkeypatch.setattr(svc, "_extract_component_data", _spy)
    await svc._handle_reasoning_event({"events": _thought(0)})
    assert threads and all(name != threading.main_thread().name for name in threads)


def test_build_records_the_consent_it_was_built_with():
    """_build_lens_client stores the consent the client gates on (source check)."""
    import inspect

    source = inspect.getsource(svc_module.AccordMetricsService._build_lens_client)
    assert "self._lens_consent_armed = bool(self._consent_given)" in source
