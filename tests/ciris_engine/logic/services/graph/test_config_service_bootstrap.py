"""Unit tests for Config Service bootstrap and end-to-end usage.

This test specifically reproduces the bootstrap bug where ConfigNode
fails to convert from GraphNode due to missing 'key' field.
"""

import json
import os
import sqlite3
import tempfile

import pytest
import pytest_asyncio

from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.graph.config_service import GraphConfigService
from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.nodes import ConfigNode, ConfigValue


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
async def memory_service_factory(temp_db, time_service):
    """Factory to create memory services with same database."""
    created_services = []

    async def _create_service():
        # Initialize the database if needed
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

        # Create a secrets service
        secrets_db = temp_db.replace(".db", "_secrets.db")
        secrets_service = SecretsService(db_path=secrets_db, time_service=time_service)
        await secrets_service.start()

        # Create memory service
        service = LocalGraphMemoryService(db_path=temp_db, secrets_service=secrets_service, time_service=time_service)
        await service.start()
        created_services.append((service, secrets_service))
        return service

    yield _create_service

    # Cleanup
    for memory_service, secrets_service in created_services:
        await memory_service.stop()
        await secrets_service.stop()


@pytest.mark.asyncio
async def test_config_bootstrap_bug_reproduction(memory_service_factory, time_service, temp_db):
    """Test that reproduces the config bootstrap bug.

    The bug occurs when:
    1. Config is stored via set_config during bootstrap
    2. Service is restarted (simulated by creating new service instance)
    3. Config retrieval fails with 'key' missing error
    """
    # Phase 1: Bootstrap - simulate what happens in ServiceInitializer._migrate_config_to_graph()
    memory_service1 = await memory_service_factory()
    config_service1 = GraphConfigService(graph_memory_service=memory_service1, time_service=time_service)
    await config_service1.start()

    # Simulate essential config migration (this is what fails)
    essential_config = EssentialConfig()
    config_dict = essential_config.model_dump()

    # This mimics the bootstrap process
    for section_name, section_data in config_dict.items():
        if isinstance(section_data, dict):
            for key, value in section_data.items():
                full_key = f"{section_name}.{key}"
                # This is exactly what ServiceInitializer does
                await config_service1.set_config(key=full_key, value=value, updated_by="system_bootstrap")
        else:
            await config_service1.set_config(key=section_name, value=section_data, updated_by="system_bootstrap")

    # Verify it works in same session
    test_config = await config_service1.get_config("limits.max_active_tasks")
    assert test_config is not None
    assert test_config.value.value == 10

    # Stop first service
    await config_service1.stop()

    # Phase 2: Restart - create new service instances with same database
    memory_service2 = await memory_service_factory()
    config_service2 = GraphConfigService(graph_memory_service=memory_service2, time_service=time_service)
    await config_service2.start()

    # This is where the bug manifests - let's check what's actually in the database
    conn = sqlite3.connect(temp_db)
    cursor = conn.execute("SELECT node_id, attributes_json FROM graph_nodes WHERE node_type = 'config'")
    rows = cursor.fetchall()
    conn.close()

    print(f"\nFound {len(rows)} config nodes in database")

    # Let's see what's actually stored
    for node_id, attrs_json in rows:
        attrs = json.loads(attrs_json) if attrs_json else {}
        print(f"\nNode ID: {node_id}")
        print(f"Has 'key' field: {'key' in attrs}")
        if "key" in attrs:
            print(f"Key value: {attrs['key']}")
        else:
            print(f"Attributes keys: {list(attrs.keys())}")

    # Now try to retrieve - this is where it fails with the bug
    # The warning "Failed to convert node config/filter_config to ConfigNode: 'key'" happens here
    try:
        test_config2 = await config_service2.get_config("limits.max_active_tasks")
        # With the bug, this might return None or raise an error
        assert test_config2 is not None, "Config retrieval failed after restart"
        assert test_config2.value.value == 10
        print("\nSUCCESS: Config retrieved after restart")
    except Exception as e:
        print(f"\nERROR: Failed to retrieve config after restart: {e}")
        # Let's manually check what's wrong
        nodes = await memory_service2.search("type:config")
        print(f"Found {len(nodes)} config nodes via search")
        for node in nodes:
            print(f"\nNode ID: {node.id}")
            print(f"Node type: {node.type}")
            attrs = node.attributes if isinstance(node.attributes, dict) else node.attributes.model_dump()
            print(f"Attributes keys: {list(attrs.keys())}")
            if "key" in attrs:
                print(f"Key value: {attrs['key']}")
        raise


