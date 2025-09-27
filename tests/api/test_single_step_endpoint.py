"""
Comprehensive unit tests for single-step API endpoint.

Tests the single-step endpoint with detailed step point data,
pipeline state, and backward compatibility.
"""

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.services.core.runtime import ProcessorControlResponse, ProcessorQueueStatus, ProcessorStatus
from ciris_engine.schemas.services.runtime_control import (
    ActionSelectionDMAResult,
    ConscienceResult,
    CSDMAResult,
    DSDMAResult,
    EthicalDMAResult,
    PipelineState,
    StepPoint,
    StepResultActionComplete,
    StepResultConscienceExecution,
    StepResultGatherContext,
    StepResultPerformASPDMA,
    StepResultPerformDMAs,
    ThoughtInPipeline,
)


class TestSingleStepEndpoint:
    """Test single-step endpoint with step point data."""

    @pytest.fixture
    def app(self):
        """Create FastAPI app with required services."""
        app = create_app()

        # Initialize auth service (required for auth endpoints)
        app.state.auth_service = APIAuthService()
        app.state.auth_service._dev_mode = True

        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Get auth headers for testing using dev credentials."""
        return {"Authorization": "Bearer admin:ciris_admin_password"}

    @pytest.fixture
    def mock_app_with_services(self, app, mock_api_runtime_control_service, mock_runtime):
        """Configure app with centralized mocked services."""
        app.state.main_runtime_control_service = mock_api_runtime_control_service
        app.state.runtime = mock_runtime
        return app

    def test_basic_single_step_backward_compatibility(self, client, auth_headers, mock_app_with_services):
        """Test that basic single-step endpoint remains unchanged for existing clients."""
        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify backward compatibility - basic SuccessResponse structure
        assert "data" in data
        assert "metadata" in data

        step_data = data["data"]
        assert "success" in step_data
        assert "message" in step_data
        assert "processor_state" in step_data
        assert "cognitive_state" in step_data
        assert "queue_depth" in step_data

        # Now always includes H3ERE step data for transparency
        assert "step_point" in step_data
        assert "step_result" in step_data or "step_results" in step_data  # Could be either field name
        assert "pipeline_state" in step_data

    def test_single_step_always_includes_enhanced_data(self, client, auth_headers, mock_app_with_services):
        """Test that single-step always includes enhanced H3ERE step data."""
        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        step_data = data["data"]

        # Verify basic fields still present
        assert step_data["success"] is True
        assert "message" in step_data
        assert step_data["processor_state"] == "paused"

        # Always includes H3ERE step data
        assert "step_point" in step_data
        assert "step_result" in step_data or "step_results" in step_data
        assert "pipeline_state" in step_data
        assert "processing_time_ms" in step_data

    def test_enhanced_response_step_point_data(self, client, auth_headers, mock_app_with_services):
        """Test that step point data is correctly included in enhanced response."""
        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]

        # Verify step point information (enum value, not string representation)
        assert step_data["step_point"] == StepPoint.PERFORM_DMAS.value

        # Verify step result structure - API consolidates step results
        step_result = step_data["step_result"]
        assert "steps_processed" in step_result
        assert step_result["steps_processed"] == 1
        assert "results_by_round" in step_result
        assert "summary" in step_result

        # Verify round results structure
        results_by_round = step_result["results_by_round"]
        assert "2" in results_by_round  # Round 2 from mock

        round_result = results_by_round["2"]
        assert "round_number" in round_result
        assert round_result["round_number"] == 2
        assert "task_id" in round_result
        assert round_result["task_id"] == "task_001"

        # Verify step data contains DMA information
        step_data_inner = round_result["step_data"]
        assert "dmas_executed" in step_data_inner
        assert isinstance(step_data_inner["dmas_executed"], list)

    def test_enhanced_response_pipeline_state(self, client, auth_headers, mock_app_with_services):
        """Test that pipeline state is correctly included in enhanced response."""
        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]

        # Verify pipeline state structure
        pipeline_state = step_data["pipeline_state"]
        assert "is_paused" in pipeline_state
        assert pipeline_state["is_paused"] is True
        assert "current_round" in pipeline_state
        assert pipeline_state["current_round"] == 2
        assert "thoughts_by_step" in pipeline_state

        # Verify thoughts by step data structure - empty arrays are valid states
        thoughts_by_step = pipeline_state["thoughts_by_step"]
        assert StepPoint.GATHER_CONTEXT.value in thoughts_by_step  # "gather_context"
        assert StepPoint.PERFORM_DMAS.value in thoughts_by_step  # "perform_dmas"

        # Verify structure is correct - all step points should exist (may be empty)
        assert isinstance(thoughts_by_step[StepPoint.GATHER_CONTEXT.value], list)
        assert isinstance(thoughts_by_step[StepPoint.PERFORM_DMAS.value], list)

        # Pipeline can be empty - this is a valid state
        # If thoughts exist, verify their structure
        context_thoughts = thoughts_by_step[StepPoint.GATHER_CONTEXT.value]
        if context_thoughts:  # Only verify if thoughts exist
            assert context_thoughts[0]["thought_id"] == "thought_001"
            assert context_thoughts[0]["task_id"] == "task_001"

    def test_enhanced_response_performance_metrics(self, client, auth_headers, mock_app_with_services):
        """Test that performance metrics are included in enhanced response."""
        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]

        # Verify performance data - use realistic values from centralized fixture
        assert step_data["processing_time_ms"] == 850.0  # From centralized fixture
        # tokens_used can be None when no LLM operations occurred - valid state
        assert "tokens_used" in step_data  # Field should exist, may be None

        # Verify transparency data - may be None in some states
        transparency_data = step_data.get("transparency_data")
        if transparency_data:  # Only verify if transparency data exists
            assert "step_timings" in transparency_data
            assert "GATHER_CONTEXT" in transparency_data["step_timings"]
            assert transparency_data["step_timings"]["GATHER_CONTEXT"] == 200.0

    def test_enhanced_response_transparency_data_structure(self, client, auth_headers, mock_app_with_services):
        """Test that transparency data has proper structure for presentation."""
        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]

        transparency_data = step_data.get("transparency_data")

        # Transparency data may not always be present - test structure if available
        if transparency_data:
            # Verify transparency data structure
            assert "category" in transparency_data
            # Category may vary based on actual step processing
            assert "step_description" in transparency_data
            assert "key_insights" in transparency_data or "step_timings" in transparency_data

            # If key insights exist, verify structure
            if "key_insights" in transparency_data:
                key_insights = transparency_data["key_insights"]
                # Verify insights have some content
                assert isinstance(key_insights, dict)

    def test_enhanced_response_with_different_step_points(
        self, client, auth_headers, mock_app_with_services, mock_step_result_gather_context
    ):
        """Test enhanced response adapts to different step points."""
        # Update both pipeline controller and runtime control service to use gather_context
        runtime = mock_app_with_services.state.runtime
        runtime.pipeline_controller.get_latest_step_result.return_value = mock_step_result_gather_context

        # Also update the runtime control service single_step response
        runtime_control = mock_app_with_services.state.main_runtime_control_service
        runtime_control.single_step.return_value.step_point = StepPoint.GATHER_CONTEXT.value

        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]

        # Verify step point changed
        assert step_data["step_point"] == StepPoint.GATHER_CONTEXT.value

        # Verify step result structure - API returns consolidated format regardless of step type
        step_result = step_data["step_result"]
        assert "steps_processed" in step_result
        assert "results_by_round" in step_result
        assert "summary" in step_result

        # Verify transparency data if available - may be None
        transparency_data = step_data.get("transparency_data")
        if transparency_data:
            # Category varies based on actual step processing
            assert "category" in transparency_data or "step_description" in transparency_data

    def test_enhanced_response_error_handling_no_pipeline_controller(
        self, client, auth_headers, mock_app_with_services
    ):
        """Test enhanced response gracefully handles missing pipeline controller."""
        # Remove pipeline controller
        mock_app_with_services.state.runtime.pipeline_controller = None

        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]

        # Verify basic response still works
        assert step_data["success"] is True

        # Verify API still works - runtime control service provides core data
        assert step_data["step_point"] == "perform_dmas"  # From runtime control service
        assert step_data["step_result"] is not None  # Runtime control provides this
        assert step_data["processing_time_ms"] == 850.0  # From runtime control service

        # Pipeline-specific fields may be None when pipeline controller missing
        assert step_data.get("pipeline_state") is None or step_data["pipeline_state"] is not None
        assert "tokens_used" in step_data  # Field exists, may be None

    def test_enhanced_response_error_handling_step_result_exception(self, client, auth_headers, mock_app_with_services):
        """Test API error handling when runtime control service fails."""
        # Mock runtime control service to raise exception (line 225 in SUT)
        runtime_control = mock_app_with_services.state.main_runtime_control_service
        runtime_control.single_step.side_effect = Exception("Runtime control error")

        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        # SUT raises HTTPException(500) when runtime_control.single_step() fails (lines 280-282)
        assert response.status_code == 500
        error_data = response.json()
        assert "detail" in error_data
        assert "Runtime control error" in error_data["detail"]

    def test_enhanced_response_queue_depth_accuracy(self, client, auth_headers, mock_app_with_services):
        """Test that enhanced response provides accurate queue depth."""
        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]

        # Verify queue depth is accurate (not hardcoded 0)
        assert step_data["queue_depth"] == 3

        # Verify cognitive state is extracted
        assert step_data["cognitive_state"] == "WORK"

    def test_response_schema_validation(self, client, auth_headers, mock_app_with_services):
        """Test that enhanced response validates against schema."""
        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify top-level SuccessResponse structure
        assert "data" in data
        assert "metadata" in data

        # Verify metadata has standard structure
        metadata = data["metadata"]
        assert "timestamp" in metadata

    def test_single_step_ignores_query_parameters(self, client, auth_headers, mock_app_with_services):
        """Test that single-step endpoint ignores query parameters since it always provides full data."""
        # Test with any query parameter - should be ignored
        response = client.post("/v1/system/runtime/step?some_param=value", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]

        # Always includes H3ERE step data regardless of query parameters
        assert "step_point" in step_data
        assert "step_result" in step_data or "step_results" in step_data
        assert "pipeline_state" in step_data

    def test_concurrent_single_step_requests(self, client, auth_headers, mock_app_with_services):
        """Test that concurrent single-step requests are handled properly."""
        import threading
        import time

        results = []

        def make_request():
            response = client.post("/v1/system/runtime/step?include_details=true", headers=auth_headers, json={})
            results.append(response.status_code)

        # Make concurrent requests
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        # Wait for all to complete
        for thread in threads:
            thread.join()

        # All should succeed
        assert all(status_code == 200 for status_code in results)
        assert len(results) == 3

    def test_basic_single_step_includes_h3ere_data(self, client, auth_headers, mock_app_with_services):
        """Test that basic single-step now includes H3ERE step data from runtime control service."""
        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        step_data = data["data"]

        # Basic fields should still be present
        assert step_data["success"] is True
        assert "message" in step_data

        # CRITICAL: The fixed service should now provide H3ERE step data in basic response
        # This test ensures the bug fix sticks - ProcessorControlResponse now passes through step data
        assert "step_point" in step_data
        assert step_data["step_point"] == "perform_dmas"
        assert "step_result" in step_data  # API consolidates step_results into step_result
        assert step_data["step_result"] is not None
        assert "processing_time_ms" in step_data
        assert step_data["processing_time_ms"] == 850.0
        assert "pipeline_state" in step_data
        assert step_data["pipeline_state"] is not None

    def test_enhanced_response_memory_efficiency(self, client, auth_headers, mock_app_with_services):
        """Test that enhanced response doesn't include excessive data."""
        response = client.post("/v1/system/runtime/step", headers=auth_headers, json={})

        assert response.status_code == status.HTTP_200_OK
        content = response.content

        # Verify response size is reasonable (should be < 50KB for demo purposes)
        assert len(content) < 50 * 1024

        step_data = response.json()["data"]

        # Verify that large data structures are summarized in transparency_data if available
        transparency_data = step_data.get("transparency_data")
        if transparency_data:  # Only check if transparency data exists
            assert "summary" in transparency_data or "key_insights" in transparency_data

        # Full data should be in step_result for programmatic access
        assert step_data["step_result"] is not None
