"""
API endpoint test module.
"""

from typing import Dict, List, Optional

from ..config import QAModule, QATestCase


class APITestModule:
    """Test module for API endpoints."""

    @staticmethod
    def get_auth_tests() -> List[QATestCase]:
        """Get authentication test cases."""
        return [
            QATestCase(
                name="Login with valid credentials",
                module=QAModule.AUTH,
                endpoint="/v1/auth/login",
                method="POST",
                payload={"username": "admin", "password": "ciris_admin_password"},
                expected_status=200,
                requires_auth=False,
                description="Test login with default admin credentials",
            ),
            QATestCase(
                name="Login with invalid credentials",
                module=QAModule.AUTH,
                endpoint="/v1/auth/login",
                method="POST",
                payload={"username": "admin", "password": "wrong_password"},
                expected_status=401,
                requires_auth=False,
                description="Test login failure with wrong password",
            ),
            QATestCase(
                name="Get current user",
                module=QAModule.AUTH,
                endpoint="/v1/auth/me",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting current authenticated user",
            ),
            # Note: No user list endpoint exists, removed this test
        ]

    @staticmethod
    def get_telemetry_tests() -> List[QATestCase]:
        """Get telemetry test cases."""
        return [
            QATestCase(
                name="Unified telemetry",
                module=QAModule.TELEMETRY,
                endpoint="/v1/telemetry/unified",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test unified telemetry endpoint",
            ),
            QATestCase(
                name="Service health",
                module=QAModule.TELEMETRY,
                endpoint="/v1/system/services",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test service health monitoring",
            ),
            QATestCase(
                name="System metrics",
                module=QAModule.TELEMETRY,
                endpoint="/v1/telemetry/metrics",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test system metrics endpoint",
            ),
            QATestCase(
                name="Resource usage",
                module=QAModule.TELEMETRY,
                endpoint="/v1/telemetry/resources",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test resource usage monitoring",
            ),
        ]

    @staticmethod
    def get_agent_tests() -> List[QATestCase]:
        """Get agent interaction test cases."""
        return [
            QATestCase(
                name="Agent status",
                module=QAModule.AGENT,
                endpoint="/v1/agent/status",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test agent status endpoint",
            ),
            QATestCase(
                name="Simple interaction",
                module=QAModule.AGENT,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "Hello, how are you?"},
                expected_status=200,
                requires_auth=True,
                description="Test simple agent interaction",
                timeout=120.0,
            ),
            QATestCase(
                name="Complex interaction",
                module=QAModule.AGENT,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "What is the current system status?", "context": {"request_type": "status_check"}},
                expected_status=200,
                requires_auth=True,
                description="Test complex agent interaction with context",
                timeout=120.0,
            ),
            QATestCase(
                name="Interaction history",
                module=QAModule.AGENT,
                endpoint="/v1/agent/history",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting interaction history",
            ),
            # New async message submission endpoint tests
            QATestCase(
                name="Message submission - immediate return",
                module=QAModule.AGENT,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "Hello async world!"},
                expected_status=200,
                requires_auth=True,
                description="Test async message submission with immediate task_id return",
            ),
            QATestCase(
                name="Message submission - task tracking",
                module=QAModule.AGENT,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "Can you track this task?"},
                expected_status=200,
                requires_auth=True,
                description="Test message submission returns trackable task_id",
            ),
            QATestCase(
                name="Message submission - with context",
                module=QAModule.AGENT,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "Message with context", "context": {"source": "qa_test", "priority": "high"}},
                expected_status=200,
                requires_auth=True,
                description="Test message submission with additional context",
            ),
            QATestCase(
                name="Message submission - status check",
                module=QAModule.AGENT,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "What is your status?"},
                expected_status=200,
                requires_auth=True,
                description="Test message submission returns complete status",
            ),
            # Clear history endpoint doesn't exist - removed
        ]

    @staticmethod
    def get_system_tests() -> List[QATestCase]:
        """Get system management test cases."""
        return [
            QATestCase(
                name="System health",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/health",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test system health endpoint",
            ),
            QATestCase(
                name="List adapters",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/adapters",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test listing system adapters",
            ),
            QATestCase(
                name="List module types",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/adapters/types",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test listing available module/adapter types with configuration schemas",
            ),
            QATestCase(
                name="Processing queue status",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/queue",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test processing queue status",
            ),
            QATestCase(
                name="System configuration",
                module=QAModule.SYSTEM,
                endpoint="/v1/config",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting system configuration",
            ),
        ]

    @staticmethod
    def get_memory_tests() -> List[QATestCase]:
        """Get memory operation test cases."""
        return [
            QATestCase(
                name="Memory search",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/query",
                method="POST",
                payload={"query": "test", "limit": 10},
                expected_status=200,
                requires_auth=True,
                description="Test memory search functionality",
            ),
            QATestCase(
                name="Memory statistics",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/stats",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test memory statistics endpoint",
            ),
            QATestCase(
                name="Store memory",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/store",
                method="POST",
                payload={
                    "node": {
                        "id": "test-node-qa",
                        "type": "observation",
                        "scope": "local",
                        "attributes": {
                            "created_by": "qa_runner",
                            "tags": ["test", "qa"],
                            "content": "Test memory entry from QA",
                            "source": "qa_test",
                        },
                    }
                },
                expected_status=200,
                requires_auth=True,
                description="Test storing new memory",
            ),
        ]

    @staticmethod
    def get_audit_tests() -> List[QATestCase]:
        """Get audit trail test cases."""
        return [
            QATestCase(
                name="List audit entries",
                module=QAModule.AUDIT,
                endpoint="/v1/audit/entries",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test listing audit entries",
            ),
            QATestCase(
                name="Search audit entries",
                module=QAModule.AUDIT,
                endpoint="/v1/audit/search",
                method="POST",
                payload={"query": "test"},
                expected_status=200,
                requires_auth=True,
                description="Test audit search functionality",
            ),
            QATestCase(
                name="Export audit data",
                module=QAModule.AUDIT,
                endpoint="/v1/audit/export",
                method="POST",
                payload={"format": "json", "include_system": False},
                expected_status=200,
                requires_auth=True,
                description="Test audit data export",
            ),
        ]

    @staticmethod
    def get_tool_tests() -> List[QATestCase]:
        """Get tool management test cases."""
        return [
            QATestCase(
                name="List available tools",
                module=QAModule.TOOLS,
                endpoint="/v1/system/tools",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test listing available tools",
            ),
            # Tools don't have individual info or execute endpoints - removed
        ]

    @staticmethod
    def get_task_tests() -> List[QATestCase]:
        """Get task management test cases."""
        # Tasks API doesn't exist - returning empty list
        return []

    @staticmethod
    def get_guidance_tests() -> List[QATestCase]:
        """Get guidance system test cases."""
        return [
            QATestCase(
                name="Request guidance",
                module=QAModule.GUIDANCE,
                endpoint="/v1/wa/guidance",
                method="POST",
                payload={
                    "topic": "Test guidance request from QA",
                    "context": "Testing the guidance system functionality",
                },
                expected_status=200,
                requires_auth=True,
                description="Test requesting guidance via WA endpoint",
            ),
            QATestCase(
                name="Get deferrals (guidance history)",
                module=QAModule.GUIDANCE,
                endpoint="/v1/wa/deferrals",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting guidance deferrals",
            ),
        ]


import time
