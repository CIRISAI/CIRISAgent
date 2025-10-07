"""
Comprehensive tests for IdentityVarianceMonitor service.

This service is critical to the patent's 20% variance threshold requirement.
"""

from datetime import datetime, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.infrastructure.sub_services.identity_variance_monitor import IdentityVarianceMonitor
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.infrastructure.behavioral_patterns import BehavioralPattern
from ciris_engine.schemas.infrastructure.identity_variance import (
    CurrentIdentityData,
    IdentityDiff,
    NodeAttributes,
    VarianceImpact,
    VarianceReport,
    WAReviewRequest,
)
from ciris_engine.schemas.runtime.core import AgentIdentityRoot, CoreProfile, IdentityMetadata
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.nodes import IdentitySnapshot
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


@pytest.fixture
def mock_time_service():
    """Mock time service."""
    service = Mock(spec=TimeServiceProtocol)
    service.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
    return service


@pytest.fixture
def mock_memory_bus():
    """Mock memory bus."""
    bus = AsyncMock()
    bus.memorize.return_value = MemoryOpResult(status=MemoryOpStatus.OK)
    bus.recall.return_value = []
    bus.recall_timeseries.return_value = []
    return bus


@pytest.fixture
def mock_wa_bus():
    """Mock WA bus."""
    bus = AsyncMock()
    bus.request_review.return_value = None
    return bus


@pytest.fixture
def sample_identity():
    """Sample agent identity for testing."""
    return AgentIdentityRoot(
        agent_id="test-agent",
        identity_hash="test-hash-123",
        core_profile=CoreProfile(
            description="Test agent for variance monitoring",
            role_description="Test Role",
            areas_of_expertise=["testing", "monitoring"],
            startup_instructions="Test startup",
            action_selection_pdma_overrides={"test_rule": "test_value"},
            csdma_overrides={"trust_param": "high"},
        ),
        identity_metadata=IdentityMetadata(
            created_at=datetime(2025, 1, 1, 0, 0, 0),
            last_modified=datetime(2025, 1, 1, 0, 0, 0),
            creator_agent_id="system",
        ),
        permitted_actions=["test", "monitor"],
        restricted_capabilities=["dangerous_action"],
    )


@pytest.fixture
def variance_monitor(mock_time_service, mock_memory_bus, mock_wa_bus):
    """Create IdentityVarianceMonitor instance."""
    monitor = IdentityVarianceMonitor(
        time_service=mock_time_service,
        memory_bus=mock_memory_bus,
        wa_bus=mock_wa_bus,
        variance_threshold=0.20,
        check_interval_hours=24,
    )
    return monitor


class TestIdentityVarianceMonitorInit:
    """Test initialization and configuration."""

    def test_init_default_threshold(self, mock_time_service):
        """Test default variance threshold is 20%."""
        monitor = IdentityVarianceMonitor(time_service=mock_time_service)
        assert monitor._variance_threshold == 0.20

    def test_init_custom_threshold(self, mock_time_service):
        """Test custom variance threshold."""
        monitor = IdentityVarianceMonitor(time_service=mock_time_service, variance_threshold=0.15)
        assert monitor._variance_threshold == 0.15

    def test_init_check_interval(self, mock_time_service):
        """Test check interval configuration."""
        monitor = IdentityVarianceMonitor(time_service=mock_time_service, check_interval_hours=12)
        assert monitor._check_interval_hours == 12
        assert monitor._run_interval == 12 * 3600

    def test_get_service_type(self, variance_monitor):
        """Test service type is MAINTENANCE."""
        assert variance_monitor.get_service_type() == ServiceType.MAINTENANCE

    def test_get_actions(self, variance_monitor):
        """Test available actions."""
        actions = variance_monitor._get_actions()
        assert "initialize_baseline" in actions
        assert "check_variance" in actions
        assert "take_snapshot" in actions
        assert "calculate_variance" in actions
        assert "trigger_wa_review" in actions

    def test_check_dependencies(self, variance_monitor):
        """Test dependencies check always returns True."""
        assert variance_monitor._check_dependencies() is True


