"""
LensCore fold integration — real ciris_persist.Engine + real LensClient
through AccordMetricsService.start() (CIRISAgent#866).

These tests exercise the actual substrate path the unit tests fake:
capture_event -> partial-trace assembly -> seal on ACTION_RESULT ->
consent gate -> Ed25519 sign (engine.signer()) -> persist -> local tee.

KNOWN UPSTREAM BLOCKER (CIRISLensCore#43): LensClient construction fails
in pip cohabitation ("no process Engine") because the lens-core wheel
statically bundles its own persist crate; the capsule handshake fix is
pending upstream. Every test that constructs a real LensClient is marked
The CIRISLensCore#43 blocker is RESOLVED (lens-core 1.0.1 ships the
engine= capsule handshake); these tests run for real against the wheel.

Engine wiring follows tests/fixtures/persist_engine.py: the global
`persist_engine` fixture calls reset_engine() first (via
_release_persist_engine), constructs Engine with a scratch sqlite DSN +
seed key, and wires it into persistence.models.graph.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest

from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

# Non-ASCII corpus — the bytes that broke the old ensure_ascii=True
# json.dumps signing path; must round-trip through the Rust substrate.
NON_ASCII_CONTENT = "ከመጀመሪያው 你好"

XFAIL_REASON = "CIRISLensCore#43: LensClient needs the Engine capsule handshake in pip cohabitation"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _thought_start(thought_id: str) -> Dict[str, Any]:
    return {
        "event_type": "THOUGHT_START",
        "thought_id": thought_id,
        "task_id": "task-fold-1",
        "timestamp": _now(),
        "round_number": 1,
        "thought_depth": 0,
        "task_description": NON_ASCII_CONTENT,
        "thought_content": f"observe: {NON_ASCII_CONTENT}",
    }


def _conscience_result(thought_id: str) -> Dict[str, Any]:
    return {
        "event_type": "CONSCIENCE_RESULT",
        "thought_id": thought_id,
        "task_id": "task-fold-1",
        "timestamp": _now(),
        "conscience_passed": True,
        "action_was_overridden": False,
        "is_recursive": False,
        "entropy_passed": True,
        "entropy_score": 0.2,
        "coherence_passed": True,
        "coherence_score": 0.9,
    }


def _action_result(thought_id: str) -> Dict[str, Any]:
    return {
        "event_type": "ACTION_RESULT",
        "thought_id": thought_id,
        "task_id": "task-fold-1",
        "timestamp": _now(),
        "execution_success": True,
        "execution_time_ms": 12.5,
        "tokens_input": 100,
        "tokens_output": 50,
        "tokens_total": 150,
        "llm_calls": 1,
        "action_parameters": {"content": NON_ASCII_CONTENT},
    }


@pytest.fixture
def fold_service(persist_engine, tmp_path, monkeypatch):
    """A consented full_traces service with the local tee pointed at
    tmp_path — env set BEFORE construction (the service probes the tee
    dir and reads consent in __init__)."""
    tee_dir = tmp_path / "lens-tee"
    monkeypatch.setenv("CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR", str(tee_dir))
    monkeypatch.setenv("CIRIS_ACCORD_METRICS_CONSENT", "true")
    monkeypatch.setenv("CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP", "2026-01-01T00:00:00+00:00")
    monkeypatch.setenv("CIRIS_ACCORD_METRICS_TRACE_LEVEL", "full_traces")

    service = AccordMetricsService(agent_id="lens-fold-test")
    service._tee_dir_for_assertions = tee_dir  # test-only breadcrumb
    return service


class TestLensFoldIntegration:
    """Real Engine + real LensClient through the service lifecycle."""

    @pytest.mark.asyncio
    async def test_start_constructs_real_lens_client(self, fold_service):
        await fold_service.start()
        try:
            assert fold_service._lens is not None
            # Not the unit-test fake — the actual substrate handle
            assert type(fold_service._lens).__name__ == "LensClient"
        finally:
            await fold_service.stop()

    @pytest.mark.asyncio
    async def test_full_seal_path_with_non_ascii_content(self, fold_service):
        """THOUGHT_START -> CONSCIENCE_RESULT -> ACTION_RESULT seals,
        signs, and persists a trace carrying multilingual content."""
        await fold_service.start()
        try:
            thought_id = "th-fold-seal"
            await fold_service._process_single_event(_thought_start(thought_id))
            assert thought_id in fold_service._open_thoughts

            await fold_service._process_single_event(_conscience_result(thought_id))
            # Still in flight — no ACTION_RESULT yet
            assert fold_service._traces_completed == 0

            await fold_service._process_single_event(_action_result(thought_id))

            # Seal bookkeeping
            assert thought_id not in fold_service._open_thoughts
            assert fold_service._traces_completed == 1
            assert fold_service._traces_signed == 1
            assert fold_service._events_sent >= 3
            assert fold_service._last_send_time is not None

            metrics = fold_service.get_metrics()
            assert metrics["traces_completed"] == 1
            assert metrics["traces_active"] == 0
            assert metrics["events_received"] == 3
            assert metrics["events_queued"] == 0
            assert metrics["substrate"] == "ciris-lens-core"
        finally:
            await fold_service.stop()

    @pytest.mark.asyncio
    async def test_local_copy_tee_writes_sealed_batch(self, fold_service):
        """lens-core tees every sealed batch to the local-copy dir
        (Gap 4) — and the teed JSON must carry the non-ASCII content as
        literal UTF-8, not \\u-escapes."""
        await fold_service.start()
        try:
            thought_id = "th-fold-tee"
            await fold_service._process_single_event(_thought_start(thought_id))
            await fold_service._process_single_event(_action_result(thought_id))
            assert fold_service._traces_completed == 1

            tee_dir = fold_service._tee_dir_for_assertions
            # rglob: the service namespaces the tee per adapter instance
            # (<base>/<instance>/lens-batch-*.json) so parallel instances
            # can't overwrite each other's batch sequence.
            tee_files = sorted(tee_dir.rglob("*.json"))
            assert tee_files, f"no teed batch files in {tee_dir}"
            teed = tee_files[0].read_text(encoding="utf-8")
            assert NON_ASCII_CONTENT in teed
        finally:
            await fold_service.stop()

    @pytest.mark.asyncio
    async def test_consent_absent_blocks_at_seal(self, persist_engine, monkeypatch, tmp_path):
        """Without consent the capture still runs, but the substrate's
        consent gate resolves consent_blocked at the seal — nothing
        persists and nothing is teed."""
        tee_dir = tmp_path / "lens-tee-noconsent"
        monkeypatch.setenv("CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR", str(tee_dir))
        monkeypatch.delenv("CIRIS_ACCORD_METRICS_CONSENT", raising=False)
        monkeypatch.delenv("CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP", raising=False)
        monkeypatch.delenv("CIRIS_COVENANT_METRICS_CONSENT", raising=False)

        service = AccordMetricsService(agent_id="lens-fold-noconsent")
        assert service._consent_given is False

        await service.start()
        try:
            thought_id = "th-fold-blocked"
            await service._process_single_event(_thought_start(thought_id))
            await service._process_single_event(_action_result(thought_id))

            assert service._traces_consent_blocked == 1
            assert service._traces_completed == 0
            assert service._events_sent == 0
            assert thought_id not in service._open_thoughts
            assert list(tee_dir.rglob("*.json")) == []

            metrics = service.get_metrics()
            assert metrics["traces_consent_blocked"] == 1
            assert metrics["traces_completed"] == 0
        finally:
            await service.stop()

    @pytest.mark.asyncio
    async def test_orphan_sweep_runs_against_real_substrate(self, fold_service):
        """A thought without ACTION_RESULT is ephemeral by design — the
        substrate sweep purges it. The purge compares the trace's
        started_at (the opening event's timestamp) STRICTLY against
        now - max_age, so backdate the event two hours and sweep at one
        hour — deterministic, no sleeps."""
        await fold_service.start()
        try:
            event = _thought_start("th-fold-orphan")
            event["timestamp"] = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            await fold_service._process_single_event(event)

            import asyncio

            purged = await asyncio.to_thread(fold_service._lens.orphan_sweep, 3600)
            assert purged >= 1
        finally:
            await fold_service.stop()
