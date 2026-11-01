"""Following persist's pages, and reading its edges, as persist writes them (2.18.0 scouts).

Two recurring errors on a Postgres-backed scout with real data:
- "get_all_graph_nodes scope-walk failed": the second page was requested with
  `{"cursor": <ListCursor>}`, and persist answered "ListCursor decode: missing
  field `version`". Three other pagers read `page["cursor"]`, a field no persist
  page has, and silently stopped after one page.
- "get_edges_for_node failed": persist omits `weight` when an edge has none, and
  the agent passed None into GraphEdge's float field.
"""

from __future__ import annotations

import json
from typing import Any, List, Optional

import pytest

from ciris_engine.logic.persistence.db.paging import next_page_cursor
from ciris_engine.logic.persistence.models import graph
from ciris_engine.schemas.services.graph_core import GraphScope

LIST_CURSOR = {"version": "v1", "last_ts": "2026-10-30T22:50:00Z", "last_id": "user/alice"}


def test_next_page_cursor_reads_persists_next_cursor() -> None:
    assert json.loads(next_page_cursor({"items": [1], "next_cursor": LIST_CURSOR}) or "") == LIST_CURSOR
    assert next_page_cursor({"items": [1]}) is None, "absent next_cursor = the last page"
    assert next_page_cursor(None) is None


def _node(node_id: str) -> dict:
    return {
        "node_id": node_id,
        "node_type": "user",
        "scope": "local",
        "attributes": {},
        "version": 1,
        "updated_at": "2026-10-30T22:50:00Z",
        "created_at": "2026-10-30T22:50:00Z",
    }


class _TwoPages:
    """Page 1 carries next_cursor; page 2 is accepted only with a real ListCursor."""

    def __init__(self) -> None:
        self.cursors: List[Optional[str]] = []

    def cirisgraph_query_nodes(self, filter_json: str, cursor_json: Optional[str], limit: int) -> str:
        self.cursors.append(cursor_json)
        if cursor_json is None:
            return json.dumps({"items": [_node("user/a")], "next_cursor": LIST_CURSOR})
        decoded = json.loads(cursor_json)
        if "version" not in decoded:
            raise ValueError("ListCursor decode: missing field `version` at line 1 column 126")
        return json.dumps({"items": [_node("user/b")]})


def test_the_scope_walk_follows_persists_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _TwoPages()
    monkeypatch.setattr(graph, "_get_engine", lambda: engine)
    monkeypatch.setattr(graph, "_node_from_persist_json", lambda it: it["node_id"])
    out: Any = graph._query_nodes_paged("local", None, 500)
    assert out == ["user/a", "user/b"], "the walk must reach page 2"
    assert json.loads(engine.cursors[1] or "") == LIST_CURSOR, "page 2 is asked for with persist's own cursor"


def test_an_edge_without_a_weight_reads_with_the_default_weight() -> None:
    edge = graph._edge_from_persist_json(
        {
            "edge_id": "e1",
            "source_node_id": "user/alice",
            "target_node_id": "system/local",
            "scope": "LOCAL",
            "relationship": "OWNS",
            "attributes": {},
            "created_at": "2026-10-30T22:50:00Z",
        }
    )
    assert edge.weight == 1.0 and edge.scope == GraphScope.LOCAL
