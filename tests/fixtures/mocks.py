"""
Common mock objects and utilities for testing.

Provides properly structured mocks that match production schemas.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

from ciris_engine.schemas.runtime.extended import ShutdownContext
from ciris_engine.schemas.runtime.system_context import TelemetrySummary
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType


def create_telemetry_summary() -> TelemetrySummary:
    """Create a valid TelemetrySummary for testing."""
    now = datetime.now(timezone.utc)
    return TelemetrySummary(
        window_start=now,
        window_end=now,
        uptime_seconds=3600.0,
        messages_processed_24h=100,
        thoughts_processed_24h=50,
        tasks_completed_24h=25,
        errors_24h=2,
        messages_current_hour=10,
        thoughts_current_hour=5,
        errors_current_hour=0,
        tokens_last_hour=1000.0,
        cost_last_hour_cents=15.0,
        carbon_last_hour_grams=0.3,
        energy_last_hour_kwh=0.0005,
    )


def create_shutdown_context() -> ShutdownContext:
    """Create a valid ShutdownContext for testing."""
    return ShutdownContext(
        is_terminal=False,
        reason="Test shutdown",
        initiated_by="test_system",
        allow_deferral=True,
        expected_reactivation=None,
        agreement_context=None,
    )


class MockTelemetryService:
    """Mock telemetry service with proper response types."""

    def __init__(self):
        self.capture_service_metrics = AsyncMock(return_value={})
        self.record_thought = AsyncMock()
        self._telemetry_summary = create_telemetry_summary()

    async def get_telemetry_summary(self) -> TelemetrySummary:
        """Return a proper TelemetrySummary object."""
        return self._telemetry_summary

    async def get_operational_context(self) -> dict:
        """Return operational context data."""
        return {
            "status": "online",
            "overall_health": "healthy",
            "services_total": 25,
            "services_online": 25,
            "memory_used_mb": 100,
            "memory_percent": 2.5,
        }


class MockResourceMonitor:
    """Mock resource monitor with proper structure."""

    def __init__(self):
        self.current_memory = 100
        self.current_memory_percent = 2.5
        self.snapshot = MagicMock()
        self.snapshot.critical = []
        self.snapshot.warnings = []

    def get_current_resources(self) -> dict:
        """Return current resource usage."""
        return {
            "cpu": {"usage_percent": 10.0},
            "memory": {"used_mb": 100, "available_mb": 4000},
            "disk": {"used_gb": 10, "available_gb": 100},
        }


class MockMemoryService:
    """Mock memory service with graph node support."""

    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.memorize = AsyncMock(return_value=MagicMock(success=True))
        self.query = AsyncMock(return_value=[])
        self.query_nodes = AsyncMock(return_value=[])

    async def recall(self, query):
        """Mock recall method that can return nodes."""
        node_id = query.node_id if hasattr(query, "node_id") else str(query)

        # Return identity node if requested
        if node_id == "agent/identity":
            # Create a mock that has model_dump method
            attrs_mock = MagicMock()
            attrs_mock.model_dump = MagicMock(
                return_value={
                    "agent_id": "test_agent",
                    "description": "Test AI Assistant",
                    "role_description": "Testing assistant",
                    "trust_level": 0.8,
                    "permitted_actions": ["speak", "observe"],
                    "restricted_capabilities": ["tool"],
                }
            )

            node = MagicMock()
            node.id = "agent/identity"
            node.type = NodeType.AGENT
            node.scope = GraphScope.IDENTITY
            node.attributes = attrs_mock
            return [node]

        # Return user nodes if requested
        if "user/" in node_id:
            user_id = node_id.replace("user/", "")
            attrs = GraphNodeAttributes(
                user_id=user_id,
                username=f"user_{user_id}",
                trust_level=0.7,
                is_wa=False,
                permissions=["read", "write"],
                last_seen=datetime.now(timezone.utc).isoformat(),
            )
            return [GraphNode(id=node_id, type=NodeType.USER, scope=GraphScope.LOCAL, attributes=attrs.model_dump())]

        return self.nodes.get(node_id, [])

    def add_node(self, node: GraphNode):
        """Add a node to the mock storage."""
        self.nodes[node.id] = node


class MockRuntime:
    """Mock runtime with proper attributes and pipeline controller."""

    def __init__(self, include_logging_mocks=True, include_time_service=True):
        self.agent_id = "test_agent"
        self.current_shutdown_context = create_shutdown_context()
        self._initialized = False
        self._start_time = 0

        # Add missing attributes for runtime tests
        self._shutdown_complete = False
        self._shutdown_event = MagicMock()
        self._shutdown_event.is_set = MagicMock(return_value=False)
        self._shutdown_event.set = MagicMock()
        self._shutdown_reason = None

        # Add adapter-related attributes
        self.adapters = []
        self._adapter_tasks = []
        self.startup_channel_id = ""
        self.adapter_configs = {}
        self.modules_to_load = ["mock_llm"]

        # Add pipeline controller mock with H3ERE step point data
        self.pipeline_controller = self._create_pipeline_controller()

        # Add agent processor mock
        self.agent_processor = MagicMock()
        self.agent_processor.state_manager = MagicMock()
        self.agent_processor.state_manager.get_state.return_value = "WORK"
        # Make state transition methods async
        self.agent_processor.state_manager.can_transition_to = AsyncMock(return_value=True)
        self.agent_processor.state_manager.transition_to = AsyncMock(return_value=True)
        self.agent_processor._pipeline_controller = self.pipeline_controller

        # Add proper task mocking to avoid AsyncMock issues
        self.agent_processor._processing_task = None
        self.agent_processor._stop_event = MagicMock()
        self.agent_processor.shutdown_processor = None

        # Add service initializer mock for logging tests
        self.service_initializer = MagicMock()

        # Add logging-specific mocks if requested
        if include_logging_mocks:
            self._setup_logging_mocks()

        # Add time service mock if requested
        if include_time_service:
            self._setup_time_service_mock()

    def _setup_logging_mocks(self):
        """Set up logging-related mocks for efficient testing."""
        # Mock logging setup success/failure scenarios
        self._logging_setup_success = True
        self._logging_setup_error = None

        # Mock file system operations
        self._log_files_created = []
        self._symlinks_created = []

    def _setup_time_service_mock(self):
        """Set up time service mock."""
        from datetime import datetime

        class MockTimeService:
            def now(self):
                return datetime.now()

            def format_timestamp(self, dt=None):
                if dt is None:
                    dt = self.now()
                return dt.strftime("%Y%m%d_%H%M%S")

        self.time_service = MockTimeService()

    def mock_logging_failure(self, error_message="Mock logging setup failed"):
        """Configure this mock to simulate logging setup failure."""
        self._logging_setup_success = False
        self._logging_setup_error = Exception(error_message)

    def mock_logging_success(self, files_created=None, symlinks_created=None):
        """Configure this mock to simulate successful logging setup."""
        self._logging_setup_success = True
        self._logging_setup_error = None
        self._log_files_created = files_created or ["logs/ciris_agent_20250927_test.log"]
        self._symlinks_created = symlinks_created or ["logs/latest.log", "logs/.current_log"]

    async def initialize(self):
        """Mock initialize method that can simulate success/failure."""
        if not self._logging_setup_success:
            raise self._logging_setup_error or RuntimeError("Initialization failed")
        self._initialized = True

    async def shutdown(self):
        """Mock shutdown method."""
        self._initialized = False
        self._shutdown_complete = True

    def request_shutdown(self, reason: str):
        """Mock request shutdown method."""
        self._shutdown_reason = reason
        self._shutdown_event.set()
        self._shutdown_event.is_set.return_value = True

    def _create_pipeline_controller(self):
        """Create a mock pipeline controller with consistent H3ERE data."""
        from ciris_engine.schemas.services.runtime_control import PipelineState, StepPoint, ThoughtInPipeline

        mock = MagicMock()

        # Mock current pipeline state - realistic empty state (common in production)
        mock.get_current_state.return_value = PipelineState(
            is_paused=True,
            current_round=2,
            # thoughts_by_step will use default factory: empty arrays for all steps
            task_queue=[],
            thought_queue=[],
        )

        # Mock processing metrics - consistent with runtime control fixture
        mock.get_processing_metrics.return_value = {
            "total_processing_time_ms": 850.0,  # Match runtime control fixture
            "tokens_used": 150,
            "step_timings": {
                "GATHER_CONTEXT": 200.0,
                "PERFORM_DMAS": 800.0,
                "PERFORM_ASPDMA": 250.0,
            },
        }

        # Use the centralized step result mock by default
        # Tests can override this by accessing the fixture directly
        mock.get_latest_step_result.return_value = None  # Will be set by test fixtures

        return mock


class MockSecretsService:
    """Mock secrets service."""

    def __init__(self):
        self.list_secrets = MagicMock(return_value=[])
        self.get_secret = MagicMock(return_value=None)


class MockServiceRegistry:
    """Mock service registry."""

    def __init__(self):
        self.services = {}

    def get_all(self) -> dict:
        """Return all registered services."""
        return self.services

    def register(self, service_id: str, service: Any):
        """Register a service."""
        self.services[service_id] = service


class MockPersistence:
    """Mock persistence layer with database connection."""

    def __init__(self):
        self.queue_status = MagicMock()
        self.queue_status.active_tasks = 0
        self.queue_status.deferred_tasks = 0
        self.queue_status.paused = False

        # Mock database connection
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.cursor.fetchone = MagicMock(return_value=None)
        self.cursor.fetchall = MagicMock(return_value=[])
        self.cursor.execute = MagicMock()
        self.connection.cursor = MagicMock(return_value=self.cursor)
        self.connection.__enter__ = MagicMock(return_value=self.connection)
        self.connection.__exit__ = MagicMock(return_value=None)

    def get_queue_status(self):
        """Return queue status."""
        return self.queue_status

    def get_db_connection(self):
        """Return mock database connection."""
        return self.connection


def create_mock_thought(
    thought_id: str = "thought_001",
    content: str = "Test thought content",
    status: str = "processing",
    context: Optional[Any] = None,
) -> MagicMock:
    """Create a mock thought with proper structure."""
    thought = MagicMock()
    thought.thought_id = thought_id
    thought.content = content
    thought.status = status
    thought.source_task_id = None
    thought.thought_type = None
    thought.thought_depth = None
    thought.context = context or MagicMock()
    if hasattr(thought.context, "user_id") and thought.context.user_id is None:
        thought.context.user_id = "test_user"
    return thought


def create_mock_task(
    task_id: str = "task_001", user_id: str = "test_user", correlation_id: str = "test_correlation"
) -> MagicMock:
    """Create a mock task with proper context."""
    from ciris_engine.schemas.tasks import Task, TaskContext, TaskStatus

    return Task(
        task_id=task_id,
        channel_id="test_channel",
        description="Test task",
        status=TaskStatus.ACTIVE,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        context=TaskContext(correlation_id=correlation_id, user_id=user_id),
    )