class TestSetServiceRegistry:
    """Test service registry setup."""

    @pytest.mark.asyncio
    async def test_set_service_registry_creates_memory_bus(self, mock_time_service):
        """Test that setting registry creates memory bus if missing."""
        monitor = IdentityVarianceMonitor(time_service=mock_time_service)
        assert monitor._memory_bus is None

        mock_registry = Mock()
        with patch(
            "ciris_engine.logic.infrastructure.sub_services.identity_variance_monitor.MemoryBus"
        ) as MockMemoryBus:
            monitor.set_service_registry(mock_registry)
            # Memory bus creation is attempted
            assert hasattr(monitor, "_service_registry")

    @pytest.mark.asyncio
    async def test_set_service_registry_creates_wa_bus(self, mock_time_service):
        """Test that setting registry creates WA bus if missing."""
        monitor = IdentityVarianceMonitor(time_service=mock_time_service)
        assert monitor._wa_bus is None

        mock_registry = Mock()
        monitor.set_service_registry(mock_registry)
        assert hasattr(monitor, "_service_registry")

    def test_set_service_registry_handles_null_time_service(self, mock_time_service):
        """Test handles None time service gracefully."""
        monitor = IdentityVarianceMonitor(time_service=None)
        mock_registry = Mock()

        # Should not raise, but should log error
        monitor.set_service_registry(mock_registry)


class TestInitializeBaseline:
    """Test baseline initialization."""

    @pytest.mark.asyncio
    async def test_initialize_baseline_success(self, variance_monitor, sample_identity):
        """Test successful baseline initialization."""
        baseline_id = await variance_monitor.initialize_baseline(sample_identity)

        assert baseline_id.startswith("identity_baseline_")
        assert variance_monitor._baseline_snapshot_id == baseline_id

        # Verify memorize was called with baseline snapshot (first call)
        assert variance_monitor._memory_bus.memorize.call_count >= 1
        first_call = variance_monitor._memory_bus.memorize.call_args_list[0]
        node = first_call.kwargs["node"] if "node" in first_call.kwargs else first_call.args[0]
        assert node.scope == GraphScope.IDENTITY
        assert "is_baseline" in node.attributes or node.attributes.get("is_baseline") is True

    @pytest.mark.asyncio
    async def test_initialize_baseline_stores_reference(self, variance_monitor, sample_identity):
        """Test baseline reference node is stored."""
        await variance_monitor.initialize_baseline(sample_identity)

        # Should call memorize twice: once for baseline, once for reference
        assert variance_monitor._memory_bus.memorize.call_count == 2

    @pytest.mark.asyncio
    async def test_initialize_baseline_no_memory_bus(self, mock_time_service, sample_identity):
        """Test baseline initialization fails without memory bus."""
        monitor = IdentityVarianceMonitor(time_service=mock_time_service)

        with pytest.raises(RuntimeError, match="Memory bus not available"):
            await monitor.initialize_baseline(sample_identity)

    @pytest.mark.asyncio
    async def test_initialize_baseline_no_time_service(self, sample_identity):
        """Test baseline initialization fails without time service."""
        monitor = IdentityVarianceMonitor(time_service=None)
        monitor._memory_bus = AsyncMock()

        with pytest.raises(RuntimeError, match="Time service not available"):
            await monitor.initialize_baseline(sample_identity)

    @pytest.mark.asyncio
    async def test_initialize_baseline_extracts_ethical_boundaries(self, variance_monitor, sample_identity):
        """Test ethical boundaries are extracted from identity."""
        await variance_monitor.initialize_baseline(sample_identity)

        call_args = variance_monitor._memory_bus.memorize.call_args_list[0]
        node = call_args[1]["node"]
        attrs = node.attributes if isinstance(node.attributes, dict) else node.attributes.model_dump()

        ethical_boundaries = attrs.get("ethical_boundaries", [])
        assert "test_rule=test_value" in ethical_boundaries
        assert "restricted:dangerous_action" in ethical_boundaries


