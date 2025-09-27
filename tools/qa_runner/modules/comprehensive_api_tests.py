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
            QATestCase(
                name="Get service health",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/services/health",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting detailed service health",
            ),
            # Note: Service restart may not be implemented - skipping
            # Note: Circuit breaker reset may require specific conditions - skipping for now
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
                payload={"query_type": "metric", "metric": "cpu_usage", "time_range": "1h"},
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
                name="Get memory stats",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/stats",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting memory statistics",
            ),
            QATestCase(
                name="Get memory timeline",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/timeline",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting memory timeline",
            ),
            QATestCase(
                name="Query memory",
                module=QAModule.MEMORY,
                endpoint="/v1/memory/query",
                method="POST",
                payload={"query": "test query", "limit": 10},
                expected_status=200,
                requires_auth=True,
                description="Test querying memory nodes",
            ),
            # Note: Memory management happens internally via agent processing - no direct API manipulation
        ]

    @staticmethod
    def get_extended_agent_tests() -> List[QATestCase]:
        """Get extended agent interaction tests."""
        return [
            QATestCase(
                name="Agent status",
                module=QAModule.AGENT,
                endpoint="/v1/agent/status",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting agent status",
            ),
            QATestCase(
                name="Agent identity",
                module=QAModule.AGENT,
                endpoint="/v1/agent/identity",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting agent identity information",
            ),
            QATestCase(
                name="Agent channels",
                module=QAModule.AGENT,
                endpoint="/v1/agent/channels",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting agent communication channels",
            ),
            QATestCase(
                name="Agent reasoning stream",
                module=QAModule.AGENT,
                endpoint="/v1/system/runtime/reasoning-stream",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test agent reasoning stream endpoint",
            ),
        ]

    @staticmethod
    def get_extended_audit_tests() -> List[QATestCase]:
        """Get extended audit tests."""
        return [
            # Note: Get specific audit entry requires real entry_id - skipping generic test
            QATestCase(
                name="Search audit entries",
                module=QAModule.AUDIT,
                endpoint="/v1/audit/search",
                method="POST",
                payload={"search_text": "test", "limit": 100},
                expected_status=200,
                requires_auth=True,
                description="Test searching audit entries",
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
                name="Query audit entries",
                module=QAModule.AUDIT,
                endpoint="/v1/audit/entries",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test querying audit entries with filters",
            ),
            # Note: Verify audit entry requires real entry_id - skipping generic test
        ]

    @staticmethod
    def get_extended_tools_tests() -> List[QATestCase]:
        """Get extended tool management tests."""
        return [
            QATestCase(
                name="Get available tools",
                module=QAModule.TOOLS,
                endpoint="/v1/system/tools",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting list of all available tools",
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
                payload={"refresh_token": "dummy_token"},
                expected_status=200,
                requires_auth=True,
                description="Test token refresh",
            ),
            QATestCase(
                name="Logout",
                module=QAModule.AUTH,
                endpoint="/v1/auth/logout",
                method="POST",
                expected_status=204,  # Logout returns 204 No Content
                requires_auth=True,
                description="Test logout endpoint",
            ),
            QATestCase(
                name="Get current user",
                module=QAModule.AUTH,
                endpoint="/v1/auth/me",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting current user information",
            ),
            # Note: OAuth provider endpoints require SYSTEM_ADMIN permissions, not just ADMIN
        ]

    @staticmethod
    def get_emergency_tests() -> List[QATestCase]:
        """Get emergency endpoint tests."""
        return [
            QATestCase(
                name="Emergency test endpoint",
                module=QAModule.SYSTEM,
                endpoint="/emergency/test",
                method="GET",
                expected_status=200,
                requires_auth=False,
                description="Test emergency system test endpoint",
            ),
            # Note: Emergency shutdown requires cryptographic signature - skipping in basic tests
        ]

    @staticmethod
    def get_websocket_tests() -> List[QATestCase]:
        """Get WebSocket endpoint tests - currently disabled as WebSocket endpoints are not REST endpoints."""
        return []  # WebSocket endpoints don't work with regular HTTP testing

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
        # Skip WebSocket tests - they don't work with HTTP testing
        # tests.extend(ComprehensiveAPITestModule.get_websocket_tests())
        return tests