@pytest.mark.asyncio
async def test_config_node_serialization_fix(time_service):
    """Test that ConfigNode serialization works correctly after fix."""
    # Create a ConfigNode - ConfigNode extends TypedGraphNode which extends GraphNode
    # So it needs the 'attributes' field even though it's not used directly
    config_node = ConfigNode(
        id="config_test_123",
        type=NodeType.CONFIG,
        scope=GraphScope.LOCAL,
        attributes={},  # Required field from GraphNode base class
        key="test.key",
        value=ConfigValue(string_value="test_value"),
        version=1,
        updated_by="test_user",
        updated_at=time_service.now(),
    )

    # Convert to GraphNode
    graph_node = config_node.to_graph_node()

    # Verify GraphNode has proper structure
    assert graph_node.id == "config:test.key"  # ConfigNode uses "config:{key}" format
    assert graph_node.type == NodeType.CONFIG

    # Check attributes - this is where the bug is
    attrs = graph_node.attributes if isinstance(graph_node.attributes, dict) else graph_node.attributes.model_dump()
    assert "key" in attrs, "Missing 'key' in attributes after to_graph_node()"
    assert attrs["key"] == "test.key"
    assert "value" in attrs
    assert "node_class" in attrs

    # Now test deserialization
    reconstructed = ConfigNode.from_graph_node(graph_node)
    assert reconstructed.key == "test.key"
    assert reconstructed.value.value == "test_value"
    assert reconstructed.version == 1
    assert reconstructed.updated_by == "test_user"


@pytest.mark.asyncio
async def test_direct_graph_node_creation(time_service):
    """Test creating GraphNode directly as memory service would store it."""
    # This simulates what actually gets stored in the database
    now = time_service.now()

    # Create attributes dict as it would be stored
    attributes = {
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "created_by": "system_bootstrap",
        "tags": ["config:limits"],
        "key": "limits.max_active_tasks",
        "value": {"int_value": 10},
        "previous_version": None,
        "node_class": "ConfigNode",
    }

    # Create GraphNode as stored in DB
    graph_node = GraphNode(
        id="config_limits_max_active_tasks_12345678",
        type=NodeType.CONFIG,
        scope=GraphScope.LOCAL,
        attributes=attributes,
        version=1,
        updated_by="system_bootstrap",
        updated_at=now,
    )

    # Try to convert back to ConfigNode
    config_node = ConfigNode.from_graph_node(graph_node)
    assert config_node.key == "limits.max_active_tasks"
    assert config_node.value.value == 10
    assert config_node.version == 1


@pytest.mark.asyncio
async def test_config_service_with_restart(memory_service_factory, time_service):
    """End-to-end test with service restart to ensure fix works."""
    # Create and use first service
    memory1 = await memory_service_factory()
    config1 = GraphConfigService(graph_memory_service=memory1, time_service=time_service)
    await config1.start()

    # Set various config types
    await config1.set_config("app.name", "TestApp", updated_by="test")
    await config1.set_config("app.port", 8080, updated_by="test")
    await config1.set_config("app.debug", True, updated_by="test")
    await config1.set_config("app.features", ["auth", "api"], updated_by="test")
    await config1.set_config("app.metadata", {"version": "1.0", "env": "test"}, updated_by="test")

    await config1.stop()

    # Create new service instance
    memory2 = await memory_service_factory()
    config2 = GraphConfigService(graph_memory_service=memory2, time_service=time_service)
    await config2.start()

    # Verify all configs are retrievable
    assert (await config2.get_config("app.name")).value.value == "TestApp"
    assert (await config2.get_config("app.port")).value.value == 8080
    assert (await config2.get_config("app.debug")).value.value is True
    assert (await config2.get_config("app.features")).value.value == ["auth", "api"]
    assert (await config2.get_config("app.metadata")).value.value == {"version": "1.0", "env": "test"}

    # List all configs
    all_configs = await config2.list_configs()
    assert len(all_configs) == 5

    await config2.stop()


if __name__ == "__main__":
    # Run the test that reproduces the bug
    import asyncio

    async def main():
        time_service = TimeService()
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            temp_db = f.name

        try:
            # Create factory closure
            services = []

            async def factory():
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

                secrets_db = temp_db.replace(".db", "_secrets.db")
                secrets_service = SecretsService(db_path=secrets_db, time_service=time_service)
                await secrets_service.start()

                memory_service = LocalGraphMemoryService(
                    db_path=temp_db, secrets_service=secrets_service, time_service=time_service
                )
                await memory_service.start()
                services.append((memory_service, secrets_service))
                return memory_service

            print("Running config bootstrap bug reproduction test...")
            await test_config_bootstrap_bug_reproduction(factory, time_service, temp_db)

            # Cleanup
            for memory_service, secrets_service in services:
                await memory_service.stop()
                await secrets_service.stop()

        finally:
            os.unlink(temp_db)
            secrets_db = temp_db.replace(".db", "_secrets.db")
            if os.path.exists(secrets_db):
                os.unlink(secrets_db)

    asyncio.run(main())
