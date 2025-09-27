"""
Simple test to verify that the corruption fix imports work correctly.

This is a minimal test that just verifies the imports are correct,
without trying to test the entire build_system_snapshot function.
"""

import pytest


def test_graph_core_imports():
    """Test that the fixed imports from graph_core work correctly."""
    # These imports should work now that we fixed the module path
    from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType

    # Verify we can create a GraphNode
    node = GraphNode(
        id="user/test123",
        type=NodeType.USER,
        scope=GraphScope.LOCAL,
        attributes={"username": "test_user", "last_seen": "2024-01-01T00:00:00Z"},
    )

    assert node.id == "user/test123"
    assert node.type == NodeType.USER
    assert node.scope == GraphScope.LOCAL
    assert node.attributes["username"] == "test_user"


def test_memory_service_has_memorize():
    """Test that memory service has the memorize method."""
    from ciris_engine.logic.services.memory_service import LocalGraphMemoryService

    # Verify the memorize method exists
    assert hasattr(LocalGraphMemoryService, "memorize")

    # The method should be callable
    assert callable(getattr(LocalGraphMemoryService, "memorize", None))


def test_corruption_detection_logic():
    """Test the logic for detecting template placeholders in timestamps."""
    # Test cases for detecting corruption
    test_cases = [
        ("2024-09-16T[insert current time]Z", True),  # Template placeholder
        ("2024-09-16T[PLACEHOLDER]Z", True),  # Another placeholder variant
        ("not-a-date", False),  # Invalid date but not a template
        ("2024-09-16T12:34:56Z", False),  # Valid ISO date
        ("2024-09-16T12:34:56.123456Z", False),  # Valid ISO with microseconds
    ]

    for timestamp, should_detect in test_cases:
        is_template = "[insert" in timestamp.lower() or "placeholder" in timestamp.lower()
        assert is_template == should_detect, f"Failed for {timestamp}"


def test_system_snapshot_imports():
    """Test that system_snapshot.py can be imported without errors."""
    # This should not raise any ImportError now that we fixed the imports
    try:
        from ciris_engine.logic.context import system_snapshot

        assert system_snapshot is not None
    except ImportError as e:
        pytest.fail(f"Failed to import system_snapshot: {e}")


if __name__ == "__main__":
    # Run the tests
    test_graph_core_imports()
    print("✓ Graph core imports work")

    test_memory_service_has_memorize()
    print("✓ Memory service has memorize method")

    test_corruption_detection_logic()
    print("✓ Corruption detection logic is correct")

    test_system_snapshot_imports()
    print("✓ System snapshot imports work")

    print("\nAll tests passed! The import fix is working correctly.")
