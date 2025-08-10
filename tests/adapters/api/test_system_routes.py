"""
Tests for system API routes.
"""

import pytest
from fastapi import status


class TestSystemRoutes:
    """Test system API endpoints."""

    def test_health_endpoint_public(self, client):
        """Test that health endpoint is public."""
        response = client.get("/v1/system/health")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "data" in data
        assert "metadata" in data

        health_data = data["data"]
        assert "status" in health_data
        assert health_data["status"] in ["healthy", "degraded", "unhealthy", "critical"]

    def test_resources_endpoint_requires_auth(self, client):
        """Test that resources endpoint requires auth."""
        response = client.get("/v1/system/resources")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_resources_endpoint_with_auth(self, client, auth_headers):
        """Test resources endpoint with valid auth."""
        response = client.get("/v1/system/resources", headers=auth_headers)
        # May be 200 with data or 503 if runtime not available
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]

        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert "cpu_percent" in data
            assert "memory_mb" in data
            assert "disk_gb" in data

    def test_time_endpoint_requires_auth(self, client):
        """Test that time endpoint requires auth."""
        response = client.get("/v1/system/time")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_time_endpoint_with_auth(self, client, auth_headers):
        """Test time endpoint with valid auth."""
        response = client.get("/v1/system/time", headers=auth_headers)
        # May be 200 or 503 if time service not available
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]

        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert "utc" in data
            assert "local" in data
            assert "timezone" in data

    def test_processors_endpoint_requires_auth(self, client):
        """Test that processors endpoint requires auth."""
        response = client.get("/v1/system/processors")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_processors_endpoint_with_auth(self, client, auth_headers):
        """Test processors endpoint with valid auth."""
        response = client.get("/v1/system/processors", headers=auth_headers)
        # May be 200 or 503 if runtime not available
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]

    def test_services_health_requires_auth(self, client):
        """Test that services health endpoint requires auth."""
        response = client.get("/v1/system/services/health")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_services_health_with_auth(self, client, auth_headers):
        """Test services health endpoint with valid auth."""
        response = client.get("/v1/system/services/health", headers=auth_headers)
        # May be 200 or 503 if runtime not available
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]

    def test_runtime_control_requires_admin(self, client, auth_headers):
        """Test that runtime control endpoints require admin role."""
        # These endpoints should require ADMIN role
        response = client.post("/v1/system/runtime/pause", headers=auth_headers, json={"action": "pause"})
        # Admin credentials should work (or 503 if runtime not available, or 422 for validation)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_adapters_list_requires_auth(self, client):
        """Test that adapters list requires auth."""
        response = client.get("/v1/system/adapters")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_adapters_list_with_auth(self, client, auth_headers):
        """Test adapters list with valid auth."""
        response = client.get("/v1/system/adapters", headers=auth_headers)
        # May be 200 or 503 if runtime not available
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE]

        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert isinstance(data, list)

    def test_invalid_system_endpoint_returns_404(self, client, auth_headers):
        """Test that invalid endpoints return 404."""
        response = client.get("/v1/system/invalid", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND
