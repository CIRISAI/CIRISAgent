"""
Basic authentication tests for API routes.
"""

import pytest
from fastapi import status


class TestAuthBasics:
    """Test basic authentication functionality."""

    def test_no_auth_returns_401(self, client):
        """Test that endpoints without auth return 401."""
        response = client.get("/v1/agent/status")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Missing authorization header" in response.json()["detail"]

    def test_invalid_auth_format_returns_401(self, client):
        """Test that invalid auth format returns 401."""
        response = client.get("/v1/agent/status", headers={"Authorization": "InvalidFormat"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid authorization format" in response.json()["detail"]

    def test_invalid_credentials_returns_401(self, client):
        """Test that invalid credentials return 401."""
        response = client.get("/v1/agent/status", headers={"Authorization": "Bearer invalid:wrong"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid username or password" in response.json()["detail"]

    def test_valid_dev_credentials_accepted(self, client, auth_headers):
        """Test that valid dev credentials are accepted."""
        # The status endpoint might not be fully implemented, but auth should work
        response = client.get("/v1/agent/status", headers=auth_headers)
        # Should not be 401 - might be 200, 501, or 503 depending on implementation
        assert response.status_code != status.HTTP_401_UNAUTHORIZED

    def test_health_endpoint_no_auth(self, client):
        """Test that health endpoint doesn't require auth."""
        response = client.get("/v1/system/health")
        # Health endpoint should work without auth
        assert response.status_code == status.HTTP_200_OK
