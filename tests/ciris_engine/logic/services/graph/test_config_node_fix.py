"""Test that verifies the CONFIG node fix prevents malformed nodes."""

import os
import tempfile
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.governance.adaptive_filter import AdaptiveFilterService
from ciris_engine.logic.services.graph.config_service import GraphConfigService
from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
from ciris_engine.schemas.services.nodes import ConfigNode


@pytest.fixture
def time_service():
    """Create a time service for testing."""
    return TimeService()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)


@pytest_asyncio.fixture
async def services(temp_db, time_service):
    """Create all services needed for testing."""
    # Initialize the database
    import sqlite3

    conn = sqlite3.connect(temp_db)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_nodes (
            node_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            node_type TEXT NOT NULL,
            attributes_json TEXT,
            version INTEGER DEFAULT 1,
            updated_by TEXT,
            updated_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (node_id, scope)
        )
    """
    )
    conn.commit()
    conn.close()

    # Create services
    secrets_db = temp_db.replace(".db", "_secrets.db")
    secrets_service = SecretsService(db_path=secrets_db, time_service=time_service)
    await secrets_service.start()

    memory_service = LocalGraphMemoryService(
        db_path=temp_db, secrets_service=secrets_service, time_service=time_service
    )
    memory_service.start()

    config_service = GraphConfigService(graph_memory_service=memory_service, time_service=time_service)
    await config_service.start()

    # Mock LLM service
    class MockLLMService:
        async def call_llm_structured(self, *args, **kwargs):
            return {"response": "mock"}

    llm_service = MockLLMService()

    # Create adaptive filter service with proper config service
    filter_service = AdaptiveFilterService(
        memory_service=memory_service, time_service=time_service, llm_service=llm_service, config_service=config_service
    )
    await filter_service.start()

    yield {
        "memory": memory_service,
        "config": config_service,
        "filter": filter_service,
        "secrets": secrets_service,
        "time": time_service,
    }

    # Cleanup
    await filter_service.stop()
    await config_service.stop()
    memory_service.stop()
    await secrets_service.stop()

    if os.path.exists(secrets_db):
        os.unlink(secrets_db)


@pytest.mark.asyncio
async def test_no_malformed_config_nodes(services):
    """Test that all CONFIG nodes are proper ConfigNode instances."""
    config_service = services["config"]

    # The filter service should have created its config properly
    filter_config = await config_service.get_config("adaptive_filter.config")
    assert filter_config is not None, "Filter config should exist"
    assert isinstance(filter_config, ConfigNode), "Should be a ConfigNode"
    assert filter_config.key == "adaptive_filter.config"
    assert filter_config.value.dict_value is not None

    # Query all config nodes - they should all be valid ConfigNodes
    all_configs = await config_service.list_configs()
    assert len(all_configs) >= 1, "Should have at least the filter config"

    # Verify each config has proper structure
    for key, value in all_configs.items():
        # list_configs now returns a dict mapping keys to actual values
        assert value is not None, f"Config {key} should have a value"
        # The values can be dict, str, int, float, bool, list
        assert isinstance(
            value, (dict, str, int, float, bool, list)
        ), f"Config {key} has unexpected type: {type(value)}"


@pytest.mark.asyncio
async def test_config_node_required_fields(services):
    """Test that ConfigNode enforces required fields."""
    config_service = services["config"]

    # Set a new config
    await config_service.set_config(key="test.config", value={"nested": "data", "count": 42}, updated_by="test_user")

    # Retrieve it
    config = await config_service.get_config("test.config")
    assert config is not None

    # Verify all required fields are present
    assert config.key == "test.config"
    assert config.value.dict_value == {"nested": "data", "count": 42}
    assert config.updated_by == "test_user"
    assert config.updated_at is not None
    assert config.version == 1

    # Verify it can be converted to/from GraphNode
    graph_node = config.to_graph_node()
    assert graph_node.type == NodeType.CONFIG

    # Verify attributes contain required fields
    attrs = graph_node.attributes
    assert isinstance(attrs, dict)
    assert "key" in attrs
    assert "value" in attrs
    assert "node_class" in attrs
    assert attrs["node_class"] == "ConfigNode"

    # Verify we can reconstruct it
    reconstructed = ConfigNode.from_graph_node(graph_node)
    assert reconstructed.key == config.key
    assert reconstructed.value.dict_value == config.value.dict_value


@pytest.mark.asyncio
async def test_config_node_error_handling(services):
    """Test that malformed nodes are properly rejected."""
    memory_service = services["memory"]
    config_service = services["config"]

    # Try to create a malformed CONFIG node directly (should fail on retrieval)
    from ciris_engine.schemas.services.graph_core import GraphNode

    malformed_node = GraphNode(
        id="config_malformed",
        type=NodeType.CONFIG,
        scope=GraphScope.LOCAL,
        attributes={
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "test",
            # Missing 'key' and 'value' fields!
        },
    )

    # Store it directly in memory
    await memory_service.memorize(malformed_node)

    # Try to list configs - the malformed node should be skipped with a warning
    configs = await config_service.list_configs()

    # The malformed node should not appear in the results
    # Since the node doesn't have a valid 'key' attribute, it won't be processed
    all_keys = list(configs.keys())
    assert not any("malformed" in key for key in all_keys), "Malformed node should not appear in results"

    # Try to get it directly - should return None
    result = await config_service.get_config("malformed")
    assert result is None


@pytest.mark.asyncio
async def test_filter_service_uses_proper_config(services):
    """Test that AdaptiveFilterService uses GraphConfigService correctly."""
    config_service = services["config"]
    filter_service = services["filter"]

    # Filter service should have saved its config during initialization
    filter_config_node = await config_service.get_config("adaptive_filter.config")
    assert filter_config_node is not None
    assert filter_config_node.key == "adaptive_filter.config"

    # The value should be a dict containing the AdaptiveFilterConfig data
    filter_config_data = filter_config_node.value.dict_value
    assert filter_config_data is not None
    assert "config_id" in filter_config_data
    assert filter_config_data["config_id"] == "filter_config"
    assert "version" in filter_config_data
    assert "attention_triggers" in filter_config_data
    assert "review_triggers" in filter_config_data
    assert "llm_filters" in filter_config_data

    # Verify the config was saved with proper metadata
    assert filter_config_node.updated_by.startswith("AdaptiveFilterService:")
    assert "Initial configuration" in filter_config_node.updated_by


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