class TestVarianceCalculation:
    """Test variance calculation logic."""

    @pytest.mark.asyncio
    async def test_calculate_variance_identical_snapshots(self, variance_monitor):
        """Test variance is 0% for identical snapshots."""
        baseline = GraphNode(
            id="baseline",
            type=NodeType.IDENTITY,
            scope=GraphScope.IDENTITY,
            attributes={"core_purpose": "test", "role": "tester", "trust_level": "high"},
        )
        current = GraphNode(
            id="current",
            type=NodeType.IDENTITY,
            scope=GraphScope.IDENTITY,
            attributes={"core_purpose": "test", "role": "tester", "trust_level": "high"},
        )

        variance = variance_monitor._calculate_variance(baseline, current)
        assert variance == 0.0

    @pytest.mark.asyncio
    async def test_calculate_variance_single_change(self, variance_monitor):
        """Test variance calculation with single attribute change."""
        baseline = GraphNode(
            id="baseline",
            type=NodeType.IDENTITY,
            scope=GraphScope.IDENTITY,
            attributes={"attr1": "value1", "attr2": "value2", "attr3": "value3"},
        )
        current = GraphNode(
            id="current",
            type=NodeType.IDENTITY,
            scope=GraphScope.IDENTITY,
            attributes={"attr1": "value1", "attr2": "CHANGED", "attr3": "value3"},
        )

        variance = variance_monitor._calculate_variance(baseline, current)
        assert variance == pytest.approx(1.0 / 3.0)  # 33% (1 of 3 changed)

    @pytest.mark.asyncio
    async def test_calculate_variance_excludes_metadata(self, variance_monitor):
        """Test variance calculation excludes metadata fields."""
        baseline = GraphNode(
            id="baseline",
            type=NodeType.IDENTITY,
            scope=GraphScope.IDENTITY,
            attributes={"core_purpose": "test", "created_at": "2025-01-01", "timestamp": "12:00"},
        )
        current = GraphNode(
            id="current",
            type=NodeType.IDENTITY,
            scope=GraphScope.IDENTITY,
            attributes={"core_purpose": "test", "created_at": "2025-01-02", "timestamp": "13:00"},
        )

        variance = variance_monitor._calculate_variance(baseline, current)
        assert variance == 0.0  # Metadata changes don't count


class TestCheckVariance:
    """Test variance checking."""

    @pytest.mark.asyncio
    async def test_check_variance_requires_baseline(self, variance_monitor):
        """Test variance check fails without baseline."""
        variance_monitor._memory_bus.recall.return_value = []  # No baseline found

        with pytest.raises(RuntimeError, match="No baseline snapshot available"):
            await variance_monitor.check_variance(force=True)

    @pytest.mark.asyncio
    async def test_check_variance_loads_baseline_if_missing(self, variance_monitor):
        """Test variance check loads baseline if not in memory."""
        # Setup baseline reference node
        baseline_ref = GraphNode(
            id="identity_baseline_current",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={"baseline_id": "baseline-123"},
        )
        variance_monitor._memory_bus.recall.return_value = [baseline_ref]

        # This may or may not fail depending on snapshot availability
        # The important thing is that baseline ID gets loaded
        try:
            await variance_monitor.check_variance(force=True)
        except RuntimeError:
            pass  # Expected if snapshot doesn't exist

        # Verify baseline ID was loaded
        assert variance_monitor._baseline_snapshot_id == "baseline-123"

    @pytest.mark.asyncio
    async def test_check_variance_skips_if_not_due(self, variance_monitor, mock_time_service):
        """Test variance check continues even if interval not elapsed (just logs)."""
        variance_monitor._baseline_snapshot_id = "test-baseline"
        variance_monitor._last_check = mock_time_service.now()

        # Mock the baseline snapshot recall
        mock_snapshot = GraphNode(
            id="test-baseline",
            type=NodeType.IDENTITY_SNAPSHOT,
            scope=GraphScope.IDENTITY,
            attributes={"is_baseline": True},
        )
        variance_monitor._memory_bus.recall.return_value = [mock_snapshot]

        # Mock time hasn't advanced - but check still runs, just logs a debug message
        result = await variance_monitor.check_variance(force=False)

        # Should complete successfully
        assert result is not None


