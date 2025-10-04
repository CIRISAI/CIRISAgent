"""Unit tests for Config Service."""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from ciris_engine.logic.services.graph.config_service import GraphConfigService
from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph_core import GraphScope


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
async def memory_service(temp_db, time_service):
    """Create a memory service for testing."""
    # Initialize the database
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

    # Create a secrets service for the memory service
    from ciris_engine.logic.secrets.service import SecretsService

    secrets_db = temp_db.replace(".db", "_secrets.db")
    secrets_service = SecretsService(db_path=secrets_db, time_service=time_service)
    await secrets_service.start()

    service = LocalGraphMemoryService(db_path=temp_db, secrets_service=secrets_service, time_service=time_service)
    await service.start()
    return service


@pytest_asyncio.fixture
async def config_service(memory_service, time_service):
    """Create a config service for testing."""
    service = GraphConfigService(graph_memory_service=memory_service, time_service=time_service)
    await service.start()
    return service


@pytest.mark.asyncio
async def test_config_service_lifecycle(config_service):
    """Test ConfigService start/stop lifecycle."""
    # Start
    await config_service.start()
    # Service should be ready

    # Stop
    await config_service.stop()
    # Should complete without error


@pytest.mark.asyncio
async def test_config_service_set_and_get(config_service):
    """Test setting and getting configuration values."""
    # Set a config value
    await config_service.set_config(key="test.setting", value="test_value", updated_by="test_user")
    # set_config returns None, not True

    # Get the config value
    config_node = await config_service.get_config("test.setting")
    assert config_node is not None
    assert config_node.key == "test.setting"
    assert config_node.value.value == "test_value"  # Use the value property
    assert config_node.updated_by == "test_user"
    assert config_node.version == 1


@pytest.mark.asyncio
async def test_config_service_get_nonexistent(config_service):
    """Test getting non-existent config returns None."""
    # Get non-existent key - should return None
    config_node = await config_service.get_config("nonexistent.key")
    assert config_node is None


@pytest.mark.asyncio
async def test_config_service_update_config(config_service):
    """Test updating existing configuration."""
    # Set initial value
    await config_service.set_config(key="update.test", value="initial", updated_by="test_user")

    # Verify initial value
    initial_config = await config_service.get_config("update.test")
    assert initial_config is not None
    assert initial_config.value.value == "initial"
    assert initial_config.version == 1
    initial_id = initial_config.id

    # Update the value
    await config_service.set_config(key="update.test", value="updated", updated_by="test_user")

    # Verify update
    config_node = await config_service.get_config("update.test")
    assert config_node is not None
    assert config_node.value.value == "updated"
    assert config_node.version == 2  # Should increment version
    assert config_node.previous_version == initial_id  # Should link to previous


@pytest.mark.asyncio
async def test_config_service_list_configs(config_service):
    """Test listing all configurations."""
    # Set multiple configs
    configs = {"app.name": "TestApp", "app.version": "1.0.0", "feature.enabled": True, "feature.limit": 100}

    for key, value in configs.items():
        await config_service.set_config(key=key, value=value, updated_by="test_user")

    # List all configs
    all_configs = await config_service.list_configs()
    assert len(all_configs) >= 4

    # Verify all our configs are present
    for key, expected_value in configs.items():
        assert key in all_configs
        # list_configs() now returns actual values, not ConfigValue instances
        actual_value = all_configs[key]
        assert actual_value == expected_value


@pytest.mark.asyncio
async def test_config_service_list_by_prefix(config_service):
    """Test listing configurations by prefix."""
    # Set configs with different prefixes
    await config_service.set_config("db.host", "localhost", updated_by="test_user")
    await config_service.set_config("db.port", 5432, updated_by="test_user")
    await config_service.set_config("api.endpoint", "https://api.example.com", updated_by="test_user")
    await config_service.set_config("api.timeout", 30, updated_by="test_user")

    # List by prefix
    db_configs = await config_service.list_configs(prefix="db.")
    assert len(db_configs) == 2
    assert all(key.startswith("db.") for key in db_configs.keys())
    assert db_configs["db.host"] == "localhost"
    assert db_configs["db.port"] == 5432

    api_configs = await config_service.list_configs(prefix="api.")
    assert len(api_configs) == 2
    assert all(key.startswith("api.") for key in api_configs.keys())
    assert api_configs["api.endpoint"] == "https://api.example.com"
    assert api_configs["api.timeout"] == 30


