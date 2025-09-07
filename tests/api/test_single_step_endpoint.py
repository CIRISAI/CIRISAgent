"""
Comprehensive unit tests for single-step API endpoint.

Tests the single-step endpoint with detailed step point data,
pipeline state, and backward compatibility.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any

from fastapi import status
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.schemas.services.core.runtime import (
    ProcessorControlResponse,
    ProcessorStatus,
    ProcessorQueueStatus,
)
from ciris_engine.schemas.services.runtime_control import (
    StepPoint,
    StepResultGatherContext,
    StepResultPerformDMAs,
    StepResultPerformASPDMA,
    StepResultConscienceExecution,
    StepResultActionComplete,
    ThoughtInPipeline,
    PipelineState,
    EthicalDMAResult,
    CSDMAResult,
    DSDMAResult,
    ActionSelectionDMAResult,
    ConscienceResult,
)
from ciris_engine.schemas.api.responses import SuccessResponse


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
    def mock_pipeline_controller(self, mock_step_result_perform_dmas):
        """Create mock pipeline controller with step point data."""
        mock = MagicMock()
        
        # Mock current pipeline state
        mock.get_current_state.return_value = PipelineState(
            is_paused=True,
            current_round=5,
            thoughts_by_step={
                str(StepPoint.GATHER_CONTEXT): [
                    ThoughtInPipeline(
                        thought_id="thought_001",
                        task_id="task_001",
                        thought_type="user_request",
                        current_step=StepPoint.GATHER_CONTEXT,
                        entered_step_at=datetime.now(timezone.utc),
                        processing_time_ms=200.0,
                    )
                ],
                str(StepPoint.PERFORM_DMAS): [
                    ThoughtInPipeline(
                        thought_id="thought_001",
                        task_id="task_001", 
                        thought_type="user_request",
                        current_step=StepPoint.PERFORM_DMAS,
                        entered_step_at=datetime.now(timezone.utc),
                        processing_time_ms=800.0,
                    )
                ],
            },
            task_queue=[],
            thought_queue=[],
        )
        
        # Use centralized mock step result
        mock.get_latest_step_result.return_value = mock_step_result_perform_dmas
        
        # Mock processing metrics
        mock.get_processing_metrics.return_value = {
            "total_processing_time_ms": 1250.0,
            "tokens_used": 150,
            "step_timings": {
                "GATHER_CONTEXT": 200.0,
                "PERFORM_DMAS": 800.0,
                "PERFORM_ASPDMA": 250.0,
            }
        }
        
        return mock


    @pytest.fixture
    def mock_app_with_services(self, app, mock_api_runtime_control_service, mock_pipeline_controller):
        """Configure app with mocked services."""
        app.state.main_runtime_control_service = mock_api_runtime_control_service
        
        # Mock runtime with pipeline controller
        mock_runtime = MagicMock()
        mock_runtime.pipeline_controller = mock_pipeline_controller
        mock_runtime.agent_processor = MagicMock()
        mock_runtime.agent_processor.state_manager = MagicMock()
        mock_runtime.agent_processor.state_manager.get_state.return_value = "WORK"
        app.state.runtime = mock_runtime
        
        return app

    def test_basic_single_step_backward_compatibility(self, client, auth_headers, mock_app_with_services):
        """Test that basic single-step endpoint remains unchanged for existing clients."""
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
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
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
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
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
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
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]
        
        # Verify pipeline state structure
        pipeline_state = step_data["pipeline_state"]
        assert "is_paused" in pipeline_state
        assert pipeline_state["is_paused"] is True
        assert "current_round" in pipeline_state
        assert pipeline_state["current_round"] == 5
        assert "thoughts_by_step" in pipeline_state
        
        # Verify thoughts by step data
        thoughts_by_step = pipeline_state["thoughts_by_step"]
        assert str(StepPoint.GATHER_CONTEXT) in thoughts_by_step
        assert str(StepPoint.PERFORM_DMAS) in thoughts_by_step
        
        # Verify thought structure  
        context_thoughts = thoughts_by_step[str(StepPoint.GATHER_CONTEXT)]
        assert len(context_thoughts) == 1
        assert context_thoughts[0]["thought_id"] == "thought_001"
        assert context_thoughts[0]["task_id"] == "task_001"

    def test_enhanced_response_performance_metrics(self, client, auth_headers, mock_app_with_services):
        """Test that performance metrics are included in enhanced response."""
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]
        
        # Verify performance data
        assert step_data["processing_time_ms"] == 1250.0
        assert step_data["tokens_used"] == 150
        
        # Verify demo data includes timing breakdowns
        demo_data = step_data["demo_data"]
        assert "step_timings" in demo_data
        assert "GATHER_CONTEXT" in demo_data["step_timings"]
        assert demo_data["step_timings"]["GATHER_CONTEXT"] == 200.0

    def test_enhanced_response_demo_data_structure(self, client, auth_headers, mock_app_with_services):
        """Test that demo data has proper structure for presentation."""
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]
        
        demo_data = step_data["demo_data"]
        
        # Verify demo data structure
        assert "category" in demo_data
        assert demo_data["category"] == "ethical_reasoning"  # Based on PERFORM_DMAS step
        assert "step_description" in demo_data
        assert "key_insights" in demo_data
        assert "step_timings" in demo_data
        
        # Verify key insights for DMA step
        key_insights = demo_data["key_insights"]
        assert "dmas_executed" in key_insights
        assert len(key_insights["dmas_executed"]) == 3

    def test_enhanced_response_with_different_step_points(self, client, auth_headers, mock_app_with_services, mock_step_result_gather_context):
        """Test enhanced response adapts to different step points."""
        # Update pipeline controller mock to use centralized fixture
        runtime = mock_app_with_services.state.runtime
        runtime.pipeline_controller.get_latest_step_result.return_value = mock_step_result_gather_context
        
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]
        
        # Verify step point changed  
        assert step_data["step_point"] == StepPoint.GATHER_CONTEXT.value
        
        # Verify step result structure for GATHER_CONTEXT
        step_result = step_data["step_result"]
        assert "system_snapshot" in step_result
        assert "agent_identity" in step_result
        assert "thought_context" in step_result
        
        # Verify demo data adapted to context building
        demo_data = step_data["demo_data"]
        assert demo_data["category"] == "system_architecture"

    def test_enhanced_response_error_handling_no_pipeline_controller(self, client, auth_headers, mock_app_with_services):
        """Test enhanced response gracefully handles missing pipeline controller."""
        # Remove pipeline controller
        mock_app_with_services.state.runtime.pipeline_controller = None
        
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]
        
        # Verify basic response still works
        assert step_data["success"] is True
        
        # Verify enhanced fields gracefully default
        assert step_data["step_point"] is None
        assert step_data["step_result"] is None
        assert step_data["pipeline_state"] is None
        assert step_data["processing_time_ms"] == 0.0
        assert step_data["tokens_used"] is None

    def test_enhanced_response_error_handling_step_result_exception(self, client, auth_headers, mock_app_with_services):
        """Test enhanced response handles step result extraction errors."""
        # Mock pipeline controller to raise exception
        runtime = mock_app_with_services.state.runtime
        runtime.pipeline_controller.get_latest_step_result.side_effect = Exception("Step result error")
        
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]
        
        # Verify basic response still succeeds
        assert step_data["success"] is True
        
        # Verify enhanced fields handle errors gracefully
        assert step_data["step_result"] is None

    def test_enhanced_response_queue_depth_accuracy(self, client, auth_headers, mock_app_with_services):
        """Test that enhanced response provides accurate queue depth."""
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]
        
        # Verify queue depth is accurate (not hardcoded 0)
        assert step_data["queue_depth"] == 3
        
        # Verify cognitive state is extracted
        assert step_data["cognitive_state"] == "WORK"

    def test_response_schema_validation(self, client, auth_headers, mock_app_with_services):
        """Test that enhanced response validates against schema."""
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
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
        response = client.post(
            "/v1/system/runtime/step?some_param=value",
            headers=auth_headers,
            json={}
        )
        
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
            response = client.post(
                "/v1/system/runtime/step?include_details=true",
                headers=auth_headers,
                json={}
            )
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
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
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
        response = client.post(
            "/v1/system/runtime/step",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == status.HTTP_200_OK
        content = response.content
        
        # Verify response size is reasonable (should be < 50KB for demo purposes)
        assert len(content) < 50 * 1024
        
        step_data = response.json()["data"]
        
        # Verify that large data structures are summarized in demo_data
        demo_data = step_data["demo_data"]
        assert "summary" in demo_data or "key_insights" in demo_data
        
        # Full data should be in step_result for programmatic access
        assert step_data["step_result"] is not None