class TestWAReviewTrigger:
    """Test WA review triggering."""

    @pytest.mark.asyncio
    async def test_trigger_wa_review_on_threshold_exceeded(self, variance_monitor):
        """Test WA review triggered when variance exceeds threshold."""
        report = VarianceReport(
            timestamp=datetime.now(),
            baseline_snapshot_id="baseline-123",
            current_snapshot_id="snapshot-456",
            total_variance=0.25,  # 25% > 20% threshold
            differences=[],
            requires_wa_review=True,
            recommendations=["Review required"],
        )

        await variance_monitor._trigger_wa_review(report)

        variance_monitor._wa_bus.request_review.assert_called_once()
        call_args = variance_monitor._wa_bus.request_review.call_args
        assert call_args.kwargs["review_type"] == "identity_variance"

    @pytest.mark.asyncio
    async def test_trigger_wa_review_urgency_high_over_30(self, variance_monitor):
        """Test high urgency for variance over 30%."""
        report = VarianceReport(
            timestamp=datetime.now(),
            baseline_snapshot_id="baseline",
            current_snapshot_id="current",
            total_variance=0.35,  # 35%
            differences=[],
            requires_wa_review=True,
            recommendations=[],
        )

        await variance_monitor._trigger_wa_review(report)

        call_args = variance_monitor._wa_bus.request_review.call_args
        review_data = call_args.kwargs["review_data"]
        assert review_data["urgency"] == "high"

    @pytest.mark.asyncio
    async def test_trigger_wa_review_urgency_moderate_under_30(self, variance_monitor):
        """Test moderate urgency for variance under 30%."""
        report = VarianceReport(
            timestamp=datetime.now(),
            baseline_snapshot_id="baseline",
            current_snapshot_id="current",
            total_variance=0.25,  # 25%
            differences=[],
            requires_wa_review=True,
            recommendations=[],
        )

        await variance_monitor._trigger_wa_review(report)

        call_args = variance_monitor._wa_bus.request_review.call_args
        review_data = call_args.kwargs["review_data"]
        assert review_data["urgency"] == "moderate"

    @pytest.mark.asyncio
    async def test_trigger_wa_review_no_bus(self, mock_time_service):
        """Test WA review handles missing bus gracefully."""
        monitor = IdentityVarianceMonitor(time_service=mock_time_service)
        report = VarianceReport(
            timestamp=datetime.now(),
            baseline_snapshot_id="baseline",
            current_snapshot_id="current",
            total_variance=0.25,
            differences=[],
            requires_wa_review=True,
            recommendations=[],
        )

        # Should not raise, just log error
        await monitor._trigger_wa_review(report)


class TestRecommendations:
    """Test recommendation generation."""

    def test_recommendations_critical_over_threshold(self, variance_monitor):
        """Test critical recommendation when over 20% threshold."""
        recommendations = variance_monitor._generate_simple_recommendations(0.25)

        assert len(recommendations) == 1
        assert "CRITICAL" in recommendations[0]
        assert "25.0%" in recommendations[0]
        assert "WA review required" in recommendations[0]

    def test_recommendations_warning_near_threshold(self, variance_monitor):
        """Test warning recommendation near threshold (>16%)."""
        recommendations = variance_monitor._generate_simple_recommendations(0.17)

        assert len(recommendations) == 1
        assert "WARNING" in recommendations[0]
        assert "approaching 20% threshold" in recommendations[0]

    def test_recommendations_healthy_under_half(self, variance_monitor):
        """Test healthy recommendation when under 10%."""
        recommendations = variance_monitor._generate_simple_recommendations(0.08)

        assert len(recommendations) == 1
        assert "Healthy" in recommendations[0]
        assert "well within safe bounds" in recommendations[0]

    def test_recommendations_empty_between_ranges(self, variance_monitor):
        """Test no recommendations between ranges (10-16%)."""
        recommendations = variance_monitor._generate_simple_recommendations(0.12)

        assert len(recommendations) == 0


