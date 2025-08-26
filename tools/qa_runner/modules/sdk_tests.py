"""
SDK test module for TypeScript/Python SDK validation.
"""

from typing import List

from ..config import QAModule, QATestCase


class SDKTestModule:
    """Test module for SDK operations."""

    @staticmethod
    def get_sdk_tests() -> List[QATestCase]:
        """Get SDK test cases."""
        return [
            # Authentication flow
            QATestCase(
                name="SDK login flow",
                module=QAModule.SDK,
                endpoint="/v1/auth/login",
                method="POST",
                payload={"username": "admin", "password": "ciris_admin_password"},
                expected_status=200,
                requires_auth=False,
                description="Test SDK authentication flow",
            ),
            QATestCase(
                name="SDK token refresh",
                module=QAModule.SDK,
                endpoint="/v1/auth/refresh",
                method="POST",
                payload={"refresh_token": "dummy_refresh_token"},  # Required field
                expected_status=200,
                requires_auth=True,
                description="Test SDK token refresh",
            ),
            # Error handling
            QATestCase(
                name="SDK error response format",
                module=QAModule.SDK,
                endpoint="/v1/nonexistent",
                method="GET",
                expected_status=404,
                requires_auth=True,
                description="Test SDK error response handling",
            ),
            QATestCase(
                name="SDK validation error",
                module=QAModule.SDK,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={},  # Missing required field
                expected_status=422,
                requires_auth=True,
                description="Test SDK validation error handling",
            ),
            # Real endpoints that exist
            QATestCase(
                name="SDK system status",
                module=QAModule.SDK,
                endpoint="/v1/system/health",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test SDK system status call",
            ),
            # Pagination on real endpoint
            QATestCase(
                name="SDK pagination",
                module=QAModule.SDK,
                endpoint="/v1/audit/entries?limit=10",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test SDK pagination support",
            ),
            # Complex data structures
            QATestCase(
                name="SDK nested object handling",
                module=QAModule.SDK,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={
                    "message": "Complex request",
                    "context": {
                        "user": {"id": "123", "preferences": {"language": "en", "timezone": "UTC"}},
                        "metadata": {"source": "sdk_test", "version": "1.0.0"},
                    },
                },
                expected_status=200,
                requires_auth=True,
                description="Test SDK complex object serialization",
            ),
            # WebSocket stream test (real endpoint)
            QATestCase(
                name="SDK agent stream endpoint check",
                module=QAModule.SDK,
                endpoint="/v1/agent/stream",
                method="WEBSOCKET",  # Special method for WebSocket testing
                expected_status=101,  # 101 Switching Protocols for WebSocket
                requires_auth=True,  # WebSocket requires auth in headers
                description="Test SDK WebSocket stream endpoint",
            ),
        ]