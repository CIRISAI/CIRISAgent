"""
Runtime helper test fixtures.

Provides robust, reusable fixtures for testing ciris_runtime_helpers.py functions.
"""

import asyncio
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from ciris_engine.logic.runtime.ciris_runtime_helpers import _SERVICE_SHUTDOWN_PRIORITIES
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus

# =============================================================================
# SERVICE FIXTURES
# =============================================================================


@pytest.fixture
def mock_scheduled_service():
    """Mock service with _task attribute."""
    service = Mock()
    service.__class__.__name__ = "MockScheduledService"
    # Use a simple mock task instead of real asyncio task
    service._task = Mock()
    service._task.cancelled.return_value = False
    service._task.cancel = Mock()
    return service


@pytest.fixture
def mock_scheduler_service():
    """Mock service with _scheduler attribute."""
    service = Mock()
    service.__class__.__name__ = "MockSchedulerService"
    service._scheduler = Mock()
    service.stop_scheduler = AsyncMock()
    return service


@pytest.fixture
def mock_normal_service():
    """Mock service with no scheduled attributes."""
    service = Mock(spec=[])  # Empty spec - no default attributes
    service.__class__.__name__ = "MockNormalService"
    service.stop = AsyncMock()
    return service


@pytest.fixture
def mock_services_collection(mock_scheduled_service, mock_scheduler_service, mock_normal_service):
    """Collection of different service types."""
    return [mock_scheduled_service, mock_scheduler_service, mock_normal_service]


# =============================================================================
# PRIORITY SERVICE FIXTURES
# =============================================================================


@pytest.fixture
def priority_services():
    """Services with different shutdown priorities."""
    services = {}

    # Create services based on actual _SERVICE_SHUTDOWN_PRIORITIES keys
    priority_mapping = {
        "TSDBService": 0,
        "TaskService": 1,
        "MemoryService": 9,
        "TimeService": 11,
        "ShutdownService": 12,
        "UnknownService": 5,  # Default
    }

    for service_name, expected_priority in priority_mapping.items():
        service = Mock()
        service.__class__.__name__ = service_name
        service.stop = AsyncMock()
        services[service_name] = {"service": service, "priority": expected_priority}

    return services


# =============================================================================
# RUNTIME FIXTURES
# =============================================================================


@pytest.fixture
def mock_runtime():
    """Mock runtime with common attributes."""
    runtime = Mock()
    runtime._shutdown_complete = False

    # Mock service registry
    service_registry = Mock()
    runtime.service_registry = service_registry

    # Mock common runtime attributes
    runtime.agent_identity = Mock()
    runtime._preserve_shutdown_continuity = AsyncMock()
    runtime.adapters = []
    runtime.bus_manager = None
    runtime.maintenance_service = None
    runtime.memory_service = None
    runtime.secrets_service = None

    # Mock service initializer
    service_initializer = Mock()
    runtime.service_initializer = service_initializer

    # Mock shutdown event handling
    runtime._ensure_shutdown_event = Mock()
    runtime._shutdown_event = Mock()

    return runtime


@pytest.fixture
def mock_runtime_with_services(mock_runtime, mock_services_collection):
    """Mock runtime with a collection of services."""
    mock_runtime.service_registry.get_all_services.return_value = mock_services_collection
    return mock_runtime


@pytest.fixture
def mock_runtime_with_identity(mock_runtime):
    """Mock runtime with agent identity for continuity awareness."""
    mock_runtime.agent_identity = Mock()
    mock_runtime._preserve_shutdown_continuity = AsyncMock()
    return mock_runtime


# =============================================================================
# AGENT PROCESSOR FIXTURES
# =============================================================================


@pytest.fixture
def mock_agent_processor():
    """Mock agent processor with state manager based on real AgentState schema."""
    # Use spec_set to prevent auto-creation of AsyncMock attributes
    processor = Mock(spec_set=['state_manager', '_processing_task', '_stop_event', 'shutdown_processor'])

    # Mock state manager with schema-based behavior matching real StateManager:
    # - get_state() is synchronous (returns AgentState directly)
    # - can_transition_to() is async (returns bool)
    # - transition_to() is async (returns bool)
    state_manager = Mock(spec_set=['get_state', 'can_transition_to', 'transition_to'])
    state_manager.get_state.return_value = AgentState.WORK
    state_manager.can_transition_to = AsyncMock(return_value=True)
    state_manager.transition_to = AsyncMock(return_value=True)
    processor.state_manager = state_manager

    # Mock processing task - None initially (no active processing)
    processor._processing_task = None
    processor._stop_event = Mock(spec_set=['set'])
    processor._stop_event.set = Mock()

    # Mock shutdown processor with schema-compliant behavior
    # Use spec_set to prevent auto-creation of AsyncMock attributes
    shutdown_processor = Mock(spec_set=['process', 'shutdown_complete', 'shutdown_result'])
    shutdown_processor.process = AsyncMock()
    shutdown_processor.shutdown_complete = False
    shutdown_processor.shutdown_result = None
    processor.shutdown_processor = shutdown_processor

    return processor


