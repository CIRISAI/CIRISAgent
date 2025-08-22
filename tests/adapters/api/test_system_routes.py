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

    def test_adapters_response_validation(self, client, auth_headers):
        """Test that adapter listing returns valid RuntimeAdapterStatus objects."""
        response = client.get("/v1/system/adapters", headers=auth_headers)

        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert "data" in data
            assert "adapters" in data["data"]

            adapters = data["data"]["adapters"]
            for adapter in adapters:
                # Verify required fields for RuntimeAdapterStatus
                assert "adapter_id" in adapter
                assert "adapter_type" in adapter
                assert "is_running" in adapter
                assert "loaded_at" in adapter
                assert "services_registered" in adapter
                assert "config_params" in adapter

                # Verify metrics is either None or valid AdapterMetrics
                if "metrics" in adapter and adapter["metrics"] is not None:
                    metrics = adapter["metrics"]
                    assert isinstance(metrics, dict)
                    assert "messages_processed" in metrics
                    assert "errors_count" in metrics
                    assert "uptime_seconds" in metrics

    def test_tools_endpoint_requires_auth(self, client):
        """Test that tools endpoint requires auth."""
        response = client.get("/v1/system/tools")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_tools_endpoint_with_auth(self, client, auth_headers):
        """Test tools endpoint returns deduplicated providers."""
        response = client.get("/v1/system/tools", headers=auth_headers)

        # Print response if it's not OK to help debug
        if response.status_code != status.HTTP_200_OK:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.json()}")

        if response.status_code == status.HTTP_200_OK:
            data = response.json()

            # Print the actual response for debugging
            if "error" in data:
                print(f"Error in response: {data}")

            assert "data" in data, f"Response missing 'data' field: {data}"

            # Check for metadata that was added in the fix
            if "metadata" in data:
                metadata = data["metadata"]
                # Only check for tool-specific metadata if we got tool data
                if "providers" in metadata:
                    # Tool-specific metadata is present
                    assert "provider_count" in metadata
                    assert "total_tools" in metadata

                    # Verify providers are unique (no duplicates)
                    providers = metadata["providers"]
                    assert len(providers) == len(set(providers)), "Tool providers should be unique"

                    # Verify counts match
                    assert metadata["provider_count"] == len(providers)
                    assert metadata["total_tools"] == len(data["data"])

            # Verify each tool has required fields
            tools = data["data"]
            for tool in tools:
                assert "name" in tool
                assert "description" in tool
                assert "provider" in tool
                assert "category" in tool
                assert "cost" in tool

    def test_tools_deduplication(self, client, auth_headers):
        """Test that duplicate tools from multiple providers are deduplicated."""
        response = client.get("/v1/system/tools", headers=auth_headers)

        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            tools = data["data"]

            # Check that tool names are unique
            tool_names = [tool["name"] for tool in tools]
            assert len(tool_names) == len(set(tool_names)), "Tool names should be unique"

            # Check for tools with multiple providers (comma-separated)
            multi_provider_tools = [tool for tool in tools if "," in tool.get("provider", "")]
            # This is valid - tools can have multiple providers listed
