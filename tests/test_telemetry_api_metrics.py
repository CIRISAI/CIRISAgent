"""
Unit tests for telemetry API endpoint metric name alignment.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes import telemetry
from ciris_engine.schemas.services.graph.telemetry import MetricRecord


class TestTelemetryAPIMetrics:
    """Test that telemetry API endpoints query for correct metric names."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test fixtures."""
        # Create mock telemetry service
        self.mock_telemetry_service = AsyncMock()

        # Create mock request with app state
        self.mock_request = MagicMock(spec=Request)
        self.mock_request.app.state.telemetry_service = self.mock_telemetry_service

        # Mock other services that might be needed
        mock_wise_authority = AsyncMock()
        mock_wise_authority.get_pending_deferrals = AsyncMock(return_value=[])
        self.mock_request.app.state.wise_authority = mock_wise_authority

        mock_incident_service = AsyncMock()
        mock_incident_service.get_incident_count = AsyncMock(return_value=0)
        self.mock_request.app.state.incident_service = mock_incident_service

        # Mock visibility service
        mock_visibility_service = AsyncMock()
        mock_visibility_service.get_current_visibility_state = AsyncMock(return_value={"state": "normal"})
        self.mock_request.app.state.visibility_service = mock_visibility_service

    @pytest.mark.asyncio
    async def test_metrics_endpoint_queries_correct_names(self):
        """Test that /metrics endpoint queries for correct metric names."""
        # Track which metrics are queried
        queried_metrics = []

        async def mock_query_metrics(metric_name, **kwargs):
            queried_metrics.append(metric_name)
            # Return dummy data based on metric type
            if "llm" in metric_name:
                return [
                    MetricRecord(
                        metric_name=metric_name,
                        value=100.0,
                        timestamp=datetime.now(timezone.utc),
                        tags={},
                    ),
                    MetricRecord(
                        metric_name=metric_name,
                        value=150.0,
                        timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
                        tags={},
                    ),
                ]
            return []

        self.mock_telemetry_service.query_metrics = mock_query_metrics

        # Mock auth context
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = AuthContext(
            user_id="test_user", role="OBSERVER", permissions=set(), authenticated_at=datetime.now(timezone.utc)
        )

        # Call the endpoint
        with patch("ciris_engine.logic.adapters.api.routes.telemetry.require_observer", return_value=mock_auth):
            response = await telemetry.get_detailed_metrics(self.mock_request, auth=mock_auth)

        # Verify correct metrics were queried
        expected_metrics = [
            "llm_tokens_used",
            "llm_api_call_structured",
            "llm.tokens.total",
            "llm.tokens.input",
            "llm.tokens.output",
            "llm.cost.cents",
            "llm.environmental.carbon_grams",
            "llm.environmental.energy_kwh",
            "handler_completed_total",
            "handler_invoked_total",
            "thought_processing_completed",
            "thought_processing_started",
            "action_selected_task_complete",
            "action_selected_memorize",
        ]

        for metric in expected_metrics:
            assert metric in queried_metrics, f"Expected {metric} to be queried by /metrics endpoint"

    @pytest.mark.asyncio
    async def test_overview_endpoint_metric_names(self):
        """Test that /overview endpoint uses correct metric names for estimation."""
        # Track metrics queried for total count estimation
        queried_metrics = []

        async def mock_query_metrics_impl(metric_name, **kwargs):
            queried_metrics.append(metric_name)
            return [{"value": 1.0}] if metric_name.startswith("llm") else []

        # Mock telemetry service without get_metric_count to force estimation path
        self.mock_telemetry_service.query_metrics = AsyncMock(side_effect=mock_query_metrics_impl)
        # Delete get_metric_count attribute to force fallback to estimation
        try:
            del self.mock_telemetry_service.get_metric_count
        except AttributeError:
            pass  # Already doesn't have it
        self.mock_telemetry_service.get_usage_summary = AsyncMock(
            return_value={
                "tokens_last_24h": 1000,
                "cost_last_24h_cents": 10,
                "service_health": {"healthy": 20, "degraded": 1},
            }
        )

        # Mock time_service and resource_monitor
        mock_time_service = AsyncMock()
        mock_time_service.now = Mock(return_value=datetime.now(timezone.utc))
        mock_time_service.get_uptime = Mock(return_value=3600.0)
        self.mock_request.app.state.time_service = mock_time_service

        mock_resource_monitor = AsyncMock()
        mock_resource_monitor.get_metrics = AsyncMock(
            return_value={"cpu_percent": 50.0, "memory_mb": 100.0, "memory_percent": 10.0}
        )
        self.mock_request.app.state.resource_monitor = mock_resource_monitor

        # Mock auth
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = AuthContext(
            user_id="test_user", role="OBSERVER", permissions=set(), authenticated_at=datetime.now(timezone.utc)
        )

        # Call overview endpoint
        with patch("ciris_engine.logic.adapters.api.routes.telemetry.require_observer", return_value=mock_auth):
            response = await telemetry.get_telemetry_overview(self.mock_request, auth=mock_auth)

        # Check that correct metrics were queried for total estimation
        expected_overview_metrics = [
            "llm.tokens.total",
            "llm_tokens_used",
            "thought_processing_completed",
            "action_selected_task_complete",
            "handler_invoked_total",
            "action_selected_memorize",
        ]

        for metric in expected_overview_metrics:
            assert metric in queried_metrics, f"Expected {metric} to be queried by overview endpoint"

    @pytest.mark.asyncio
    async def test_individual_metric_endpoint(self):
        """Test that /metrics/{name} endpoint queries the specified metric."""

        # Mock query_metrics with AsyncMock to track calls
        async def mock_query_metrics_impl(metric_name, **kwargs):
            if metric_name == "llm.tokens.total":
                return [
                    {"value": 100.0, "timestamp": datetime.now(timezone.utc), "tags": {}},
                    {"value": 200.0, "timestamp": datetime.now(timezone.utc) - timedelta(hours=1), "tags": {}},
                ]
            return []

        self.mock_telemetry_service.query_metrics = AsyncMock(side_effect=mock_query_metrics_impl)

        # Mock auth
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = AuthContext(
            user_id="test_user", role="OBSERVER", permissions=set(), authenticated_at=datetime.now(timezone.utc)
        )

        # Call individual metric endpoint
        with patch("ciris_engine.logic.adapters.api.routes.telemetry.require_observer", return_value=mock_auth):
            response = await telemetry.get_detailed_metric(
                request=self.mock_request, metric_name="llm.tokens.total", auth=mock_auth, hours=24
            )

        # Verify response contains the metric data
        assert response is not None
        assert response.data.name == "llm.tokens.total"
        # Current value is the last value in the data points list (200.0 from 1 hour ago)
        assert response.data.current_value == 200.0

        # Verify query_metrics was called with correct name
        assert self.mock_telemetry_service.query_metrics.called
        call_args = self.mock_telemetry_service.query_metrics.call_args_list
        # All calls should have metric_name="llm.tokens.total"
        for call in call_args:
            assert call.kwargs.get("metric_name") == "llm.tokens.total" or (
                len(call.args) > 0 and call.args[0] == "llm.tokens.total"
            )

    @pytest.mark.asyncio
    async def test_metrics_endpoint_handles_missing_service(self):
        """Test that endpoints handle missing telemetry service gracefully."""
        # Remove telemetry service
        self.mock_request.app.state.telemetry_service = None

        # Mock auth
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = AuthContext(
            user_id="test_user", role="OBSERVER", permissions=set(), authenticated_at=datetime.now(timezone.utc)
        )

        # Should raise HTTPException with 503
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            with patch("ciris_engine.logic.adapters.api.routes.telemetry.require_observer", return_value=mock_auth):
                await telemetry.get_detailed_metrics(self.mock_request, auth=mock_auth)

        assert exc_info.value.status_code == 503
        assert "Telemetry service" in exc_info.value.detail
