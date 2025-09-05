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
    StepResult,
    StepResultBuildContext,
    StepResultPerformDMAs,
    StepResultPerformASPDMA,
    StepResultConscienceExecution,
    StepResultActionSelection,
    StepResultHandlerComplete,
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
    def mock_runtime_control_service(self):
        """Create enhanced mock runtime control service with step point data."""
        mock = AsyncMock()
        
        # Configure basic single_step response
        mock.single_step.return_value = ProcessorControlResponse(
            success=True,
            processor_name="agent",
            operation="single_step",
            new_status=ProcessorStatus.PAUSED,
            message="Processed 1 thought",
        )
        
        # Configure queue status
        mock.get_processor_queue_status.return_value = ProcessorQueueStatus(
            processor_name="agent",
            queue_size=3,
            max_size=1000,
            processing_rate=1.2,
            average_latency_ms=150.0,
            oldest_message_age_seconds=45.0,
        )
        
        return mock

    @pytest.fixture
    def mock_pipeline_controller(self):
        """Create mock pipeline controller with step point data."""
        mock = MagicMock()
        
        # Mock current pipeline state
        mock.get_current_state.return_value = PipelineState(
            is_paused=True,
            current_round=5,
            thoughts_by_step={
                str(StepPoint.BUILD_CONTEXT): [
                    ThoughtInPipeline(
                        thought_id="thought_001",
                        task_id="task_001",
                        thought_type="user_request",
                        current_step=StepPoint.BUILD_CONTEXT,
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
        
        # Mock latest step result
        mock.get_latest_step_result.return_value = self._create_mock_step_result()
        
        # Mock processing metrics
        mock.get_processing_metrics.return_value = {
            "total_processing_time_ms": 1250.0,
            "tokens_used": 150,
            "step_timings": {
                "BUILD_CONTEXT": 200.0,
                "PERFORM_DMAS": 800.0,
                "PERFORM_ASPDMA": 250.0,
            }
        }
        
        return mock

    def _create_mock_step_result(self) -> StepResult:
        """Create a comprehensive mock step result for testing."""
        # Return a PERFORM_DMAS result with rich data matching actual schemas
        return StepResultPerformDMAs(
            step_point=StepPoint.PERFORM_DMAS,
            success=True,
            thought_id="thought_001",
            ethical_dma=EthicalDMAResult(
                decision="approve",
                reasoning="Analyzed ethical implications thoroughly",
                alignment_check="All CIRIS principles satisfied: transparency maintained, user wellbeing prioritized",
            ),
            common_sense_dma=CSDMAResult(
                plausibility_score=0.90,
                flags=["standard_request"],
                reasoning="Applied common sense principles - request is straightforward",
            ),
            domain_dma=DSDMAResult(
                domain="api_development",
                domain_alignment=0.80,
                flags=["technical_accuracy"],
                reasoning="Domain expertise applied following API best practices",
            ),
            dmas_executed=["ethical", "common_sense", "domain"],
            dma_failures=[],  # List, not dict
            longest_dma_time_ms=300.0,
            total_time_ms=800.0,
        )

    @pytest.fixture
    def mock_app_with_services(self, app, mock_runtime_control_service, mock_pipeline_controller):
        """Configure app with mocked services."""
        app.state.main_runtime_control_service = mock_runtime_control_service
        
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
        
        # Verify no enhanced data by default
        assert "step_point" not in step_data
        assert "step_result" not in step_data
        assert "pipeline_state" not in step_data

    def test_enhanced_single_step_with_details_parameter(self, client, auth_headers, mock_app_with_services):
        """Test enhanced single-step with ?include_details=true parameter."""
        response = client.post(
            "/v1/system/runtime/step?include_details=true",
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
        
        # Verify enhanced fields present
        assert "step_point" in step_data
        assert "step_result" in step_data
        assert "pipeline_state" in step_data
        assert "processing_time_ms" in step_data
        assert "tokens_used" in step_data
        assert "demo_data" in step_data

    def test_enhanced_response_step_point_data(self, client, auth_headers, mock_app_with_services):
        """Test that step point data is correctly included in enhanced response."""
        response = client.post(
            "/v1/system/runtime/step?include_details=true",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]
        
        # Verify step point information (enum value, not string representation)
        assert step_data["step_point"] == StepPoint.PERFORM_DMAS.value
        
        # Verify step result structure
        step_result = step_data["step_result"]
        assert "step_point" in step_result
        assert "thought_id" in step_result
        assert step_result["thought_id"] == "thought_001"
        
        # Verify DMA results are included
        assert "ethical_dma" in step_result
        assert "common_sense_dma" in step_result
        assert "domain_dma" in step_result
        
        # Verify DMA result details
        ethical_dma = step_result["ethical_dma"]
        assert "reasoning" in ethical_dma
        assert "decision" in ethical_dma
        assert ethical_dma["decision"] == "approve"

    def test_enhanced_response_pipeline_state(self, client, auth_headers, mock_app_with_services):
        """Test that pipeline state is correctly included in enhanced response."""
        response = client.post(
            "/v1/system/runtime/step?include_details=true",
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
        assert str(StepPoint.BUILD_CONTEXT) in thoughts_by_step
        assert str(StepPoint.PERFORM_DMAS) in thoughts_by_step
        
        # Verify thought structure  
        context_thoughts = thoughts_by_step[str(StepPoint.BUILD_CONTEXT)]
        assert len(context_thoughts) == 1
        assert context_thoughts[0]["thought_id"] == "thought_001"
        assert context_thoughts[0]["task_id"] == "task_001"

    def test_enhanced_response_performance_metrics(self, client, auth_headers, mock_app_with_services):
        """Test that performance metrics are included in enhanced response."""
        response = client.post(
            "/v1/system/runtime/step?include_details=true",
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
        assert "BUILD_CONTEXT" in demo_data["step_timings"]
        assert demo_data["step_timings"]["BUILD_CONTEXT"] == 200.0

    def test_enhanced_response_demo_data_structure(self, client, auth_headers, mock_app_with_services):
        """Test that demo data has proper structure for presentation."""
        response = client.post(
            "/v1/system/runtime/step?include_details=true",
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

    def test_enhanced_response_with_different_step_points(self, client, auth_headers, mock_app_with_services):
        """Test enhanced response adapts to different step points."""
        # Mock a different step result
        mock_build_context_result = StepResultBuildContext(
            step_point=StepPoint.BUILD_CONTEXT,
            success=True,
            thought_id="thought_002",
            system_snapshot={"agent_state": "active", "services": 25},
            agent_identity={"agent_id": "test_agent", "role": "assistant"},
            thought_context={"user_id": "test_user", "channel": "test_channel"},
            channel_context={"type": "discord", "permissions": ["read", "write"]},
            memory_context={"relevant_memories": 3},
            permitted_actions=["speak", "observe"],
            constraints=["no_harmful_content"],
            context_size_bytes=2048,
            memory_queries_performed=2,
        )
        
        # Update pipeline controller mock
        runtime = mock_app_with_services.state.runtime
        runtime.pipeline_controller.get_latest_step_result.return_value = mock_build_context_result
        
        response = client.post(
            "/v1/system/runtime/step?include_details=true",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]
        
        # Verify step point changed  
        assert step_data["step_point"] == StepPoint.BUILD_CONTEXT.value
        
        # Verify step result structure for BUILD_CONTEXT
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
            "/v1/system/runtime/step?include_details=true",
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
            "/v1/system/runtime/step?include_details=true",
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
            "/v1/system/runtime/step?include_details=true",
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
            "/v1/system/runtime/step?include_details=true",
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

    def test_invalid_include_details_parameter(self, client, auth_headers, mock_app_with_services):
        """Test handling of invalid include_details parameter values."""
        # Test with invalid boolean string - FastAPI will return 422
        response = client.post(
            "/v1/system/runtime/step?include_details=invalid",
            headers=auth_headers,
            json={}
        )
        
        # FastAPI returns 422 for invalid query parameter types
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Test with valid false value
        response = client.post(
            "/v1/system/runtime/step?include_details=false",
            headers=auth_headers,
            json={}
        )
        
        assert response.status_code == status.HTTP_200_OK
        step_data = response.json()["data"]
        
        # Should not include enhanced data
        assert "step_point" not in step_data

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

    def test_enhanced_response_memory_efficiency(self, client, auth_headers, mock_app_with_services):
        """Test that enhanced response doesn't include excessive data."""
        response = client.post(
            "/v1/system/runtime/step?include_details=true",
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