class TestRebaseline:
    """Test re-baselining functionality."""

    @pytest.mark.asyncio
    async def test_rebaseline_requires_approval_token(self, variance_monitor):
        """Test re-baseline requires WA approval token."""
        with pytest.raises(ValueError, match="WA approval token required"):
            await variance_monitor.rebaseline_with_approval("")

    @pytest.mark.asyncio
    async def test_rebaseline_success(self, variance_monitor):
        """Test successful re-baseline with approval."""
        # Setup current identity data
        variance_monitor._memory_bus.recall.return_value = [
            GraphNode(
                id="agent/identity",
                type=NodeType.IDENTITY,
                scope=GraphScope.IDENTITY,
                attributes={
                    "agent_id": "test-agent",
                    "identity_hash": "new-hash",
                    "description": "Updated purpose",
                    "role_description": "New role",
                    "permitted_actions": ["action1"],
                    "restricted_capabilities": [],
                },
            )
        ]
        variance_monitor._memory_bus.recall_timeseries.return_value = []

        old_baseline = variance_monitor._baseline_snapshot_id
        new_baseline = await variance_monitor.rebaseline_with_approval("WA-APPROVAL-TOKEN-123")

        assert new_baseline.startswith("identity_baseline_")
        assert variance_monitor._baseline_snapshot_id == new_baseline
        assert variance_monitor._baseline_snapshot_id != old_baseline

    @pytest.mark.asyncio
    async def test_rebaseline_no_memory_bus(self, mock_time_service):
        """Test re-baseline fails without memory bus."""
        monitor = IdentityVarianceMonitor(time_service=mock_time_service)

        with pytest.raises(RuntimeError, match="Memory bus not available"):
            await monitor.rebaseline_with_approval("APPROVAL-TOKEN")


class TestSnapshotCreation:
    """Test identity snapshot creation."""

    @pytest.mark.asyncio
    async def test_take_snapshot_creates_node(self, variance_monitor):
        """Test snapshot creation creates graph node."""
        variance_monitor._memory_bus.recall.return_value = [
            GraphNode(
                id="agent/identity",
                type=NodeType.IDENTITY,
                scope=GraphScope.IDENTITY,
                attributes={"agent_id": "test", "identity_hash": "hash"},
            )
        ]
        variance_monitor._memory_bus.recall_timeseries.return_value = []

        snapshot = await variance_monitor._take_identity_snapshot()

        # _take_identity_snapshot returns a GraphNode already
        assert snapshot.scope == GraphScope.IDENTITY
        assert snapshot.id.startswith("identity_snapshot:")

    @pytest.mark.asyncio
    async def test_take_snapshot_no_time_service(self):
        """Test snapshot creation fails without time service."""
        monitor = IdentityVarianceMonitor(time_service=None)
        monitor._memory_bus = AsyncMock()

        with pytest.raises(RuntimeError, match="Time service not available"):
            await monitor._take_identity_snapshot()


class TestBehavioralPatternAnalysis:
    """Test behavioral pattern analysis."""

    @pytest.mark.asyncio
    async def test_analyze_behavioral_patterns_empty(self, variance_monitor):
        """Test pattern analysis with no data."""
        variance_monitor._memory_bus.recall_timeseries.return_value = []

        patterns = await variance_monitor._analyze_behavioral_patterns()
        assert patterns == []

    @pytest.mark.asyncio
    async def test_analyze_behavioral_patterns_calculates_frequency(self, variance_monitor, mock_time_service):
        """Test pattern frequency calculation."""
        # Mock timeseries data
        from ciris_engine.schemas.runtime.memory import TimeSeriesDataPoint

        variance_monitor._memory_bus.recall_timeseries.return_value = [
            TimeSeriesDataPoint(
                timestamp=mock_time_service.now(),
                metric_name="action_frequency",
                value=1.0,
                correlation_type="METRIC_DATAPOINT",
                tags={"action_type": "speak"},
            ),
            TimeSeriesDataPoint(
                timestamp=mock_time_service.now(),
                metric_name="action_frequency",
                value=1.0,
                correlation_type="METRIC_DATAPOINT",
                tags={"action_type": "speak"},
            ),
            TimeSeriesDataPoint(
                timestamp=mock_time_service.now(),
                metric_name="action_frequency",
                value=1.0,
                correlation_type="METRIC_DATAPOINT",
                tags={"action_type": "think"},
            ),
        ]

        patterns = await variance_monitor._analyze_behavioral_patterns()

        assert len(patterns) == 2
        # Find speak pattern
        speak_pattern = next(p for p in patterns if "speak" in p.pattern_type)
        assert speak_pattern.frequency == pytest.approx(2.0 / 3.0)