@pytest.fixture
def mock_runtime_with_agent_processor(mock_runtime, mock_agent_processor):
    """Mock runtime with agent processor."""
    mock_runtime.agent_processor = mock_agent_processor
    return mock_runtime


# =============================================================================
# ADAPTER FIXTURES
# =============================================================================


@pytest.fixture
def mock_adapters():
    """Mock adapters for testing adapter shutdown - schema-based behavior."""
    adapters = []

    for i in range(2):
        adapter = Mock()
        adapter.__class__.__name__ = f"MockAdapter{i+1}"
        adapter.stop = AsyncMock()

        # Mock adapter config based on schema
        adapter.config = AdapterConfig(
            adapter_type=f"mock_type_{i+1}", enabled=True, settings={"timeout": 30, "max_retries": 3}
        )

        adapters.append(adapter)

    return adapters


@pytest.fixture
def mock_bus_manager():
    """Mock bus manager for testing bus shutdown."""
    bus_manager = AsyncMock()
    bus_manager.stop = AsyncMock()
    return bus_manager


@pytest.fixture
def mock_runtime_with_adapters(mock_runtime, mock_adapters, mock_bus_manager):
    """Mock runtime with adapters and bus manager."""
    mock_runtime.adapters = mock_adapters
    mock_runtime.bus_manager = mock_bus_manager
    return mock_runtime


# =============================================================================
# TASK AND ERROR FIXTURES
# =============================================================================

# Real task fixtures removed - they cause event loop issues in tests


# =============================================================================
# SERVICE STOP TASK FIXTURES
# =============================================================================


@pytest.fixture
def service_with_real_task(event_loop):
    """Service with a real asyncio task."""
    service = Mock()
    service.__class__.__name__ = "RealTaskService"

    async def service_work():
        await asyncio.sleep(0.1)  # Shorter sleep

    # Use event_loop fixture to ensure event loop is running
    task = event_loop.create_task(service_work())
    service._task = task
    return service


@pytest.fixture
def service_with_scheduler_only():
    """Service that only has scheduler, no task."""
    service = Mock()
    service.__class__.__name__ = "SchedulerOnlyService"
    service.stop_scheduler = AsyncMock()

    # Explicitly ensure no _task attribute
    if hasattr(service, "_task"):
        delattr(service, "_task")

    return service


# =============================================================================
# MAINTENANCE FIXTURES
# =============================================================================


@pytest.fixture
def mock_runtime_with_maintenance(mock_runtime):
    """Mock runtime with maintenance services."""
    # Mock maintenance service
    maintenance_service = AsyncMock()
    maintenance_service.perform_startup_cleanup = AsyncMock()
    mock_runtime.maintenance_service = maintenance_service

    # Mock TSDB service
    tsdb_service = AsyncMock()
    tsdb_service._run_consolidation = AsyncMock()

    service_initializer = Mock()
    service_initializer.tsdb_consolidation_service = tsdb_service
    mock_runtime.service_initializer = service_initializer

    return mock_runtime


# =============================================================================
# ERROR HANDLING FIXTURES
# =============================================================================


@pytest.fixture
def failing_maintenance_runtime(mock_runtime):
    """Mock runtime with failing maintenance services."""
    # Mock failing maintenance service
    maintenance_service = AsyncMock()
    maintenance_service.perform_startup_cleanup = AsyncMock(side_effect=Exception("Maintenance failed"))
    mock_runtime.maintenance_service = maintenance_service

    # Mock failing TSDB service
    tsdb_service = AsyncMock()
    tsdb_service._run_consolidation = AsyncMock(side_effect=Exception("TSDB failed"))

    service_initializer = Mock()
    service_initializer.tsdb_consolidation_service = tsdb_service
    mock_runtime.service_initializer = service_initializer

    return mock_runtime


# =============================================================================
# CLEANUP FIXTURES - DISABLED to avoid hanging tests
# =============================================================================

# @pytest.fixture(autouse=True)
# async def cleanup_tasks():
#     """Automatically clean up any pending tasks after each test."""
#     yield


# =============================================================================
# PARAMETER SETS
# =============================================================================


@pytest.fixture(params=list(_SERVICE_SHUTDOWN_PRIORITIES.keys()))
def service_priority_keyword(request):
    """Parameterized fixture for all service priority keywords."""
    return request.param


@pytest.fixture(
    params=[
        ("TSDBConsolidationService", 0),
        ("TaskSchedulerService", 1),
        ("MemoryService", 9),
        ("TimeService", 11),
        ("UnknownTypeService", 5),
    ]
)
def service_with_expected_priority(request):
    """Parameterized fixture for services with their expected priorities."""
    service_name, expected_priority = request.param

    service = Mock()
    service.__class__.__name__ = service_name
    service.stop = AsyncMock()

    return service, expected_priority
