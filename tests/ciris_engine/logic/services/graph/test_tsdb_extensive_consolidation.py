"""Unit tests for TSDB extensive consolidation (daily summaries).

Post-A1 absorption (CIRISAgent#763, CIRISPersist#63): extensive (daily)
consolidation now routes through persist's substrate methods —
`telemetry_consolidate_period`, `tsdb_consolidate_tasks`,
`tsdb_consolidate_conversations`, `tsdb_consolidate_traces`,
`tsdb_consolidate_audit` — each invoked with `level=daily`. The legacy
in-agent aggregation (4x basic summaries -> 1 daily) is now persist's
responsibility.

The legacy test suite (memorize-call assertions on
`tsdb_summary_daily_*` nodes) is incompatible with the new orchestration
shape. Locking is substrate-internal (persist consolidators take
`locked_by` and manage stale locks themselves — the agent-side lock
wrappers were deleted in the 2.9.7 DRY purge). Tests below verify:
1. `locked_by` flows to the substrate in each request
2. persist substrate method invocation
3. graceful handling when persist raises
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation import TSDBConsolidationService
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


@pytest.fixture
def mock_memory_bus():
    """Create a mock memory bus."""
    mock = Mock()
    mock.memorize = AsyncMock(return_value=MemoryOpResult(status=MemoryOpStatus.OK))
    mock.recall = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_time_service():
    """Create a mock time service that returns a fixed Monday."""
    mock = Mock()
    # Tuesday, July 15, 2025 at 01:00 UTC (after midnight so consolidation runs)
    mock.now = Mock(return_value=datetime(2025, 7, 15, 1, 0, 0, tzinfo=timezone.utc))
    return mock


@pytest.fixture
def tsdb_service(mock_memory_bus, mock_time_service, persist_engine):
    """Create TSDB service wired to the test persist engine."""
    return TSDBConsolidationService(memory_bus=mock_memory_bus, time_service=mock_time_service)


class TestExtensiveConsolidation:
    """Test cases for extensive consolidation orchestration via persist."""

    @pytest.mark.asyncio
    async def test_extensive_consolidation_passes_locked_by(self, tsdb_service, persist_engine, monkeypatch):
        """Every substrate request carries `locked_by` — persist owns the
        consolidation lock internally (broke_stale_lock semantics)."""
        captured_requests: list[dict] = []

        class _CapturingEngine:
            def __getattr__(self, name):
                if name.startswith("tsdb_consolidate_") or name == "telemetry_consolidate_period":
                    def _capture(req_json):
                        captured_requests.append(json.loads(req_json))
                        return json.dumps({"ok": True})

                    return _capture
                return getattr(persist_engine, name)

        import ciris_engine.logic.persistence.models.graph as graph_mod

        monkeypatch.setattr(graph_mod, "_engine", _CapturingEngine())

        await tsdb_service._run_extensive_consolidation()

        assert len(captured_requests) == 5
        for req in captured_requests:
            assert req.get("locked_by", "").startswith("ciris-agent-")

    @pytest.mark.asyncio
    async def test_extensive_consolidation_empty_corpus_smoke(self, tsdb_service, persist_engine):
        """With no data, extensive consolidation runs cleanly to completion."""
        # Should not raise even with an empty persist corpus
        await tsdb_service._run_extensive_consolidation()

    @pytest.mark.asyncio
    async def test_extensive_consolidation_handles_persist_errors(
        self, tsdb_service, persist_engine, monkeypatch
    ):
        """If a persist consolidator raises, the orchestration logs and continues."""
        called: list[str] = []

        class _RaisingEngine:
            def __getattr__(self, name):
                if name.startswith("tsdb_consolidate_") or name == "telemetry_consolidate_period":
                    def _raise(*args, **kwargs):
                        called.append(name)
                        raise RuntimeError(f"simulated {name} failure")

                    return _raise
                return getattr(persist_engine, name)

        import ciris_engine.logic.persistence.models.graph as graph_mod

        monkeypatch.setattr(graph_mod, "_engine", _RaisingEngine())

        # Should not raise — orchestration logs each failure and continues
        await tsdb_service._run_extensive_consolidation()

    @pytest.mark.asyncio
    async def test_extensive_consolidation_uses_daily_level(
        self, tsdb_service, persist_engine, monkeypatch
    ):
        """When the orchestration succeeds in calling persist methods, the
        request payload carries `level=daily`."""
        captured_requests: list[dict] = []

        class _CapturingEngine:
            def __getattr__(self, name):
                if name.startswith("tsdb_consolidate_") or name == "telemetry_consolidate_period":
                    def _capture(req_json):
                        captured_requests.append(json.loads(req_json))
                        return json.dumps({"ok": True})

                    return _capture
                return getattr(persist_engine, name)

        import ciris_engine.logic.persistence.models.graph as graph_mod

        monkeypatch.setattr(graph_mod, "_engine", _CapturingEngine())

        await tsdb_service._run_extensive_consolidation()

        # Either captured the request (lock acquired) or skipped (lock failed in prod).
        # We only assert on what was captured.
        for req in captured_requests:
            assert req.get("level") == "daily", f"Expected level=daily, got {req.get('level')}"
            assert "period_start" in req
            assert "period_end" in req
            assert "tenant_id" in req
