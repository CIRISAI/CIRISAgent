"""
Unit tests for telemetry API endpoint metric name alignment.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes import telemetry


class TestTelemetryAPIMetrics(unittest.TestCase):
    """Test that telemetry API endpoints query for correct metric names."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock telemetry service
        self.mock_telemetry_service = AsyncMock()

        # Create mock request with app state
        self.mock_request = MagicMock(spec=Request)
        self.mock_request.app.state.telemetry_service = self.mock_telemetry_service

        # Mock other services that might be needed
        self.mock_request.app.state.wise_authority = AsyncMock()
        self.mock_request.app.state.incident_service = AsyncMock()

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
                    {"value": 100.0, "timestamp": datetime.now(timezone.utc)},
                    {"value": 150.0, "timestamp": datetime.now(timezone.utc) - timedelta(hours=1)},
                ]
            return []

        self.mock_telemetry_service.query_metrics = mock_query_metrics

        # Mock auth context
        from ciris_engine.schemas.auth.contexts import AuthContext

        mock_auth = AuthContext(user_id="test_user", role="OBSERVER", agent_id="test_agent")

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
            self.assertIn(metric, queried_metrics, f"Expected {metric} to be queried by /metrics endpoint")

    @pytest.mark.asyncio
    async def test_overview_endpoint_metric_names(self):
        """Test that /overview endpoint uses correct metric names for estimation."""
        # Track metrics queried for total count estimation
        queried_metrics = []

        async def mock_query_metrics(metric_name, **kwargs):
            queried_metrics.append(metric_name)
            return [{"value": 1.0}] if metric_name.startswith("llm") else []

        self.mock_telemetry_service.query_metrics = mock_query_metrics
        self.mock_telemetry_service.get_usage_summary = AsyncMock(
            return_value={
                "tokens_last_24h": 1000,
                "cost_last_24h_cents": 10,
                "service_health": {"healthy": 20, "degraded": 1},
            }
        )

        # Mock other methods
        self.mock_request.app.state.wise_authority.get_pending_deferrals = AsyncMock(return_value=[])
        self.mock_request.app.state.incident_service.get_incident_count = AsyncMock(return_value=0)

        # Mock auth
        from ciris_engine.schemas.auth.contexts import AuthContext

        mock_auth = AuthContext(user_id="test_user", role="OBSERVER", agent_id="test_agent")

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
            self.assertIn(metric, queried_metrics, f"Expected {metric} to be queried by overview endpoint")

    @pytest.mark.asyncio
    async def test_individual_metric_endpoint(self):
        """Test that /metrics/{name} endpoint queries the specified metric."""

        # Mock query_metrics
        async def mock_query_metrics(metric_name, **kwargs):
            if metric_name == "llm.tokens.total":
                return [
                    {"value": 100.0, "timestamp": datetime.now(timezone.utc), "tags": {}},
                    {"value": 200.0, "timestamp": datetime.now(timezone.utc) - timedelta(hours=1), "tags": {}},
                ]
            return []

        self.mock_telemetry_service.query_metrics = mock_query_metrics

        # Mock auth
        from ciris_engine.schemas.auth.contexts import AuthContext

        mock_auth = AuthContext(user_id="test_user", role="OBSERVER", agent_id="test_agent")

        # Call individual metric endpoint
        with patch("ciris_engine.logic.adapters.api.routes.telemetry.require_observer", return_value=mock_auth):
            response = await telemetry.get_metric_details(
                request=self.mock_request, metric_name="llm.tokens.total", auth=mock_auth
            )

        # Verify response contains the metric data
        self.assertIsNotNone(response)
        self.assertEqual(response.data.name, "llm.tokens.total")
        self.assertEqual(response.data.current_value, 100.0)

        # Verify query_metrics was called with correct name
        self.mock_telemetry_service.query_metrics.assert_called()
        call_args = self.mock_telemetry_service.query_metrics.call_args_list
        # Should be called multiple times for different time ranges
        for call in call_args:
            self.assertEqual(call.kwargs.get("metric_name", call.args[0]), "llm.tokens.total")

    @pytest.mark.asyncio
    async def test_metrics_endpoint_handles_missing_service(self):
        """Test that endpoints handle missing telemetry service gracefully."""
        # Remove telemetry service
        self.mock_request.app.state.telemetry_service = None

        # Mock auth
        from ciris_engine.schemas.auth.contexts import AuthContext

        mock_auth = AuthContext(user_id="test_user", role="OBSERVER", agent_id="test_agent")

        # Should raise HTTPException with 503
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as context:
            with patch("ciris_engine.logic.adapters.api.routes.telemetry.require_observer", return_value=mock_auth):
                await telemetry.get_detailed_metrics(self.mock_request, auth=mock_auth)

        self.assertEqual(context.exception.status_code, 503)
        self.assertIn("Telemetry service", context.exception.detail)


if __name__ == "__main__":
    unittest.main()
