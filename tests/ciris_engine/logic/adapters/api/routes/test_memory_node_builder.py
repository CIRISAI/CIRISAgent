"""The memory API returns what was stored, and skips graph rows that are not agent memory.

GraphNodeBuilder dropped every attribute except tags/created_by, so content came
back stripped from /v1/memory/query, and it logged an ERROR for each
substrate-owned row ("attestation", "family") a scope listing touched (#1303).
"""

import logging

from ciris_engine.logic.adapters.api.routes.memory_query_helpers import GraphNodeBuilder


def _row(node_type: str, **attributes: object) -> dict:
    return {
        "node_id": "n1",
        "scope": "IDENTITY",
        "node_type": node_type,
        "attributes": {"created_by": "agent", **attributes},
        "version": 1,
        "updated_by": "agent",
        "updated_at": "2026-10-21T12:00:00+00:00",
    }


def test_content_is_returned():
    node = GraphNodeBuilder.build_from_row(_row("concept", content="the stored fact", tags=["a"]))
    assert node is not None
    assert node.attributes.content == "the stored fact"
    assert node.attributes.tags == ["a"]
    assert node.scope.value == "identity"


def test_substrate_owned_rows_are_skipped_without_an_error(caplog):
    with caplog.at_level(logging.DEBUG):
        assert GraphNodeBuilder.build_from_row(_row("attestation")) is None
        assert GraphNodeBuilder.build_from_row(_row("family")) is None
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_a_genuinely_broken_agent_row_still_logs_an_error(caplog):
    row = _row("concept")
    row["scope"] = "NOT_A_SCOPE"
    with caplog.at_level(logging.ERROR):
        assert GraphNodeBuilder.build_from_row(row) is None
    assert any("Failed to build GraphNode" in r.getMessage() for r in caplog.records)


def test_an_amendment_comes_back_with_its_approval():
    """RATCHET run 39795442173: an amendment read back here had no wa_amendment."""
    provenance = {"wa_id": "wa-1", "deferral_id": "defer_c5", "granted_at": "2026-10-22T14:00:00+00:00"}
    node = GraphNodeBuilder.build_from_row(
        _row(
            "identity_amendment",
            content="Take care, from Ally.",
            wa_amendment=provenance,
            proposed_node_id="identity/agent",
        )
    )
    assert node is not None
    assert node.attributes["wa_amendment"] == provenance
    assert node.attributes["proposed_node_id"] == "identity/agent"
    assert node.attributes["content"] == "Take care, from Ally."


def test_other_nodes_keep_the_base_projection():
    node = GraphNodeBuilder.build_from_row(_row("concept", content="fact", wa_amendment={"wa_id": "x"}))
    assert node is not None
    assert not isinstance(node.attributes, dict)
