"""
Test the pause→interact contract using live API server.

This test uses a real API server instead of complex mocking,
which is more reliable for integration testing.
"""

import asyncio
import pytest
import requests
import time


@pytest.fixture(scope="module") 
def api_base_url():
    """Base URL for the API server."""
    return "http://localhost:8000"


@pytest.fixture(scope="module")
def auth_token(api_base_url):
    """Get authentication token from live API."""
    response = requests.post(
        f"{api_base_url}/v1/auth/login",
        json={"username": "admin", "password": "ciris_admin_password"}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Authentication headers."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestPauseInteractionContract:
    """Test pause→interact contract with live API."""
    
    def test_pause_blocks_interaction_processing(self, api_base_url, auth_headers):
        """
        CRITICAL TEST: Verify that paused processor does not process interactions immediately.
        
        This test validates the core COVENANT transparency requirement using live API.
        """
        # Step 1: Pause the processor
        pause_response = requests.post(
            f"{api_base_url}/v1/system/runtime/pause", 
            headers=auth_headers, 
            json={}
        )
        
        assert pause_response.status_code == 200, f"Pause failed: {pause_response.text}"
        data = pause_response.json()["data"]
        assert data["success"] is True
        assert data["processor_state"] == "paused"
        
        # Step 2: Attempt interaction while paused
        interaction_response = requests.post(
            f"{api_base_url}/v1/agent/interact",
            headers=auth_headers,
            json={"message": "Test ethical decision"}
        )
        
        # The interaction should either be queued or rejected, not processed immediately
        if interaction_response.status_code == 200:
            # If it returns 200, it should indicate queuing, not processing
            data = interaction_response.json().get("data", {})
            response_text = str(data).lower()
            # Accept any of these as valid pause behavior:
            # 1. Explicit queued/pending indication  
            # 2. "Still processing" (slower due to pause)
            # 3. Any mention of paused state
            valid_responses = ["queued", "pending", "paused", "still processing", "check back later"]
            is_valid = any(keyword in response_text for keyword in valid_responses)
            
            assert is_valid, \
                f"Expected pause-aware response but got: {data}"
        else:
            # If it returns an error, it should indicate processor is paused
            assert interaction_response.status_code in [409, 423], \
                f"Expected 409 Conflict or 423 Locked but got {interaction_response.status_code}"
            error_msg = str(interaction_response.json()).lower()
            assert "paused" in error_msg, \
                f"Error should mention paused state: {error_msg}"
    
    def test_state_endpoint_reflects_pause_status(self, api_base_url, auth_headers):
        """Test that the state endpoint correctly reflects pause status."""
        
        # First pause the system 
        pause_response = requests.post(
            f"{api_base_url}/v1/system/runtime/pause",
            headers=auth_headers, 
            json={}
        )
        assert pause_response.status_code == 200
        
        # Check state
        state_response = requests.post(
            f"{api_base_url}/v1/system/runtime/state",
            headers=auth_headers, 
            json={}
        )
        assert state_response.status_code == 200
        
        data = state_response.json()["data"]
        assert data["processor_state"] == "paused", \
            f"Expected paused state but got: {data['processor_state']}"
    
    def test_queue_endpoint_available(self, api_base_url, auth_headers):
        """Test that the queue endpoint is available and returns data."""
        
        # Check queue endpoint exists
        queue_response = requests.get(
            f"{api_base_url}/v1/system/runtime/queue", 
            headers=auth_headers
        )
        assert queue_response.status_code == 200
        
        data = queue_response.json()["data"]
        assert "queue_size" in data, f"Queue response missing queue_size: {data}"
        assert isinstance(data["queue_size"], int), f"Queue size should be int: {data}"
    
    def teardown_method(self, method):
        """Clean up after each test by resuming the processor."""
        # Always try to resume after tests to clean up
        try:
            auth_response = requests.post(
                "http://localhost:8000/v1/auth/login",
                json={"username": "admin", "password": "ciris_admin_password"}
            )
            if auth_response.status_code == 200:
                token = auth_response.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}
                
                # Resume processing
                requests.post(
                    "http://localhost:8000/v1/system/runtime/resume",
                    headers=headers,
                    json={}
                )
        except Exception:
            pass  # Ignore cleanup errors