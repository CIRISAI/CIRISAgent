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
            QATestCase(
                name="Clear history",
                module=QAModule.AGENT,
                endpoint="/v1/agent/history/clear",
                method="POST",
                expected_status=200,
                requires_auth=True,
                description="Test clearing interaction history",
            ),
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
                        "content": "Test memory entry from QA",
                        "metadata": {"source": "qa_test", "tags": ["test", "qa"]},
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
            QATestCase(
                name="Get tool info",
                module=QAModule.TOOLS,
                endpoint="/v1/tools/list_files",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting specific tool information",
            ),
            QATestCase(
                name="Execute tool",
                module=QAModule.TOOLS,
                endpoint="/v1/tools/execute",
                method="POST",
                payload={"tool_name": "list_files", "parameters": {"path": "."}},
                expected_status=200,
                requires_auth=True,
                description="Test tool execution",
            ),
        ]

    @staticmethod
    def get_task_tests() -> List[QATestCase]:
        """Get task management test cases."""
        return [
            QATestCase(
                name="List tasks",
                module=QAModule.TASKS,
                endpoint="/v1/tasks",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test listing tasks",
            ),
            QATestCase(
                name="Create task",
                module=QAModule.TASKS,
                endpoint="/v1/tasks",
                method="POST",
                payload={"description": "Test task from QA", "priority": 5, "tags": ["test", "qa"]},
                expected_status=200,
                requires_auth=True,
                description="Test creating a new task",
            ),
            QATestCase(
                name="Get task details",
                module=QAModule.TASKS,
                endpoint="/v1/tasks/latest",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting task details",
            ),
        ]

    @staticmethod
    def get_guidance_tests() -> List[QATestCase]:
        """Get guidance system test cases."""
        return [
            QATestCase(
                name="Request guidance",
                module=QAModule.GUIDANCE,
                endpoint="/v1/guidance/request",
                method="POST",
                payload={
                    "thought_id": "test-thought-" + str(time.time()),
                    "context": {"situation": "test", "question": "Should I proceed?"},
                },
                expected_status=200,
                requires_auth=True,
                description="Test requesting guidance",
            ),
            QATestCase(
                name="Get guidance history",
                module=QAModule.GUIDANCE,
                endpoint="/v1/guidance/history",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting guidance history",
            ),
        ]


import time
