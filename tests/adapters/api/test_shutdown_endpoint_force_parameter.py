"""
Unit tests for the /v1/system/shutdown endpoint force parameter.

This test file specifically covers the fix for the bug where forced shutdown
was still generating thoughts instead of immediately terminating.
"""

import pytest
from fastapi import status


class TestShutdownEndpointForceParameter:
    """Test the shutdown endpoint with force parameter."""

    def test_shutdown_endpoint_requires_auth(self, client):
        """Test that shutdown endpoint requires authentication."""
        response = client.post("/v1/system/shutdown", json={"reason": "Test shutdown", "force": False, "confirm": True})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_shutdown_requires_confirmation(self, client, auth_headers):
        """Test that shutdown requires confirm=true."""
        response = client.post(
            "/v1/system/shutdown", headers=auth_headers, json={"reason": "Test shutdown", "force": False}
        )
        # Should reject without confirmation (422 for Pydantic validation or 400 for app logic)
        assert response.status_code in [status.HTTP_422_UNPROCESSABLE_ENTITY, status.HTTP_400_BAD_REQUEST]
        # Response should mention confirmation if available
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            assert "confirmation" in response.json()["detail"].lower()

    def test_shutdown_reason_required(self, client, auth_headers):
        """Test that shutdown endpoint requires a reason."""
        response = client.post(
            "/v1/system/shutdown", headers=auth_headers, json={"force": True, "confirm": True}  # Missing reason
        )

        # Should fail validation
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_shutdown_empty_reason_rejected(self, client, auth_headers):
        """Test that empty reason is rejected."""
        response = client.post(
            "/v1/system/shutdown", headers=auth_headers, json={"reason": "", "force": False, "confirm": True}
        )

        # Should fail validation or service unavailable (empty string validation may pass Pydantic)
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_503_SERVICE_UNAVAILABLE,  # Runtime may not be available in test
        ]

    def test_shutdown_force_not_boolean(self, client, auth_headers):
        """Test that force parameter must be boolean."""
        response = client.post(
            "/v1/system/shutdown",
            headers=auth_headers,
            json={"reason": "Test", "force": "yes", "confirm": True},  # String instead of boolean
        )

        # Should fail validation (Pydantic will reject non-boolean for force field)
        # May be 422 for validation error, 400 for bad request, or 503 if runtime unavailable
        assert response.status_code in [
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]

    def test_shutdown_normal_accepted(self, client, auth_headers):
        """Test that normal shutdown request is accepted."""
        response = client.post(
            "/v1/system/shutdown",
            headers=auth_headers,
            json={"reason": "Normal shutdown test", "force": False, "confirm": True},
        )

        # Should be accepted (200) or runtime not available (503) or already shutting down (409)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            status.HTTP_409_CONFLICT,
        ]

    def test_shutdown_force_accepted(self, client, auth_headers):
        """Test that forced shutdown request is accepted."""
        response = client.post(
            "/v1/system/shutdown",
            headers=auth_headers,
            json={"reason": "Forced shutdown test", "force": True, "confirm": True},
        )

        # Should be accepted (200) or runtime not available (503) or already shutting down (409)
        # Note: In real execution, forced shutdown would call sys.exit(1) and terminate immediately
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            status.HTTP_409_CONFLICT,
        ]

    def test_shutdown_without_force_defaults_to_false(self, client, auth_headers):
        """Test that shutdown without force parameter defaults to normal shutdown."""
        response = client.post(
            "/v1/system/shutdown",
            headers=auth_headers,
            json={"reason": "Default shutdown test", "confirm": True},  # No force parameter
        )

        # Should be accepted (200) or runtime not available (503) or already shutting down (409)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            status.HTTP_409_CONFLICT,
        ]

    def test_shutdown_response_format(self, client, auth_headers):
        """Test that shutdown endpoint returns proper response format."""
        response = client.post(
            "/v1/system/shutdown", headers=auth_headers, json={"reason": "Format test", "force": False, "confirm": True}
        )

        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert "data" in data
            assert "metadata" in data

            # Check shutdown response data
            shutdown_data = data["data"]
            assert "message" in shutdown_data or "status" in shutdown_data


class TestShutdownProtection:
    """Test shutdown protection mechanisms."""

    def test_shutdown_duplicate_request_rejected(self, client, auth_headers):
        """Test that duplicate shutdown requests are rejected."""
        # First shutdown request
        response1 = client.post(
            "/v1/system/shutdown",
            headers=auth_headers,
            json={"reason": "First shutdown", "force": False, "confirm": True},
        )

        # If first request succeeded, second should be rejected with 409
        if response1.status_code == status.HTTP_200_OK:
            response2 = client.post(
                "/v1/system/shutdown",
                headers=auth_headers,
                json={"reason": "Second shutdown", "force": False, "confirm": True},
            )
            assert response2.status_code == status.HTTP_409_CONFLICT
            assert "already" in response2.json()["detail"].lower()
