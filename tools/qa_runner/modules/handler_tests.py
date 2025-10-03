"""
Handler interaction test module - uses agent/message endpoint with SSE streaming.

Updated to use async /agent/message + SSE streaming for optimal performance.
"""

from typing import List

from ..config import QAModule, QATestCase


class HandlerTestModule:
    """Test module for agent interactions via SSE streaming."""

    @staticmethod
    def get_handler_tests() -> List[QATestCase]:
        """Get agent interaction test cases using async message submission + SSE."""
        return [
            # Basic interactions using SSE streaming
            QATestCase(
                name="Status request",
                module=QAModule.HANDLERS,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "What's your current status?"},
                expected_status=200,  # Async submission returns 200 OK with task_id
                requires_auth=True,
                description="Test status request via async message + SSE",
                timeout=30.0,  # Reduced from 120s - SSE is much faster
            ),
            QATestCase(
                name="System health check",
                module=QAModule.HANDLERS,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "Are all systems operational?"},
                expected_status=200,  # Async submission returns 200 OK with task_id
                requires_auth=True,
                description="Test system health via async message + SSE",
                timeout=30.0,
            ),
            # Conversation tests
            QATestCase(
                name="Simple conversation",
                module=QAModule.HANDLERS,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "Hello, how are you today?"},
                expected_status=200,  # Async submission returns 200 OK with task_id
                requires_auth=True,
                description="Test conversation via async message + SSE",
                timeout=30.0,
            ),
            QATestCase(
                name="Question answering",
                module=QAModule.HANDLERS,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "What is your purpose?"},
                expected_status=200,  # Async submission returns 200 OK with task_id
                requires_auth=True,
                description="Test question answering via async message + SSE",
                timeout=30.0,
            ),
            # Mock LLM specific tests
            QATestCase(
                name="Mock response verification",
                module=QAModule.HANDLERS,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "Tell me about CIRIS"},
                expected_status=200,  # Async submission returns 200 OK with task_id
                requires_auth=True,
                description="Test mock LLM response via async message + SSE",
                timeout=30.0,
            ),
        ]

    @staticmethod
    def get_simple_handler_tests() -> List[QATestCase]:
        """Get simple handler test cases - removed as these endpoints don't exist."""
        return []  # No simple handler endpoints in current API
