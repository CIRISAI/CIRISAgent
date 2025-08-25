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
                expected_status=200,
                requires_auth=True,
                description="Test SDK token refresh",
            ),
            # Batch operations
            QATestCase(
                name="SDK batch request",
                module=QAModule.SDK,
                endpoint="/v1/batch",
                method="POST",
                payload={
                    "requests": [
                        {"method": "GET", "endpoint": "/v1/system/status"},
                        {"method": "GET", "endpoint": "/v1/telemetry/unified"},
                        {"method": "GET", "endpoint": "/v1/agent/status"},
                    ]
                },
                expected_status=200,
                requires_auth=True,
                description="Test SDK batch operations",
            ),
            # Streaming operations
            QATestCase(
                name="SDK WebSocket connection",
                module=QAModule.SDK,
                endpoint="/v1/ws",
                method="GET",
                expected_status=101,  # WebSocket upgrade
                requires_auth=True,
                description="Test SDK WebSocket support",
                timeout=10,
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
            # Rate limiting
            QATestCase(
                name="SDK rate limit headers",
                module=QAModule.SDK,
                endpoint="/v1/system/status",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test SDK rate limit header parsing",
            ),
            # Pagination
            QATestCase(
                name="SDK pagination",
                module=QAModule.SDK,
                endpoint="/v1/audit/events?limit=10&offset=0",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test SDK pagination support",
            ),
            # File operations
            QATestCase(
                name="SDK file upload",
                module=QAModule.SDK,
                endpoint="/v1/files/upload",
                method="POST",
                payload={
                    "filename": "test.txt",
                    "content": "VGVzdCBmaWxlIGNvbnRlbnQ=",  # Base64 encoded
                    "mime_type": "text/plain",
                },
                expected_status=200,
                requires_auth=True,
                description="Test SDK file upload",
            ),
            QATestCase(
                name="SDK file download",
                module=QAModule.SDK,
                endpoint="/v1/files/download/test.txt",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test SDK file download",
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
            # Async operations
            QATestCase(
                name="SDK async task submission",
                module=QAModule.SDK,
                endpoint="/v1/tasks/async",
                method="POST",
                payload={
                    "task": "process_data",
                    "async": True,
                    "callback": {
                        "url": "http://localhost:8000/callback",
                        "method": "POST",
                        "headers": {"X-Callback-Token": "test123"},
                    },
                },
                expected_status=202,
                requires_auth=True,
                description="Test SDK async task handling",
            ),
            QATestCase(
                name="SDK async task status",
                module=QAModule.SDK,
                endpoint="/v1/tasks/async/status/test-task-id",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test SDK async task status polling",
            ),
        ]
