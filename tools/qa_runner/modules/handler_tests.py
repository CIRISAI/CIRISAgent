"""
Handler interaction test module.
"""

from typing import List

from ..config import QAModule, QATestCase


class HandlerTestModule:
    """Test module for message handlers."""

    @staticmethod
    def get_handler_tests() -> List[QATestCase]:
        """Get comprehensive handler test cases."""
        return [
            # Status handlers
            QATestCase(
                name="Status request",
                module=QAModule.HANDLERS,
                endpoint="/v1/handlers/process",
                method="POST",
                payload={"type": "status_request", "content": "What's your current status?"},
                expected_status=200,
                requires_auth=True,
                description="Test status request handler",
            ),
            QATestCase(
                name="System health check",
                module=QAModule.HANDLERS,
                endpoint="/v1/handlers/process",
                method="POST",
                payload={"type": "health_check", "content": "Are all systems operational?"},
                expected_status=200,
                requires_auth=True,
                description="Test system health handler",
            ),
            # Interaction handlers
            QATestCase(
                name="Simple conversation",
                module=QAModule.HANDLERS,
                endpoint="/v1/handlers/process",
                method="POST",
                payload={"type": "conversation", "content": "Hello, how are you today?"},
                expected_status=200,
                requires_auth=True,
                description="Test conversation handler",
            ),
            QATestCase(
                name="Question answering",
                module=QAModule.HANDLERS,
                endpoint="/v1/handlers/process",
                method="POST",
                payload={"type": "question", "content": "What is your purpose?"},
                expected_status=200,
                requires_auth=True,
                description="Test question answering handler",
            ),
            # Command handlers
            QATestCase(
                name="Command execution",
                module=QAModule.HANDLERS,
                endpoint="/v1/handlers/process",
                method="POST",
                payload={
                    "type": "command",
                    "content": "list current tasks",
                    "context": {"command_type": "task_management"},
                },
                expected_status=200,
                requires_auth=True,
                description="Test command execution handler",
            ),
            QATestCase(
                name="Tool invocation",
                module=QAModule.HANDLERS,
                endpoint="/v1/handlers/process",
                method="POST",
                payload={"type": "tool_request", "content": "list files in current directory", "tool": "list_files"},
                expected_status=200,
                requires_auth=True,
                description="Test tool invocation handler",
            ),
            # Error handling
            QATestCase(
                name="Invalid handler type",
                module=QAModule.HANDLERS,
                endpoint="/v1/handlers/process",
                method="POST",
                payload={"type": "invalid_type", "content": "This should fail"},
                expected_status=400,
                requires_auth=True,
                description="Test invalid handler type",
            ),
            QATestCase(
                name="Missing content",
                module=QAModule.HANDLERS,
                endpoint="/v1/handlers/process",
                method="POST",
                payload={"type": "conversation"},
                expected_status=422,
                requires_auth=True,
                description="Test missing required field",
            ),
            # Complex handlers
            QATestCase(
                name="Multi-step processing",
                module=QAModule.HANDLERS,
                endpoint="/v1/handlers/process",
                method="POST",
                payload={
                    "type": "workflow",
                    "content": "Execute data analysis workflow",
                    "steps": ["collect", "analyze", "report"],
                    "context": {"priority": "high"},
                },
                expected_status=200,
                requires_auth=True,
                description="Test multi-step workflow handler",
            ),
            QATestCase(
                name="Async handler",
                module=QAModule.HANDLERS,
                endpoint="/v1/handlers/process",
                method="POST",
                payload={
                    "type": "async_task",
                    "content": "Start background processing",
                    "async": True,
                    "callback_url": "http://localhost:8000/callback",
                },
                expected_status=202,
                requires_auth=True,
                description="Test async handler processing",
            ),
        ]

    @staticmethod
    def get_simple_handler_tests() -> List[QATestCase]:
        """Get simple handler test cases for quick validation."""
        return [
            QATestCase(
                name="Ping handler",
                module=QAModule.SIMPLE_HANDLERS,
                endpoint="/v1/handlers/ping",
                method="GET",
                expected_status=200,
                requires_auth=False,
                description="Test ping handler",
            ),
            QATestCase(
                name="Echo handler",
                module=QAModule.SIMPLE_HANDLERS,
                endpoint="/v1/handlers/echo",
                method="POST",
                payload={"message": "test echo"},
                expected_status=200,
                requires_auth=False,
                description="Test echo handler",
            ),
            QATestCase(
                name="Version handler",
                module=QAModule.SIMPLE_HANDLERS,
                endpoint="/v1/handlers/version",
                method="GET",
                expected_status=200,
                requires_auth=False,
                description="Test version handler",
            ),
        ]
