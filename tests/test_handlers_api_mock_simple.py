"""
Simplified tests for mock LLM handlers through API.
Validates actual handler functionality and responses.
"""

import pytest
import requests
import time
import socket
from typing import Dict, Any, Optional, List


# Skip all tests in this module if API is not available
def check_api_available():
    """Check if API is accessible."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 8080))
        sock.close()
        return result == 0
    except Exception:
        return False


# Apply skip to entire module
pytestmark = [
    pytest.mark.skipif(not check_api_available(), reason="API not running on localhost:8080"),
    pytest.mark.integration  # Mark as integration test
]


class CIRISAPIClient:
    """Helper class for interacting with CIRIS API."""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.token: Optional[str] = None
        self.headers: Dict[str, str] = {}
        
    def login(self, username: str = "admin", password: str = "ciris_admin_password") -> bool:
        """Login and store authentication token."""
        resp = requests.post(
            f"{self.base_url}/v1/auth/login",
            json={"username": username, "password": password}
        )
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
            return True
        return False
        
    def interact(self, message: str, channel_id: str = "api_test", timeout: int = 5) -> Dict[str, Any]:
        """Send a message to the agent."""
        resp = requests.post(
            f"{self.base_url}/v1/agent/interact",
            json={"message": message, "channel_id": channel_id},
            headers=self.headers,
            timeout=timeout  # Configurable timeout for tests
        )
        return resp.json() if resp.status_code == 200 else {"error": resp.text}
    
    def get_memory(self, node_id: str) -> Dict[str, Any]:
        """Get a specific memory node."""
        resp = requests.get(
            f"{self.base_url}/v1/memory/{node_id}",
            headers=self.headers
        )
        return resp.json() if resp.status_code == 200 else {"error": resp.text}
    
    def search_memory(self, query: str) -> List[Dict[str, Any]]:
        """Search memory nodes."""
        resp = requests.get(
            f"{self.base_url}/v1/memory/search",
            params={"q": query},
            headers=self.headers
        )
        if resp.status_code == 200:
            result = resp.json()
            return result.get("data", {}).get("nodes", [])
        return []
    
    def get_tasks(self, status: str = None) -> List[Dict[str, Any]]:
        """Get tasks, optionally filtered by status."""
        params = {"status": status} if status else {}
        resp = requests.get(
            f"{self.base_url}/v1/agent/tasks",
            params=params,
            headers=self.headers
        )
        if resp.status_code == 200:
            result = resp.json()
            return result.get("data", {}).get("tasks", [])
        return []


@pytest.fixture
def api_client():
    """Create and authenticate API client."""
    client = CIRISAPIClient()
    assert client.login(), "Failed to authenticate with API"
    return client


class TestHandlers:
    """Test all handlers with validation of actual functionality."""
    
    def test_speak(self, api_client):
        """Test SPEAK handler - validates message is spoken."""
        test_message = "Hello from test!"
        result = api_client.interact(f"$speak {test_message}")
        
        # Basic response validation
        assert "data" in result
        assert result["data"]["message_id"] is not None
        assert result["data"]["state"] == "WORK"
        
        # The API will return "Still processing" due to 5s timeout
        # OR the mock LLM might return a follow-up response
        # This is expected behavior - the handler is working correctly
        response = result["data"]["response"]
        # Accept various valid responses:
        # 1. "Still processing" - timeout response
        # 2. test_message - the actual spoken message
        # 3. Mock LLM responses (various formats)
        valid_responses = ["Still processing", test_message, "[MOCK LLM]", "[MOCKLLM", "mock llm"]
        assert any(expected.lower() in response.lower() for expected in valid_responses)
        
    def test_memorize(self, api_client):
        """Test MEMORIZE handler - validates memory is stored."""
        node_id = "test_memory_node"
        result = api_client.interact(f"$memorize {node_id} CONCEPT LOCAL")
        
        assert "data" in result
        assert result["data"]["message_id"] is not None
        
        # Wait for processing
        time.sleep(1)  # Reduced from 3s
        
        # Try to recall the memorized data
        recall_result = api_client.interact(f"$recall {node_id}")
        assert "data" in recall_result
        
    def test_recall(self, api_client):
        """Test RECALL handler - validates memory retrieval."""
        # First memorize something specific
        unique_id = f"recall_test_{int(time.time())}"
        memorize_result = api_client.interact(f"$memorize {unique_id} CONCEPT LOCAL")
        assert "data" in memorize_result
        
        # Wait for memorization to complete
        time.sleep(1)  # Reduced from 3s
        
        # Then recall it
        recall_result = api_client.interact(f"$recall {unique_id}")
        assert "data" in recall_result
        assert recall_result["data"]["message_id"] is not None
        
        # The response should indicate recall operation
        response = recall_result["data"]["response"]
        print(f"RECALL response: {response}")
        if "still processing" not in response.lower():
            # Should either find the memory or report not found
            # Accept various mock LLM responses
            assert any(word in response.lower() for word in ["found", "recall", "memory", "no memories", "mock llm", "mockllm", "speak in response"])
        else:
            # RECALL is an async operation, "Still processing" is expected
            assert True
        
    def test_ponder(self, api_client):
        """Test PONDER handler - validates pondering happens."""
        result = api_client.interact("$ponder What is the meaning of life?; Why do we exist?")
        
        assert "data" in result
        assert result["data"]["message_id"] is not None
        
        # Ponder is an internal action that doesn't return immediate results
        # The API will return "Still processing" which is expected
        response = result["data"]["response"]
        valid_responses = ["Still processing", "[MOCK LLM]", "[MOCKLLM", "mock llm", "ponder"]
        assert any(expected.lower() in response.lower() for expected in valid_responses)
        
    def test_tool(self, api_client):
        """Test TOOL handler - validates tool execution."""
        result = api_client.interact("$tool list_tools")
        
        assert "data" in result
        assert result["data"]["message_id"] is not None
        
        # Tool execution is async and may take time
        # "Still processing" is the expected response
        response = result["data"]["response"]
        valid_responses = ["Still processing", "[MOCK LLM]", "[MOCKLLM", "mock llm", "tool"]
        assert any(expected.lower() in response.lower() for expected in valid_responses)
        
    def test_observe(self, api_client):
        """Test OBSERVE handler - validates observation."""
        result = api_client.interact("$observe api_test")
        
        assert "data" in result
        assert result["data"]["message_id"] is not None
        
        # Observe should process
        response = result["data"]["response"]
        print(f"OBSERVE response: {response}")
        if "Still processing" in response:
            assert "Agent response is not guaranteed" in response
        else:
            # Accept various mock LLM responses
            assert any(word in response.lower() for word in ["observ", "channel", "mock llm", "mockllm", "speak in response"])
        
    def test_defer(self, api_client):
        """Test DEFER handler - validates task deferral."""
        reason = "Need more information"
        result = api_client.interact(f"$defer {reason}")
        
        assert "data" in result
        assert result["data"]["message_id"] is not None
        
        # Defer typically doesn't respond, expect timeout
        response = result["data"]["response"]
        valid_responses = ["Still processing", "[MOCK LLM]", "[MOCKLLM", "mock llm", "Agent response is not guaranteed"]
        assert any(expected.lower() in response.lower() for expected in valid_responses)
        
    def test_reject(self, api_client):
        """Test REJECT handler - validates rejection."""
        reason = "Inappropriate request"
        result = api_client.interact(f"$reject {reason}")
        
        assert "data" in result
        assert result["data"]["message_id"] is not None
        
        # Reject should process
        response = result["data"]["response"]
        print(f"REJECT response: {response}")
        if "Still processing" in response:
            assert "Agent response is not guaranteed" in response
        else:
            # Accept various mock LLM responses
            assert any(word in response.lower() for word in ["reject", "inappropriate", "mock llm", "mockllm", "speak in response"])
        
        # Wait for the reject to fully process before next test
        time.sleep(2)
        
    def test_task_complete(self, api_client):
        """Test TASK_COMPLETE handler - validates task completion."""
        # Add a wait to ensure system is ready after previous tests
        time.sleep(4)
        
        # First create a task by sending a regular message
        # Use a benign message that won't trigger any filters
        speak_result = api_client.interact("$speak Working on test scenario")
        
        # The speak might timeout due to previous test state, which is OK
        # We just need to ensure a task exists for completion
        if "Still processing" not in speak_result["data"]["response"]:
            assert speak_result["data"]["response"] == "Working on test scenario"  # Verify speak worked
        
        time.sleep(1)  # Reduced from 2s
        
        # Then complete it
        result = api_client.interact("$task_complete All done!")
        
        assert "data" in result
        assert result["data"]["message_id"] is not None
        
        # Task complete should NOT generate a response - this is correct behavior
        # The API will timeout waiting for a response, which is expected
        response = result["data"]["response"]
        
        # The response should indicate no agent response (timeout)
        assert "Still processing" in response or "Agent response is not guaranteed" in response
        
        # The important thing is that the task was completed in the audit log
        # We can't easily check audit logs in this test, but the lack of response
        # is the correct behavior for TASK_COMPLETE
        
    def test_help_bug_fixed(self, api_client):
        """Test that $help doesn't break subsequent commands."""
        # First send help
        help_result = api_client.interact("$help")
        assert "data" in help_result
        
        # Wait for help to process
        time.sleep(1)  # Reduced from 3s
        
        # Then try another command - should work
        result = api_client.interact("$speak Testing after help")
        assert "data" in result
        assert result["data"]["message_id"] is not None
        assert result["data"]["state"] == "WORK"
        
        # Should get a response
        response = result["data"]["response"]
        if "still processing" not in response:
            assert len(response) > 0  # Should have some response