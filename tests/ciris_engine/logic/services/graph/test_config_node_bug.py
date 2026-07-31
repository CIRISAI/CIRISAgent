"""Tests for ConfigNode.from_graph_node conversion, including legacy nodes without `key`.

Historically, ``from_graph_node`` hard-indexed ``attrs["key"]`` and raised
``KeyError: 'key'`` for any CONFIG-typed node whose attributes lacked the
field. Production graphs contain such nodes (written by services before they
carried ``key`` — see the accord_metrics counter below), and every config
scan warned "Failed to convert node ... to ConfigNode: 'key'" every ~10s,
flooding incidents_latest.log (#935).

The contract fix: ``to_graph_node`` always encodes the key in the node id
(``id == f"config:{key}"``), so ``from_graph_node`` now derives the key from
the id when the attribute is absent.
"""

from datetime import datetime, timezone

from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType
from ciris_engine.schemas.services.nodes import ConfigNode, ConfigValue


def test_config_node_from_graph_node_with_graphnodeattributes():
    """A CONFIG node with GraphNodeAttributes (no `key` field) converts via id-derived key.

    Previously this raised KeyError('key') — attrs from GraphNodeAttributes
    never contain the ConfigNode extra fields.
    """
    graph_node = GraphNode(
        id="config_test_key_123",
        type=NodeType.CONFIG,
        scope=GraphScope.LOCAL,
        attributes=GraphNodeAttributes(
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by="test_user",
            tags=["config:test"],
        ),
        version=1,
        updated_by="test_user",
        updated_at=datetime.now(timezone.utc),
    )

    config_node = ConfigNode.from_graph_node(graph_node)
    # No "config:" prefix on the id, so the id itself is the key
    assert config_node.key == "config_test_key_123"
    assert config_node.value.value is None


def test_config_node_from_graph_node_with_dict():
    """Canonical shape (attrs carry `key`) still uses the attribute, not the id."""
    now = datetime.now(timezone.utc)
    graph_node = GraphNode(
        id="config_test_key_123",
        type=NodeType.CONFIG,
        scope=GraphScope.LOCAL,
        attributes={
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "created_by": "test_user",
            "tags": ["config:test"],
            "key": "test.key",
            "value": {"string_value": "test_value"},
            "node_class": "ConfigNode",
        },
        version=1,
        updated_by="test_user",
        updated_at=now,
    )

    config_node = ConfigNode.from_graph_node(graph_node)
    assert config_node.key == "test.key"
    assert config_node.value.value == "test_value"


def test_config_node_derives_key_stripping_config_prefix():
    """Nodes written by to_graph_node() (id == f"config:{key}") derive the bare key."""
    now = datetime.now(timezone.utc)
    graph_node = GraphNode(
        id="config:some.setting",
        type=NodeType.CONFIG,
        scope=GraphScope.LOCAL,
        attributes={
            "created_at": now.isoformat(),
            "created_by": "test_user",
            # `key` missing — simulates a node whose extra fields were dropped
        },
        version=1,
        updated_by="test_user",
        updated_at=now,
    )

    config_node = ConfigNode.from_graph_node(graph_node)
    assert config_node.key == "some.setting"


def test_legacy_accord_metrics_events_total_round_trips():
    """Regression (#935): the exact legacy accord_metrics counter node converts.

    Pre-2.9.0 ciris_adapters/ciris_accord_metrics wrote this CONFIG-typed
    node with only counter attributes — no `key`, no `value`. It survives in
    long-lived production graphs; the config service must be able to
    round-trip it instead of warning every ~10 seconds.
    """
    now = datetime.now(timezone.utc)
    legacy_node = GraphNode(
        id="accord_metrics/events_total",
        type=NodeType.CONFIG,
        scope=GraphScope.LOCAL,
        attributes={
            "events_sent_total": 42,
            "last_updated": now.isoformat(),
        },
        updated_by="accord_metrics_service",
        updated_at=now,
    )

    # Conversion succeeds — key derived from the node id (which is exactly
    # what the fixed 2.9.0+ writer sets as the key attribute).
    config_node = ConfigNode.from_graph_node(legacy_node)
    assert config_node.key == "accord_metrics/events_total"
    assert config_node.value == ConfigValue()

    # Full round-trip: back to GraphNode and through the converter again.
    round_tripped = ConfigNode.from_graph_node(config_node.to_graph_node())
    assert round_tripped.key == "accord_metrics/events_total"


def test_config_node_canonical_round_trip():
    """ConfigNode -> to_graph_node -> from_graph_node preserves key and value."""
    now = datetime.now(timezone.utc)
    original = ConfigNode(
        id="config:round.trip",
        key="round.trip",
        value=ConfigValue(int_value=7),
        version=3,
        updated_by="tester",
        updated_at=now,
        scope=GraphScope.LOCAL,
        attributes={},
    )

    restored = ConfigNode.from_graph_node(original.to_graph_node())
    assert restored.key == "round.trip"
    assert restored.value.value == 7
    assert restored.version == 3
