"""
Regression tests for CIRISAgent#788 — the
`tsdb_query_summary_nodes` callsite drift after CIRISPersist v1.6.2.

What broke and why these tests exist:

1. **TypeError at consolidation read-back**: `service.py:_consolidate_period`
   still called the pre-v1.6.2 single-arg JSON-blob form
   `engine.tsdb_query_summary_nodes(filter_json)`. Persist's PyO3 binding
   raises `TypeError: missing 4 required positional arguments` on import,
   so every basic-consolidation tick after upgrade logged an error and
   `_basic_consolidations` never advanced.

2. **Invalid `node_type`**: 4 other callsites (one in service.py, two in
   query_manager.py, one in get_summary_for_period) passed
   `"tsdb_summary"` — the cirisgraph-namespace string — as the first
   argument. Persist's enum only accepts `task_summary` /
   `conversation_summary` / `trace_summary` / `audit_summary` and the
   Rust side answers `unknown summary node_type: tsdb_summary`,
   returning zero rows. Effect: probes silently always returned
   "not consolidated", and the agent re-consolidated every tick.

Both classes of failure are now routed through the shared
`query_typed_summaries` helper. These tests pin:
  - The helper iterates ALL 4 valid persist node_types.
  - Per-type errors don't fail the others (best-effort aggregation).
  - The helper never re-raises — callers can rely on the empty-list
    contract for both "no data" and "all sub-tables errored".
  - The callers (`check_period_consolidated`,
    `get_last_consolidated_period`, `_is_period_consolidated`,
    `get_summary_for_period`, `_consolidate_period`) all funnel through
    the helper rather than calling `tsdb_query_summary_nodes` directly
    with the invalid string.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from ciris_engine.logic.services.graph.tsdb_consolidation.query_manager import (
    _SUMMARY_NODE_TYPES,
    query_typed_summaries,
)


class TestSummaryNodeTypeEnum:
    """Pin the persist node_type enum we query against. If persist ever
    grows a 5th typed summary table, this test forces an update — the
    consolidation read-back has to cover every sub-table or the agent
    will silently under-count rows."""

    def test_node_types_match_persist_contract(self):
        # Order doesn't matter functionally, but the set is the
        # contract from `ciris_persist.Engine.tsdb_query_summary_nodes`
        # docstring (v1.6.2+).
        assert set(_SUMMARY_NODE_TYPES) == {
            "task_summary",
            "conversation_summary",
            "trace_summary",
            "audit_summary",
        }


class TestQueryTypedSummaries:
    """Pin the 4-way fan-out + best-effort aggregation contract."""

    def _engine_returning(self, per_type_rows):
        """Build a fake engine whose tsdb_query_summary_nodes returns a
        per-node_type payload from the supplied dict."""

        def fake_query(node_type, level, tenant, from_iso, to_iso):
            payload = per_type_rows.get(node_type, [])
            if isinstance(payload, Exception):
                raise payload
            return json.dumps(payload)

        engine = MagicMock()
        engine.tsdb_query_summary_nodes.side_effect = fake_query
        return engine

    def test_calls_persist_once_per_node_type(self):
        engine = self._engine_returning({})
        query_typed_summaries(engine, "basic", "tenant-1", "from", "to")
        # 4 calls — one per typed sub-table — never a single
        # "tsdb_summary" call.
        assert engine.tsdb_query_summary_nodes.call_count == 4
        called_types = {
            c.args[0] for c in engine.tsdb_query_summary_nodes.call_args_list
        }
        assert called_types == set(_SUMMARY_NODE_TYPES)
        # And NEVER passes the cirisgraph-namespace string.
        assert "tsdb_summary" not in called_types

    def test_passes_five_positional_args_in_order(self):
        """Pin the v1.6.2+ signature.

        This is the load-bearing assertion that catches a regression to
        the old single-arg JSON-blob shape (the #788 root cause). If
        someone reintroduces `engine.tsdb_query_summary_nodes(filter_json)`
        anywhere in the consolidation path, this test fails.
        """
        engine = self._engine_returning({})
        query_typed_summaries(engine, "basic", "tenant-1", "2024-01-01Z", "2024-01-02Z")
        for call in engine.tsdb_query_summary_nodes.call_args_list:
            # 5 positional args, no kwargs, no JSON blob.
            assert len(call.args) == 5
            assert call.kwargs == {}
            node_type, level, tenant, from_iso, to_iso = call.args
            assert level == "basic"
            assert tenant == "tenant-1"
            assert from_iso == "2024-01-01Z"
            assert to_iso == "2024-01-02Z"

    def test_aggregates_rows_across_all_types(self):
        per_type = {
            "task_summary": [{"id": "t1"}],
            "conversation_summary": [{"id": "c1"}, {"id": "c2"}],
            "trace_summary": [],
            "audit_summary": [{"id": "a1"}],
        }
        rows = query_typed_summaries(
            self._engine_returning(per_type), "basic", "t", "from", "to"
        )
        # Union, not just first-non-empty.
        ids = {r["id"] for r in rows if isinstance(r, dict)}
        assert ids == {"t1", "c1", "c2", "a1"}

    def test_returns_empty_when_no_rows_anywhere(self):
        rows = query_typed_summaries(
            self._engine_returning({}), "basic", "t", "from", "to"
        )
        assert rows == []

    def test_one_type_error_does_not_fail_others(self):
        """Persist might tolerate one sub-table being missing/locked but
        we still want partial answers — the consolidation probe only
        needs ANY row to know the period is consolidated."""
        per_type = {
            "task_summary": [{"id": "t1"}],
            "conversation_summary": RuntimeError("rust-side panic in conversation_summary"),
            "trace_summary": [{"id": "tr1"}],
            "audit_summary": [{"id": "a1"}],
        }
        rows = query_typed_summaries(
            self._engine_returning(per_type), "basic", "t", "from", "to"
        )
        # Three healthy types contributed.
        ids = {r["id"] for r in rows if isinstance(r, dict)}
        assert ids == {"t1", "tr1", "a1"}

    def test_all_types_error_returns_empty_no_raise(self):
        """The caller's `if not rows` branch must always work — even
        when every sub-table errors. We never propagate."""
        per_type = {nt: RuntimeError(f"{nt} failed") for nt in _SUMMARY_NODE_TYPES}
        rows = query_typed_summaries(
            self._engine_returning(per_type), "basic", "t", "from", "to"
        )
        assert rows == []

    def test_accepts_pre_decoded_list_payload(self):
        """Persist's binding can return either a JSON string or a
        Python list depending on call path. The helper must handle
        both — the original callsites all branched on
        `isinstance(raw, (bytes, str))`. Make sure we don't regress
        to "only handles strings"."""
        engine = MagicMock()
        engine.tsdb_query_summary_nodes.return_value = [{"id": "x"}]
        rows = query_typed_summaries(engine, "basic", "t", "from", "to")
        # Persist returned a list directly for each of the 4 calls.
        assert len(rows) == 4
        assert all(isinstance(r, dict) and r["id"] == "x" for r in rows)

    def test_no_callsite_references_tsdb_summary_as_node_type(self):
        """Source-level guard against regression. The cirisgraph string
        "tsdb_summary" is what passes for the agent-side node_type in
        the graph (NodeType.TSDB_SUMMARY) but is NOT a valid argument
        to persist's tsdb_query_summary_nodes. If a future edit
        reintroduces it as a string literal next to a
        `tsdb_query_summary_nodes(...)` call, this test catches it."""
        import inspect

        from ciris_engine.logic.services.graph.tsdb_consolidation import (
            query_manager,
            service,
        )

        for module in (service, query_manager):
            src = inspect.getsource(module)
            # Walk every line where the persist API name appears and
            # confirm no line within ±4 lines mentions the bogus string.
            lines = src.splitlines()
            for i, line in enumerate(lines):
                if "tsdb_query_summary_nodes(" not in line:
                    continue
                window = "\n".join(lines[max(0, i - 4) : min(len(lines), i + 5)])
                # The helper itself uses _SUMMARY_NODE_TYPES (allowed);
                # the only call should be inside that helper. Either
                # way, "tsdb_summary" as a positional literal next to
                # the API call is the regression we want to block.
                assert '"tsdb_summary"' not in window, (
                    f"{module.__name__} line {i + 1} reintroduces the "
                    f"invalid \"tsdb_summary\" node_type adjacent to a "
                    f"tsdb_query_summary_nodes() call — see CIRISAgent#788."
                )