@pytest.mark.asyncio
async def test_config_service_delete_config(config_service):
    """Test deleting configuration."""
    # GraphConfigService doesn't have a delete_config method
    # Instead, test that configs can be overwritten
    await config_service.set_config("to.update", "value", updated_by="test_user")

    # Overwrite with new value
    await config_service.set_config("to.update", "new_value", updated_by="test_user")

    # Verify it's updated
    config_node = await config_service.get_config("to.update")
    assert config_node is not None
    assert config_node.value.value == "new_value"


@pytest.mark.asyncio
async def test_config_service_complex_values(config_service):
    """Test storing complex configuration values."""
    # Store different types
    await config_service.set_config("string.value", "hello", updated_by="test_user")
    await config_service.set_config("int.value", 42, updated_by="test_user")
    await config_service.set_config("float.value", 3.14, updated_by="test_user")
    await config_service.set_config("bool.value", True, updated_by="test_user")
    await config_service.set_config("list.value", ["a", "b", "c"], updated_by="test_user")
    await config_service.set_config("dict.value", {"key": "value", "nested": {"deep": True}}, updated_by="test_user")

    # Retrieve and verify types
    assert (await config_service.get_config("string.value")).value.value == "hello"
    assert (await config_service.get_config("int.value")).value.value == 42
    assert (await config_service.get_config("float.value")).value.value == 3.14
    assert (await config_service.get_config("bool.value")).value.value is True
    assert (await config_service.get_config("list.value")).value.value == ["a", "b", "c"]
    dict_config = await config_service.get_config("dict.value")
    assert dict_config.value.value == {"key": "value", "nested": {"deep": True}}


def test_config_service_capabilities(config_service):
    """Test ConfigService.get_capabilities() returns correct info."""
    caps = config_service.get_capabilities()
    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "GraphConfigService"
    assert caps.version == "1.0.0"
    assert "get_config" in caps.actions
    assert "set_config" in caps.actions
    assert "list_configs" in caps.actions
    assert "delete_config" in caps.actions  # Listed in _get_actions even though not implemented
    assert "register_config_listener" in caps.actions
    assert "unregister_config_listener" in caps.actions
    # BaseGraphService adds MemoryBus dependency, but ConfigService also uses TimeService
    assert "MemoryBus" in caps.dependencies  # From BaseGraphService
    assert "TimeService" in caps.dependencies


@pytest.mark.asyncio
async def test_config_service_status(config_service):
    """Test ConfigService.get_status() returns correct status."""
    # Service is already started in fixture
    status = config_service.get_status()
    assert isinstance(status, ServiceStatus)
    assert status.service_name == "GraphConfigService"
    assert status.service_type == "config"  # ServiceType.CONFIG from get_service_type()
    assert status.is_healthy is True

    # Add some configs and check status
    for i in range(5):
        await config_service.set_config(f"test.config{i}", f"value{i}", updated_by="test_user")


@pytest.mark.asyncio
async def test_config_service_versioning(config_service, time_service):
    """Test configuration versioning."""
    key = "versioned.config"

    # Set initial version
    await config_service.set_config(key, "v1", updated_by="test_user")

    # Get config node to check version
    v1_config = await config_service.get_config(key)
    assert v1_config is not None
    assert v1_config.version == 1
    assert v1_config.previous_version is None
    v1_id = v1_config.id

    # Update to create new version
    await config_service.set_config(key, "v2", updated_by="test_user")

    # Get updated config
    v2_config = await config_service.get_config(key)
    assert v2_config is not None
    assert v2_config.version == 2
    assert v2_config.previous_version == v1_id


@pytest.mark.asyncio
async def test_config_service_metadata_tracking(config_service, time_service):
    """Test configuration metadata is properly tracked."""
    # Set a config - GraphConfigService only takes key, value, updated_by
    await config_service.set_config(key="metadata.test", value="test_value", updated_by="unit_test")

    # Get the config node
    config = await config_service.get_config("metadata.test")
    assert config is not None
    assert config.key == "metadata.test"
    assert config.value.value == "test_value"
    assert config.updated_by == "unit_test"
    assert config.updated_at is not None


