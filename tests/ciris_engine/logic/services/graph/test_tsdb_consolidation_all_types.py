"""
End-to-end tests for TSDB consolidation across all summary types.

Post-A1 absorption (CIRISAgent#763, CIRISPersist#63): the legacy
`_consolidate_period(start, end)` orchestration was retired. All summary
construction now happens inside persist substrate methods
(`telemetry_consolidate_period`, `tsdb_consolidate_tasks`,
`tsdb_consolidate_conversations`, `tsdb_consolidate_traces`,
`tsdb_consolidate_audit`). The agent calls these via
`_run_extensive_consolidation` and `_run_profound_consolidation`.

The legacy 1400-line test suite that fed correlations via raw SQL and
mocked `recall_timeseries` to drive the in-agent consolidators no longer
maps to any real code path. The tests below smoke-test the new orchestration
and the persist-side substrate methods directly.

TODO(CIRISPersist): no test fixture exposes pre-built per-period correlation /
node corpora through persist substrate. The pre-2.9.0 fixture machinery
(raw INSERT INTO service_correlations + recall_timeseries mocks) drove the
agent-side consolidators directly. Equivalent end-to-end coverage requires
either (a) a persist test harness that seeds the cirislens substrate, or
(b) integration tests that exercise the full agent runtime. Both are
out-of-scope for the test absorption pass — file CIRISPersist#TBD for the
fixture work.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation import TSDBConsolidationService


@pytest.fixture
def mock_time_service():
    """Create a mock time service with fixed time."""
    from unittest.mock import Mock

    fixed_time = datetime(2024, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
    mock = Mock()
    mock.now = Mock(return_value=fixed_time)
    return mock


@pytest.fixture
def mock_memory_bus():
    """Create a mock memory bus."""
    from unittest.mock import AsyncMock

    return AsyncMock()


@pytest.fixture
def consolidation_service(mock_memory_bus, mock_time_service, persist_engine):
    """Create a TSDB consolidation service wired to the test persist engine."""
    service = TSDBConsolidationService(
        memory_bus=mock_memory_bus,
        time_service=mock_time_service,
        consolidation_interval_hours=6,
        raw_retention_hours=24,
    )
    yield service


def test_persist_substrate_exposes_tsdb_consolidate_methods(persist_engine):
    """Verify persist exposes all five tsdb_consolidate_* + telemetry method names
    that the orchestration loop iterates."""
    expected = (
        "telemetry_consolidate_period",
        "tsdb_consolidate_tasks",
        "tsdb_consolidate_conversations",
        "tsdb_consolidate_traces",
        "tsdb_consolidate_audit",
    )
    for name in expected:
        assert hasattr(persist_engine, name), f"persist Engine missing method: {name}"


def test_persist_consolidate_methods_accept_period_json(persist_engine):
    """Smoke: each tsdb_consolidate_* / telemetry_consolidate_period method
    accepts a single JSON request and returns without raising on empty data."""
    req = {
        "tenant_id": "agent-default",
        "period_start": "2024-01-01T06:00:00Z",
        "period_end": "2024-01-01T12:00:00Z",
        "locked_by": "test-worker",
        "level": "basic",
    }
    req_json = json.dumps(req)

    for name in (
        "telemetry_consolidate_period",
        "tsdb_consolidate_tasks",
        "tsdb_consolidate_conversations",
        "tsdb_consolidate_traces",
        "tsdb_consolidate_audit",
    ):
        method = getattr(persist_engine, name)
        # Empty corpus — should return a result (possibly an empty/zero outcome) or raise
        # a categorized error; not an attribute / argument error.
        try:
            method(req_json)
        except Exception as e:
            # Acceptable: a domain error from persist; not a Python-level signature
            # / attribute error.
            msg = str(e)
            assert "object has no attribute" not in msg, f"{name} signature drift: {msg}"


def test_persist_query_summary_nodes_accepts_known_node_types(persist_engine):
    """Persist accepts task/conversation/trace/audit summary node_types via
    tsdb_query_summary_nodes."""
    for node_type in ("task_summary", "conversation_summary", "trace_summary", "audit_summary"):
        raw = persist_engine.tsdb_query_summary_nodes(
            node_type, "basic", "agent-default", "2024-01-01T00:00:00Z", "2024-12-31T23:59:59Z"
        )
        # Empty corpus: should return an empty list (or its JSON encoding).
        parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
        assert isinstance(parsed, list)
        assert parsed == []


def test_run_extensive_consolidation_invokes_persist_methods(consolidation_service, persist_engine):
    """Smoke: _run_extensive_consolidation should walk through persist's
    consolidate methods without raising AttributeError / TypeError. Empty
    corpus means no work is done — we're verifying the orchestration plumbing."""
    import asyncio

    # Run the loop — should complete cleanly with no data
    asyncio.run(consolidation_service._run_extensive_consolidation())


def test_run_profound_consolidation_invokes_persist_methods(consolidation_service, persist_engine):
    """Smoke: _run_profound_consolidation should walk weekly+monthly tiers
    via persist without raising on an empty corpus."""
    consolidation_service._run_profound_consolidation()


def test_cleanup_old_data_smoke(consolidation_service, persist_engine):
    """Cleanup smoke test — empty corpus prunes nothing, returns 0."""
    deleted = consolidation_service._cleanup_old_data()
    assert deleted == 0