class TestHelperMethods:
    """Test helper extraction methods."""

    def test_extract_ethical_boundaries(self, variance_monitor, sample_identity):
        """Test ethical boundary extraction."""
        boundaries = variance_monitor._extract_ethical_boundaries(sample_identity)

        assert "test_rule=test_value" in boundaries
        assert "restricted:dangerous_action" in boundaries

    def test_extract_trust_parameters(self, variance_monitor, sample_identity):
        """Test trust parameter extraction."""
        trust_params = variance_monitor._extract_trust_parameters(sample_identity)

        assert trust_params["trust_param"] == "high"

    def test_extract_capability_changes(self, variance_monitor):
        """Test capability change extraction."""
        nodes = [
            GraphNode(
                id="cap1",
                type=NodeType.CONCEPT,
                scope=GraphScope.IDENTITY,
                attributes={"node_type": "capability_change", "capability": "new_skill"},
            )
        ]

        capabilities = variance_monitor._extract_capability_changes(nodes)
        assert "new_skill" in capabilities


class TestServiceLifecycle:
    """Test service lifecycle methods."""

    @pytest.mark.asyncio
    async def test_on_start(self, variance_monitor):
        """Test service start."""
        await variance_monitor._on_start()
        # Should not raise

    @pytest.mark.asyncio
    async def test_on_stop(self, variance_monitor):
        """Test service stop."""
        await variance_monitor._on_stop()

        # Should clear bus references
        assert variance_monitor._memory_bus is None
        assert variance_monitor._wa_bus is None

    @pytest.mark.asyncio
    async def test_is_healthy_with_memory_bus(self, variance_monitor):
        """Test health check with memory bus."""
        assert await variance_monitor.is_healthy() is True

    @pytest.mark.asyncio
    async def test_is_healthy_without_memory_bus(self, mock_time_service):
        """Test health check without memory bus."""
        monitor = IdentityVarianceMonitor(time_service=mock_time_service)
        assert await monitor.is_healthy() is False

    @pytest.mark.asyncio
    async def test_scheduled_task_execution(self, variance_monitor):
        """Test scheduled task runs variance check."""
        variance_monitor._baseline_snapshot_id = "test-baseline"
        variance_monitor._memory_bus.recall.return_value = []

        # Should attempt variance check but fail gracefully
        await variance_monitor._run_scheduled_task()


class TestStatusAndCapabilities:
    """Test status and capabilities reporting."""

    def test_get_status(self, variance_monitor):
        """Test status reporting."""
        status = variance_monitor.get_status()
        assert status is not None

    def test_get_capabilities(self, variance_monitor):
        """Test capabilities reporting."""
        capabilities = variance_monitor.get_capabilities()

        assert capabilities.service_name == "IdentityVarianceMonitor"
        assert "initialize_baseline" in capabilities.actions
        assert "check_variance" in capabilities.actions


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_check_variance_no_time_service(self):
        """Test variance check with no time service."""
        monitor = IdentityVarianceMonitor(time_service=None)
        monitor._memory_bus = AsyncMock()
        monitor._baseline_snapshot_id = "baseline"

        report = await monitor.check_variance(force=True)

        assert report.total_variance == 0.0
        assert "unavailable" in report.current_snapshot_id

    @pytest.mark.asyncio
    async def test_gather_nodes_handles_exceptions(self, variance_monitor):
        """Test node gathering handles exceptions gracefully."""
        variance_monitor._memory_bus.recall.side_effect = Exception("Test error")

        nodes = await variance_monitor._gather_identity_nodes()
        assert nodes == []

    @pytest.mark.asyncio
    async def test_pattern_analysis_handles_exceptions(self, variance_monitor):
        """Test pattern analysis handles exceptions gracefully."""
        variance_monitor._memory_bus.recall_timeseries.side_effect = Exception("Test error")

        patterns = await variance_monitor._analyze_behavioral_patterns()
        assert patterns == []
