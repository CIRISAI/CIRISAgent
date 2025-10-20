"""Tests for typed service registries."""

import pytest

from ciris_engine.logic.registries import (
    CommunicationRegistry,
    LLMRegistry,
    MemoryRegistry,
    Priority,
    RuntimeControlRegistry,
    ToolRegistry,
    WiseRegistry,
)


class MockMemoryService:
    """Mock memory service for testing."""

    async def is_healthy(self) -> bool:
        return True

    async def memorize(self, node):
        return {"success": True}

    async def recall(self, query):
        return []

    async def forget(self, node):
        return {"success": True}


class MockLLMService:
    """Mock LLM service for testing."""

    async def is_healthy(self) -> bool:
        return True

    async def call_llm_structured(self, messages, response_model, max_tokens=1024, temperature=0.0):
        return (None, {})


class MockCommunicationService:
    """Mock communication service for testing."""

    async def is_healthy(self) -> bool:
        return True

    async def send_message(self, channel_id: str, content: str) -> bool:
        return True

    async def fetch_messages(self, channel_id: str, limit: int = 50, before=None):
        return []

    def get_home_channel_id(self):
        return "test_channel"


class MockToolService:
    """Mock tool service for testing."""

    async def is_healthy(self) -> bool:
        return True

    async def execute_tool(self, tool_name: str, parameters):
        return {"success": True}

    async def list_tools(self):
        return ["test_tool"]


class MockRuntimeControlService:
    """Mock runtime control service for testing."""

    async def is_healthy(self) -> bool:
        return True

    async def pause_processing(self):
        return {"success": True}


class MockWiseService:
    """Mock wise authority service for testing."""

    async def is_healthy(self) -> bool:
        return True

    async def check_authorization(self, wa_id: str, action: str, resource=None) -> bool:
        return True


@pytest.mark.asyncio
async def test_memory_registry_type_safety():
    """Test that MemoryRegistry provides type-safe registration and lookup."""
    registry = MemoryRegistry()

    # Register a memory service
    service = MockMemoryService()
    provider_name = registry.register("memory", service, priority=Priority.HIGH)

    assert provider_name is not None

    # Get service with proper return type
    retrieved = await registry.get("test_handler")
    assert retrieved is not None
    assert isinstance(retrieved, MockMemoryService)


@pytest.mark.asyncio
async def test_llm_registry_type_safety():
    """Test that LLMRegistry provides type-safe registration and lookup."""
    registry = LLMRegistry()

    # Register an LLM service
    service = MockLLMService()
    provider_name = registry.register("llm", service, priority=Priority.HIGH)

    assert provider_name is not None

    # Get service with proper return type
    retrieved = await registry.get("test_handler")
    assert retrieved is not None
    assert isinstance(retrieved, MockLLMService)


@pytest.mark.asyncio
async def test_communication_registry_type_safety():
    """Test that CommunicationRegistry provides type-safe registration and lookup."""
    registry = CommunicationRegistry()

    # Register a communication service
    service = MockCommunicationService()
    provider_name = registry.register("comm", service, priority=Priority.HIGH)

    assert provider_name is not None

    # Get service with proper return type
    retrieved = await registry.get("test_handler")
    assert retrieved is not None
    assert isinstance(retrieved, MockCommunicationService)


@pytest.mark.asyncio
async def test_tool_registry_type_safety():
    """Test that ToolRegistry provides type-safe registration and lookup."""
    registry = ToolRegistry()

    # Register a tool service
    service = MockToolService()
    provider_name = registry.register("tool", service, priority=Priority.HIGH)

    assert provider_name is not None

    # Get service with proper return type
    retrieved = await registry.get("test_handler")
    assert retrieved is not None
    assert isinstance(retrieved, MockToolService)


@pytest.mark.asyncio
async def test_runtime_control_registry_type_safety():
    """Test that RuntimeControlRegistry provides type-safe registration and lookup."""
    registry = RuntimeControlRegistry()

    # Register a runtime control service
    service = MockRuntimeControlService()
    provider_name = registry.register("control", service, priority=Priority.HIGH)

    assert provider_name is not None

    # Get service with proper return type
    retrieved = await registry.get("test_handler")
    assert retrieved is not None
    assert isinstance(retrieved, MockRuntimeControlService)


@pytest.mark.asyncio
async def test_wise_registry_type_safety():
    """Test that WiseRegistry provides type-safe registration and lookup."""
    registry = WiseRegistry()

    # Register a wise authority service
    service = MockWiseService()
    provider_name = registry.register("wise", service, priority=Priority.HIGH)

    assert provider_name is not None

    # Get service with proper return type
    retrieved = await registry.get("test_handler")
    assert retrieved is not None
    assert isinstance(retrieved, MockWiseService)


@pytest.mark.asyncio
async def test_registry_get_all():
    """Test that get_all returns properly typed lists."""
    registry = MemoryRegistry()

    # Register multiple services
    service1 = MockMemoryService()
    service2 = MockMemoryService()

    registry.register("memory1", service1, priority=Priority.HIGH)
    registry.register("memory2", service2, priority=Priority.NORMAL)

    # Get all services
    services = registry.get_all()
    assert len(services) == 2
    assert all(isinstance(s, MockMemoryService) for s in services)


@pytest.mark.asyncio
async def test_registry_capabilities_filtering():
    """Test that capabilities filtering works with typed registries."""
    registry = MemoryRegistry()

    # Register service with capabilities
    service = MockMemoryService()
    registry.register("memory", service, priority=Priority.HIGH, capabilities=["read", "write"])

    # Should find service with matching capabilities
    retrieved = await registry.get("test_handler", required_capabilities=["read"])
    assert retrieved is not None

    # Should not find service with missing capabilities
    retrieved = await registry.get("test_handler", required_capabilities=["admin"])
    assert retrieved is None
