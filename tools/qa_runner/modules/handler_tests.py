"""
Handler interaction test module - uses agent/interact endpoint with mock LLM.
"""

from typing import List

from ..config import QAModule, QATestCase


class HandlerTestModule:
    """Test module for agent interactions (formerly handlers)."""

    @staticmethod
    def get_handler_tests() -> List[QATestCase]:
        """Get agent interaction test cases using mock LLM."""
        return [
            # Basic interactions using mock LLM
            QATestCase(
                name="Status request",
                module=QAModule.HANDLERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "What's your current status?"},
                expected_status=200,
                requires_auth=True,
                description="Test status request via agent interact",
            ),
            QATestCase(
                name="System health check",
                module=QAModule.HANDLERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "Are all systems operational?"},
                expected_status=200,
                requires_auth=True,
                description="Test system health via agent interact",
            ),
            # Conversation tests
            QATestCase(
                name="Simple conversation",
                module=QAModule.HANDLERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "Hello, how are you today?"},
                expected_status=200,
                requires_auth=True,
                description="Test conversation via agent interact",
            ),
            QATestCase(
                name="Question answering",
                module=QAModule.HANDLERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "What is your purpose?"},
                expected_status=200,
                requires_auth=True,
                description="Test question answering via agent interact",
            ),
            # Mock LLM specific tests
            QATestCase(
                name="Mock response verification",
                module=QAModule.HANDLERS,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "Tell me about CIRIS"},
                expected_status=200,
                requires_auth=True,
                description="Test mock LLM response",
            ),
        ]

    @staticmethod
    def get_simple_handler_tests() -> List[QATestCase]:
        """Get simple handler test cases - removed as these endpoints don't exist."""
        return []  # No simple handler endpoints in current API