@pytest.mark.asyncio
async def test_config_service_batch_operations(config_service):
    """Test batch configuration operations."""
    # Set multiple configs in a batch-like manner
    batch_configs = {f"batch.item{i}": f"value{i}" for i in range(10)}

    # Set all configs
    for key, value in batch_configs.items():
        await config_service.set_config(key, value, updated_by="test_user")

    # Get all batch configs - returns dict
    batch_results = await config_service.list_configs(prefix="batch.")
    assert len(batch_results) == 10

    # Verify all values
    for key, expected_value in batch_configs.items():
        assert key in batch_results
        # list_configs() now returns actual values, not ConfigValue instances
        assert batch_results[key] == expected_value


@pytest.mark.asyncio
async def test_config_service_sensitive_config(config_service):
    """Test handling of sensitive configuration values."""
    # Set a sensitive config (e.g., password, API key)
    # GraphConfigService doesn't have special params for sensitive data
    await config_service.set_config(key="secrets.api_key", value="sk-1234567890abcdef", updated_by="test_user")

    # Retrieve it
    config_node = await config_service.get_config("secrets.api_key")
    assert config_node is not None
    assert config_node.value.value == "sk-1234567890abcdef"

    # List configs returns dict of key->actual values
    configs = await config_service.list_configs(prefix="secrets.")
    assert "secrets.api_key" in configs
    assert configs["secrets.api_key"] == "sk-1234567890abcdef"
    # SecretsService in memory layer handles encryption, not config service


@pytest.mark.asyncio
async def test_config_node_typed_graph_node_compliance(config_service):
    """Test ConfigNode properly implements TypedGraphNode pattern."""
    # Set a config value
    await config_service.set_config(key="typed.test", value={"nested": "dict", "count": 42}, updated_by="test_user")

    # Get the config node
    config_node = await config_service.get_config("typed.test")
    assert config_node is not None

    # ConfigNode uses updated_at/updated_by (not created_at/created_by)
    assert hasattr(config_node, "updated_at")
    assert hasattr(config_node, "updated_by")

    # These should be populated
    assert config_node.updated_at is not None
    assert config_node.updated_by == "test_user"

    # created_at/created_by are stored in attributes when converted to GraphNode
    assert isinstance(config_node.attributes, dict)
    assert "created_at" in config_node.attributes
    assert "created_by" in config_node.attributes
    assert config_node.attributes["created_by"] == "test_user"

    # Verify it has proper type
    assert config_node.type.value == "config"  # NodeType.CONFIG

    # Verify scope is set
    assert config_node.scope == GraphScope.LOCAL

    # Verify conversion methods exist
    assert hasattr(config_node, "to_graph_node")
    assert hasattr(config_node, "from_graph_node")


@pytest.mark.asyncio
async def test_config_service_no_duplicate_updates(config_service):
    """Test that setting same value doesn't create new version."""
    # Set initial value
    await config_service.set_config("duplicate.test", "same_value", updated_by="test_user")

    # Get initial config
    v1_config = await config_service.get_config("duplicate.test")
    assert v1_config.version == 1
    v1_id = v1_config.id

    # Set same value again
    await config_service.set_config("duplicate.test", "same_value", updated_by="test_user")

    # Should still be version 1 with same ID
    current_config = await config_service.get_config("duplicate.test")
    assert current_config.version == 1
    assert current_config.id == v1_id  # No new node created


@pytest.mark.asyncio
async def test_config_service_path_values(config_service):
    """Test handling of Path objects as config values."""
    # Set Path value
    test_path = Path("/home/user/test.txt")
    await config_service.set_config("paths.test", test_path, updated_by="test_user")

    # Get it back - should be converted to string
    config_node = await config_service.get_config("paths.test")
    assert config_node is not None
    assert config_node.value.value == "/home/user/test.txt"
    assert config_node.value.string_value == "/home/user/test.txt"

    # List should also return string value
    configs = await config_service.list_configs(prefix="paths.")
    assert "paths.test" in configs
    assert configs["paths.test"] == "/home/user/test.txt"
