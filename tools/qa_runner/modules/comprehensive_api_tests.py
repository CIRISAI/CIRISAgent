"""
Comprehensive API test module with extended coverage.
"""

from typing import List

from ..config import QAModule, QATestCase


class ComprehensiveAPITestModule:
    """Extended API test coverage for all endpoints."""

    @staticmethod
    def get_extended_system_tests() -> List[QATestCase]:
        """Get extended system management tests."""
        return [
            # Processor state tests  
            QATestCase(
                name="Get processor states",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/processors",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting available processor cognitive states",
            ),
            # Service management
            QATestCase(
                name="Get service health",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/services/health",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting detailed service health",
            ),
            QATestCase(
                name="Restart service",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/services/restart",
                method="POST",
                payload={"service_name": "telemetry"},
                expected_status=200,
                requires_auth=True,
                description="Test restarting a specific service",
            ),
            # Circuit breaker management (actual endpoint from system_extensions.py)
            QATestCase(
                name="Reset circuit breaker",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/services/circuit-breakers/reset",
                method="POST",
                payload={"provider_name": "memory"},
                expected_status=200,
                requires_auth=True,
                description="Test resetting a circuit breaker",
            ),
            # Processing queue management
            QATestCase(
                name="Get queue details",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/queue",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting processing queue status",
            ),
            QATestCase(
                name="Single step processing",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step",
                method="POST",
                payload={"step_type": "single"},
                expected_status=200,
                requires_auth=True,
                description="Test single step processing execution",
            ),
        ]

    @staticmethod
    def get_extended_telemetry_tests() -> List[QATestCase]:
        """Get extended telemetry tests."""
        return [
            QATestCase(
                name="Get telemetry overview",
                module=QAModule.TELEMETRY,
                endpoint="/v1/telemetry/overview",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting telemetry system overview",
            ),
            QATestCase(
                name="Get resource telemetry",
                module=QAModule.TELEMETRY,
                endpoint="/v1/telemetry/resources",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting resource telemetry data",
            ),
            QATestCase(
                name="Get metrics",
                module=QAModule.TELEMETRY,
                endpoint="/v1/telemetry/metrics",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting system metrics",
            ),
            QATestCase(
                name="Get traces",
                module=QAModule.TELEMETRY,
                endpoint="/v1/telemetry/traces",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting trace data",
            ),
            QATestCase(
                name="Query telemetry data",
                module=QAModule.TELEMETRY,
                endpoint="/v1/telemetry/query",
                method="POST",
                payload={"metric": "cpu_usage", "time_range": "1h"},
                expected_status=200,
                requires_auth=True,
                description="Test querying telemetry data",
            ),
        ]

    @staticmethod
    def get_extended_memory_tests() -> List[QATestCase]:
        """Get extended memory operation tests."""
        return [
            QATestCase(
                name="Get memory graph",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/graph",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting memory graph structure",
            ),
            QATestCase(
                name="Get memory nodes",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/nodes",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test listing memory nodes",
            ),
            QATestCase(
                name="Get specific node",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/nodes/{node_id}",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting specific memory node",
            ),
            QATestCase(
                name="Delete memory node",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/nodes/{node_id}",
                method="DELETE",
                expected_status=200,
                requires_auth=True,
                description="Test deleting memory node",
            ),
            QATestCase(
                name="Get memory relationships",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/relationships",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting memory relationships",
            ),
            QATestCase(
                name="Create relationship",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/relationships",
                method="POST",
                payload={"source_id": "node1", "target_id": "node2", "relationship_type": "RELATES_TO"},
                expected_status=200,
                requires_auth=True,
                description="Test creating memory relationship",
            ),
            QATestCase(
                name="Memory consolidation",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/consolidate",
                method="POST",
                expected_status=200,
                requires_auth=True,
                description="Test memory consolidation process",
            ),
        ]

    @staticmethod
    def get_extended_agent_tests() -> List[QATestCase]:
        """Get extended agent interaction tests."""
        return [
            QATestCase(
                name="Agent streaming",
                module=QAModule.AGENT,
                endpoint="/v1/agent/stream",
                method="POST",
                payload={"message": "Tell me about yourself", "stream": True},
                expected_status=200,
                requires_auth=True,
                description="Test agent streaming response",
            ),
            QATestCase(
                name="Agent context",
                module=QAModule.AGENT,
                endpoint="/v1/agent/context",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting agent context",
            ),
            QATestCase(
                name="Update agent context",
                module=QAModule.AGENT,
                endpoint="/v1/agent/context",
                method="PUT",
                payload={"context": {"user_preferences": {"language": "en", "verbosity": "high"}}},
                expected_status=200,
                requires_auth=True,
                description="Test updating agent context",
            ),
            QATestCase(
                name="Agent capabilities",
                module=QAModule.AGENT,
                endpoint="/v1/agent/capabilities",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting agent capabilities",
            ),
            QATestCase(
                name="Agent reasoning",
                module=QAModule.AGENT,
                endpoint="/v1/agent/reason",
                method="POST",
                payload={"query": "What should I do if the system is slow?", "context": {"system_load": 0.8}},
                expected_status=200,
                requires_auth=True,
                description="Test agent reasoning endpoint",
            ),
        ]

    @staticmethod
    def get_extended_audit_tests() -> List[QATestCase]:
        """Get extended audit tests."""
        return [
            QATestCase(
                name="Get audit event details",
                module=QAModule.AUDIT,
                endpoint="/v1/audit/events/{event_id}",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting specific audit event",
            ),
            QATestCase(
                name="Query audit events",
                module=QAModule.AUDIT,
                endpoint="/v1/audit/query",
                method="POST",
                payload={
                    "start_time": "2024-01-01T00:00:00Z",
                    "end_time": "2024-12-31T23:59:59Z",
                    "event_types": ["LOGIN", "ACTION"],
                    "limit": 100,
                },
                expected_status=200,
                requires_auth=True,
                description="Test querying audit events",
            ),
            QATestCase(
                name="Export audit log",
                module=QAModule.AUDIT,
                endpoint="/v1/audit/export",
                method="POST",
                payload={"format": "json", "include_signatures": True},
                expected_status=200,
                requires_auth=True,
                description="Test exporting audit log",
            ),
            QATestCase(
                name="Get audit statistics",
                module=QAModule.AUDIT,
                endpoint="/v1/audit/stats",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting audit statistics",
            ),
            QATestCase(
                name="Verify entry range",
                module=QAModule.AUDIT,
                endpoint="/v1/audit/verify/range",
                method="POST",
                payload={"start_id": 1, "end_id": 100},
                expected_status=200,
                requires_auth=True,
                description="Test verifying audit entry range",
            ),
        ]

    @staticmethod
    def get_extended_tools_tests() -> List[QATestCase]:
        """Get extended tool management tests."""
        return [
            QATestCase(
                name="Get tool schema",
                module=QAModule.TOOLS,
                endpoint="/v1/tools/{tool_name}/schema",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting tool schema",
            ),
            QATestCase(
                name="Validate tool parameters",
                module=QAModule.TOOLS,
                endpoint="/v1/tools/validate",
                method="POST",
                payload={"tool_name": "list_files", "parameters": {"path": "/tmp"}},
                expected_status=200,
                requires_auth=True,
                description="Test validating tool parameters",
            ),
            QATestCase(
                name="Get tool execution history",
                module=QAModule.TOOLS,
                endpoint="/v1/tools/history",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting tool execution history",
            ),
            QATestCase(
                name="Cancel tool execution",
                module=QAModule.TOOLS,
                endpoint="/v1/tools/executions/{execution_id}/cancel",
                method="POST",
                expected_status=200,
                requires_auth=True,
                description="Test canceling tool execution",
            ),
            QATestCase(
                name="Get tool metrics",
                module=QAModule.TOOLS,
                endpoint="/v1/tools/metrics",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting tool usage metrics",
            ),
        ]

    @staticmethod
    def get_extended_auth_tests() -> List[QATestCase]:
        """Get extended authentication tests."""
        return [
            QATestCase(
                name="Refresh token",
                module=QAModule.AUTH,
                endpoint="/v1/auth/refresh",
                method="POST",
                expected_status=200,
                requires_auth=True,
                description="Test token refresh",
            ),
            QATestCase(
                name="Logout",
                module=QAModule.AUTH,
                endpoint="/v1/auth/logout",
                method="POST",
                expected_status=200,
                requires_auth=True,
                description="Test logout endpoint",
            ),
            QATestCase(
                name="Change password",
                module=QAModule.AUTH,
                endpoint="/v1/users/admin/password",
                method="PUT",
                payload={"current_password": "ciris_admin_password", "new_password": "new_secure_password"},
                expected_status=200,
                requires_auth=True,
                description="Test password change",
            ),
            QATestCase(
                name="Restore original password",
                module=QAModule.AUTH,
                endpoint="/v1/users/admin/password",
                method="PUT",
                payload={"current_password": "new_secure_password", "new_password": "ciris_admin_password"},
                expected_status=200,
                requires_auth=True,
                description="Restore admin password to original value",
            ),
            QATestCase(
                name="Create user",
                module=QAModule.AUTH,
                endpoint="/v1/auth/users",
                method="POST",
                payload={"username": "test_user", "password": "test_password", "role": "OBSERVER"},
                expected_status=200,
                requires_auth=True,
                description="Test user creation",
            ),
            QATestCase(
                name="Delete user",
                module=QAModule.AUTH,
                endpoint="/v1/auth/users/{user_id}",
                method="DELETE",
                expected_status=200,
                requires_auth=True,
                description="Test user deletion",
            ),
            QATestCase(
                name="Get user permissions",
                module=QAModule.AUTH,
                endpoint="/v1/auth/permissions",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting user permissions",
            ),
        ]

    @staticmethod
    def get_emergency_tests() -> List[QATestCase]:
        """Get emergency endpoint tests."""
        return [
            QATestCase(
                name="Emergency status",
                module=QAModule.SYSTEM,
                endpoint="/v1/emergency/status",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting emergency system status",
            ),
            QATestCase(
                name="Trigger emergency mode",
                module=QAModule.SYSTEM,
                endpoint="/v1/emergency/activate",
                method="POST",
                payload={"reason": "Testing emergency mode"},
                expected_status=200,
                requires_auth=True,
                description="Test activating emergency mode",
            ),
            QATestCase(
                name="Deactivate emergency mode",
                module=QAModule.SYSTEM,
                endpoint="/v1/emergency/deactivate",
                method="POST",
                expected_status=200,
                requires_auth=True,
                description="Test deactivating emergency mode",
            ),
        ]

    @staticmethod
    def get_websocket_tests() -> List[QATestCase]:
        """Get WebSocket endpoint tests."""
        return [
            QATestCase(
                name="WebSocket connection",
                module=QAModule.AGENT,
                endpoint="/v1/ws",
                method="GET",
                expected_status=101,  # WebSocket upgrade
                requires_auth=True,
                description="Test WebSocket connection upgrade",
                timeout=10,
            ),
            QATestCase(
                name="WebSocket events",
                module=QAModule.AGENT,
                endpoint="/v1/ws/events",
                method="GET",
                expected_status=101,
                requires_auth=True,
                description="Test WebSocket event stream",
                timeout=10,
            ),
        ]

    @staticmethod
    def get_all_extended_tests() -> List[QATestCase]:
        """Get all extended API tests."""
        tests = []
        tests.extend(ComprehensiveAPITestModule.get_extended_system_tests())
        tests.extend(ComprehensiveAPITestModule.get_extended_telemetry_tests())
        tests.extend(ComprehensiveAPITestModule.get_extended_memory_tests())
        tests.extend(ComprehensiveAPITestModule.get_extended_agent_tests())
        tests.extend(ComprehensiveAPITestModule.get_extended_audit_tests())
        tests.extend(ComprehensiveAPITestModule.get_extended_tools_tests())
        tests.extend(ComprehensiveAPITestModule.get_extended_auth_tests())
        tests.extend(ComprehensiveAPITestModule.get_emergency_tests())
        tests.extend(ComprehensiveAPITestModule.get_websocket_tests())
        return tests
