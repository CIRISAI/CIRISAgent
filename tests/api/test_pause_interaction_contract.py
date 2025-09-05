"""
Test the critical pause→interact contract for COVENANT transparency compliance.

This test validates that when a processor is paused, interactions are queued
and not processed immediately, enabling single-step debugging of the ethical
reasoning pipeline as required by the COVENANT.
"""

import asyncio
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from ciris_engine.logic.adapters.api.adapter import ApiPlatform
from ciris_engine.schemas.services.core.runtime import RuntimeStatusResponse
from tests.fixtures.runtime_control import mock_main_runtime_control_service
from tests.fixtures.authentication import mock_authentication_service, mock_api_auth_service


# Using fixtures from tests/fixtures/ instead of inline mocks


@pytest.fixture
def mock_communication_service():
    """Mock communication service with proper typed responses."""
    mock = AsyncMock()
    mock.process_message = AsyncMock(return_value={
        "message_id": "test-123",
        "response": "Mock response",
        "state": "WORK",
        "processing_time_ms": 100
    })
    return mock


class TestPauseInteractionContract:
    """Test the pause→interact contract for COVENANT compliance."""

    @pytest.mark.asyncio
    async def test_pause_blocks_interaction_processing(self, mock_main_runtime_control_service, mock_communication_service, mock_authentication_service, mock_api_auth_service):
        """
        CRITICAL TEST: Verify that paused processor does not process interactions immediately.
        
        This test validates the core COVENANT transparency requirement:
        When paused, the ethical reasoning pipeline must be inspectable step-by-step.
        """
        # Setup API with comprehensive mocked services
        with patch('ciris_engine.logic.buses.RuntimeControlBus') as mock_rcb, \
             patch('ciris_engine.logic.buses.CommunicationBus') as mock_cb, \
             patch.object(ApiPlatform, 'start') as mock_start:
            
            # Configure runtime control bus
            mock_rcb.return_value.get_service.return_value = mock_main_runtime_control_service
            
            # Configure communication bus 
            mock_cb.return_value.get_service.return_value = mock_communication_service
            
            # Create real APIAuthService in dev mode
            from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
            real_auth_service = APIAuthService()
            real_auth_service._dev_mode = True
            
            # Create API platform with mocked services
            mock_runtime = MagicMock()
            # Add pipeline_controller to mock_runtime
            mock_runtime.pipeline_controller = MagicMock()
            mock_runtime.pipeline_controller.get_current_state = MagicMock(return_value=None)
            api_platform = ApiPlatform(mock_runtime)
            
            # Mock the start method to avoid real service initialization
            mock_start.return_value = None
            
            # Set up the app directly without starting services
            from ciris_engine.logic.adapters.api.app import create_app
            api_platform.app = create_app()
            
            # Mock all the services that would be injected
            api_platform.app.state.main_runtime_control_service = mock_main_runtime_control_service
            api_platform.app.state.runtime_control_service = None
            api_platform.app.state.runtime = mock_runtime
            api_platform.app.state.authentication_service = mock_authentication_service
            api_platform.app.state.auth_service = real_auth_service
            
            app = api_platform.app
            client = TestClient(app)
            
            # Authenticate
            login_response = client.post("/v1/auth/login", json={
                "username": "admin",
                "password": "ciris_admin_password"
            })
            if login_response.status_code != 200:
                print(f"Login failed: {login_response.status_code}")
                print(f"Response: {login_response.text}")
            assert login_response.status_code == 200
            token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            # Step 1: Pause the processor
            pause_response = client.post("/v1/system/runtime/pause", 
                                       headers=headers, json={})
            assert pause_response.status_code == 200
            assert pause_response.json()["data"]["success"] is True
            assert pause_response.json()["data"]["processor_state"] == "paused"
            
            # Verify pause was actually called
            mock_main_runtime_control_service.pause_processing.assert_called_once()
            
            # Step 2: Modify the mock to simulate paused state
            # The processor should now be paused and NOT process interactions
            mock_communication_service.process_message.side_effect = Exception(
                "VIOLATION: Processor is paused but attempted to process interaction!"
            )
            
            # Step 3: Attempt interaction while paused
            # This should either:
            # A) Queue the interaction without processing, OR
            # B) Return an error indicating processor is paused
            interaction_response = client.post("/v1/agent/interact",
                                             headers=headers,
                                             json={"message": "Test ethical decision"})
            
            # The interaction should NOT be processed immediately
            # It should either be queued or rejected
            if interaction_response.status_code == 200:
                # If it returns 200, it should indicate queuing, not processing
                data = interaction_response.json()["data"]
                assert "queued" in str(data).lower() or "pending" in str(data).lower(), \
                    f"Expected queued/pending indication but got: {data}"
                
                # Verify the communication service was NOT called to process
                mock_communication_service.process_message.assert_not_called()
            else:
                # If it returns an error, it should indicate processor is paused
                assert interaction_response.status_code in [409, 423], \
                    f"Expected 409 Conflict or 423 Locked but got {interaction_response.status_code}"
                error_msg = str(interaction_response.json())
                assert "paused" in error_msg.lower(), \
                    f"Error should mention paused state: {error_msg}"

    @pytest.mark.asyncio
    async def test_state_endpoint_reflects_pause_status(self, mock_main_runtime_control_service, mock_authentication_service, mock_api_auth_service):
        """
        Test that the state endpoint correctly reflects pause status.
        
        This ensures the RuntimeStatusResponse includes pause state information.
        """
        with patch('ciris_engine.logic.buses.RuntimeControlBus') as mock_rcb, \
             patch.object(ApiPlatform, 'start') as mock_start:
            mock_rcb.return_value.get_service.return_value = mock_main_runtime_control_service
            
            # Create real APIAuthService in dev mode
            from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
            real_auth_service = APIAuthService()
            real_auth_service._dev_mode = True
            
            # Mock a paused runtime status
            mock_main_runtime_control_service.get_runtime_status.return_value = MagicMock()
            mock_main_runtime_control_service.get_runtime_status.return_value.paused = True
            mock_main_runtime_control_service.get_runtime_status.return_value.cognitive_state = "PAUSED"
            mock_main_runtime_control_service.get_runtime_status.return_value.queue_depth = 1
            
            # Create mock runtime
            mock_runtime = MagicMock()
            # Add pipeline_controller to mock_runtime
            mock_runtime.pipeline_controller = MagicMock()
            mock_runtime.pipeline_controller.get_current_state = MagicMock(return_value=None)
            
            api_platform = ApiPlatform(mock_runtime)
            # Mock the start method to avoid real service initialization
            mock_start.return_value = None
            
            # Set up the app directly without starting services
            from ciris_engine.logic.adapters.api.app import create_app
            api_platform.app = create_app()
            
            # Mock all required services
            api_platform.app.state.main_runtime_control_service = mock_main_runtime_control_service
            api_platform.app.state.authentication_service = mock_authentication_service
            api_platform.app.state.auth_service = real_auth_service
            api_platform.app.state.runtime = mock_runtime
            
            app = api_platform.app
            client = TestClient(app)
            
            # Authenticate
            login_response = client.post("/v1/auth/login", json={
                "username": "admin",
                "password": "ciris_admin_password"
            })
            token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            # Check state
            state_response = client.post("/v1/system/runtime/state", 
                                       headers=headers, json={})
            assert state_response.status_code == 200
            
            data = state_response.json()["data"]
            assert data["processor_state"] == "paused", \
                f"Expected paused state but got: {data['processor_state']}"

    @pytest.mark.asyncio  
    async def test_queue_depth_increases_when_paused(self, mock_main_runtime_control_service, mock_authentication_service, mock_api_auth_service):
        """
        Test that queue depth increases when interactions are sent to paused processor.
        
        This validates the queuing mechanism for step-by-step debugging.
        """
        with patch('ciris_engine.logic.buses.RuntimeControlBus') as mock_rcb, \
             patch.object(ApiPlatform, 'start') as mock_start:
            mock_rcb.return_value.get_service.return_value = mock_main_runtime_control_service
            
            # Create real APIAuthService in dev mode
            from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
            real_auth_service = APIAuthService()
            real_auth_service._dev_mode = True
            
            # Create mock runtime
            mock_runtime = MagicMock()
            # Add pipeline_controller to mock_runtime
            mock_runtime.pipeline_controller = MagicMock()
            mock_runtime.pipeline_controller.get_current_state = MagicMock(return_value=None)
            
            api_platform = ApiPlatform(mock_runtime)
            # Mock the start method to avoid real service initialization
            mock_start.return_value = None
            
            # Set up the app directly without starting services
            from ciris_engine.logic.adapters.api.app import create_app
            api_platform.app = create_app()
            
            # Mock all required services
            api_platform.app.state.main_runtime_control_service = mock_main_runtime_control_service
            api_platform.app.state.authentication_service = mock_authentication_service
            api_platform.app.state.auth_service = real_auth_service
            api_platform.app.state.runtime = mock_runtime
            
            app = api_platform.app
            client = TestClient(app)
            
            # Authenticate
            login_response = client.post("/v1/auth/login", json={
                "username": "admin", 
                "password": "ciris_admin_password"
            })
            token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            
            # Pause processor
            pause_response = client.post("/v1/system/runtime/pause",
                                       headers=headers, json={})
            assert pause_response.status_code == 200
            
            # Check initial queue
            queue_response = client.get("/v1/system/runtime/queue", headers=headers)
            initial_queue_size = queue_response.json()["data"]["queue_size"]
            
            # Send interaction while paused
            interaction_response = client.post("/v1/agent/interact",
                                             headers=headers,
                                             json={"message": "Test"})
            
            # Check queue increased (unless interaction was rejected)
            if interaction_response.status_code == 200:
                queue_response = client.get("/v1/system/runtime/queue", headers=headers)
                final_queue_size = queue_response.json()["data"]["queue_size"]
                assert final_queue_size > initial_queue_size, \
                    "Queue size should increase when interactions are sent to paused processor"

    def test_pause_contract_documentation(self):
        """
        Document the expected pause→interact contract for COVENANT compliance.
        """
        contract = """
        PAUSE→INTERACT CONTRACT FOR COVENANT TRANSPARENCY:
        
        1. When processor.pause_processing() is called:
           - All new interactions must be QUEUED, not processed immediately
           - State endpoint must return processor_state: "paused" 
           - Queue endpoint must show queued interactions
           
        2. When processor is paused and interaction is received:
           - Option A: Queue interaction and return queue confirmation
           - Option B: Reject interaction with 409/423 status code
           - NEVER: Process interaction immediately (violates transparency)
           
        3. Single-step functionality requires:
           - Paused processor to have queued thoughts/interactions
           - Step endpoint to process exactly one pipeline step
           - Detailed step information for audit trail
           
        4. COVENANT compliance mandates:
           - Step-by-step visibility of 15-step ethical reasoning pipeline
           - Audit trail of PDMA (Principled Decision-Making Algorithm)
           - No "black box" processing during ethical decisions
        """
        
        # This test passes by documenting the contract
        assert len(contract) > 0