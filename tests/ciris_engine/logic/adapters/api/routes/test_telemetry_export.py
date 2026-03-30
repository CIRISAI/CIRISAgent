"""Unit tests for telemetry export destinations CRUD API.

Tests cover:
1. List destinations (empty and populated)
2. Create destination with validation
3. Get single destination
4. Update destination
5. Delete destination
6. Test destination connectivity
7. Error handling for missing config service
8. Duplicate name validation
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import require_admin
from ciris_engine.logic.adapters.api.routes.telemetry_export import router


def override_admin_auth():
    """Override admin authentication dependency."""
    return Mock(user_id="test_admin", role="ADMIN")


@pytest.fixture
def mock_config_service():
    """Create a mock config service with storage."""
    service = MagicMock()
    storage = {"telemetry_export:destinations": []}

    async def mock_get_config(key):
        if key not in storage:
            return None
        mock_node = MagicMock()
        mock_node.value.value = storage.get(key, [])
        return mock_node

    async def mock_set_config(key, value, updated_by):
        storage[key] = value

    service.get_config = mock_get_config
    service.set_config = mock_set_config

    return service


@pytest.fixture
def app_with_config(mock_config_service):
    """Create app with config service."""
    app = FastAPI()
    app.dependency_overrides[require_admin] = override_admin_auth
    app.include_router(router)
    app.state.config_service = mock_config_service
    return app


@pytest.fixture
def app_without_config():
    """Create app without config service."""
    app = FastAPI()
    app.dependency_overrides[require_admin] = override_admin_auth
    app.include_router(router)
    app.state.config_service = None
    return app


@pytest.fixture
def client(app_with_config):
    """Create test client with config service."""
    return TestClient(app_with_config)


@pytest.fixture
def client_no_config(app_without_config):
    """Create test client without config service."""
    return TestClient(app_without_config)


class TestListDestinations:
    """Tests for GET /telemetry/export/destinations."""

    def test_list_empty_destinations(self, client):
        """Test listing destinations when none exist."""
        response = client.get("/telemetry/export/destinations")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["destinations"] == []
        assert data["data"]["total"] == 0

    def test_list_destinations_no_config_service(self, client_no_config):
        """Test error when config service is not available."""
        response = client_no_config.get("/telemetry/export/destinations")
        assert response.status_code == 503
        assert "Config service not available" in response.json()["detail"]


class TestCreateDestination:
    """Tests for POST /telemetry/export/destinations."""

    def test_create_destination_otlp(self, client):
        """Test creating an OTLP destination."""
        destination = {
            "name": "Grafana Cloud",
            "endpoint": "https://otlp.grafana.net/v1",
            "format": "otlp",
            "signals": ["metrics", "traces"],
            "auth_type": "bearer",
            "auth_value": "secret_token",
            "interval_seconds": 60,
            "enabled": True,
        }
        response = client.post("/telemetry/export/destinations", json=destination)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["name"] == "Grafana Cloud"
        assert data["data"]["format"] == "otlp"
        assert "id" in data["data"]
        # Auth value should be redacted
        assert data["data"]["auth_value"] == "***REDACTED***"

    def test_create_destination_prometheus(self, client):
        """Test creating a Prometheus destination."""
        destination = {
            "name": "Local Prometheus",
            "endpoint": "http://localhost:9090",
            "format": "prometheus",
            "signals": ["metrics"],
            "auth_type": "none",
            "interval_seconds": 30,
            "enabled": True,
        }
        response = client.post("/telemetry/export/destinations", json=destination)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["format"] == "prometheus"
        assert data["data"]["signals"] == ["metrics"]

    def test_create_destination_graphite(self, client):
        """Test creating a Graphite destination."""
        destination = {
            "name": "Graphite Server",
            "endpoint": "https://graphite.example.com",
            "format": "graphite",
            "signals": ["metrics"],
            "auth_type": "basic",
            "auth_value": "user:password",
            "interval_seconds": 120,
            "enabled": False,
        }
        response = client.post("/telemetry/export/destinations", json=destination)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["format"] == "graphite"
        assert data["data"]["enabled"] is False

    def test_create_destination_custom_header_auth(self, client):
        """Test creating a destination with custom header auth."""
        destination = {
            "name": "Custom API",
            "endpoint": "https://api.example.com/metrics",
            "format": "otlp",
            "signals": ["metrics", "logs"],
            "auth_type": "header",
            "auth_value": "my-api-key-value",
            "auth_header": "X-API-Key",
            "interval_seconds": 60,
            "enabled": True,
        }
        response = client.post("/telemetry/export/destinations", json=destination)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["auth_type"] == "header"
        assert data["data"]["auth_header"] == "X-API-Key"

    def test_create_destination_invalid_endpoint(self, client):
        """Test validation rejects invalid endpoint URL."""
        destination = {
            "name": "Invalid",
            "endpoint": "not-a-url",
            "format": "otlp",
            "signals": ["metrics"],
        }
        response = client.post("/telemetry/export/destinations", json=destination)
        assert response.status_code == 422  # Validation error

    def test_create_destination_duplicate_name(self, client):
        """Test that duplicate names are rejected."""
        destination = {
            "name": "Unique Name",
            "endpoint": "https://example.com",
            "format": "otlp",
            "signals": ["metrics"],
        }
        # Create first
        response1 = client.post("/telemetry/export/destinations", json=destination)
        assert response1.status_code == 200

        # Try to create duplicate
        response2 = client.post("/telemetry/export/destinations", json=destination)
        assert response2.status_code == 400
        assert "already exists" in response2.json()["detail"]

    def test_create_destination_no_config_service(self, client_no_config):
        """Test error when config service is not available."""
        destination = {
            "name": "Test",
            "endpoint": "https://example.com",
            "format": "otlp",
            "signals": ["metrics"],
        }
        response = client_no_config.post("/telemetry/export/destinations", json=destination)
        assert response.status_code == 503


class TestGetDestination:
    """Tests for GET /telemetry/export/destinations/{destination_id}."""

    def test_get_destination_success(self, client):
        """Test getting a specific destination."""
        # Create first
        destination = {
            "name": "Test Destination",
            "endpoint": "https://example.com",
            "format": "otlp",
            "signals": ["metrics"],
        }
        create_response = client.post("/telemetry/export/destinations", json=destination)
        dest_id = create_response.json()["data"]["id"]

        # Get it
        response = client.get(f"/telemetry/export/destinations/{dest_id}")
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Test Destination"

    def test_get_destination_not_found(self, client):
        """Test 404 for non-existent destination."""
        response = client.get("/telemetry/export/destinations/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestUpdateDestination:
    """Tests for PUT /telemetry/export/destinations/{destination_id}."""

    def test_update_destination_success(self, client):
        """Test updating a destination."""
        # Create first
        destination = {
            "name": "Original Name",
            "endpoint": "https://example.com",
            "format": "otlp",
            "signals": ["metrics"],
            "enabled": True,
        }
        create_response = client.post("/telemetry/export/destinations", json=destination)
        dest_id = create_response.json()["data"]["id"]

        # Update
        update = {"name": "Updated Name", "enabled": False}
        response = client.put(f"/telemetry/export/destinations/{dest_id}", json=update)
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Name"
        assert response.json()["data"]["enabled"] is False

    def test_update_destination_partial(self, client):
        """Test partial update of a destination."""
        # Create first
        destination = {
            "name": "Test",
            "endpoint": "https://example.com",
            "format": "otlp",
            "signals": ["metrics"],
            "interval_seconds": 60,
        }
        create_response = client.post("/telemetry/export/destinations", json=destination)
        dest_id = create_response.json()["data"]["id"]

        # Update only interval
        update = {"interval_seconds": 120}
        response = client.put(f"/telemetry/export/destinations/{dest_id}", json=update)
        assert response.status_code == 200
        assert response.json()["data"]["interval_seconds"] == 120
        assert response.json()["data"]["name"] == "Test"  # Unchanged

    def test_update_destination_not_found(self, client):
        """Test 404 for updating non-existent destination."""
        response = client.put("/telemetry/export/destinations/nonexistent", json={"name": "New Name"})
        assert response.status_code == 404


class TestDeleteDestination:
    """Tests for DELETE /telemetry/export/destinations/{destination_id}."""

    def test_delete_destination_success(self, client):
        """Test deleting a destination."""
        # Create first
        destination = {
            "name": "To Delete",
            "endpoint": "https://example.com",
            "format": "otlp",
            "signals": ["metrics"],
        }
        create_response = client.post("/telemetry/export/destinations", json=destination)
        dest_id = create_response.json()["data"]["id"]

        # Delete
        response = client.delete(f"/telemetry/export/destinations/{dest_id}")
        assert response.status_code == 200
        assert "deleted successfully" in response.json()["data"]["message"]

        # Verify it's gone
        get_response = client.get(f"/telemetry/export/destinations/{dest_id}")
        assert get_response.status_code == 404

    def test_delete_destination_not_found(self, client):
        """Test 404 for deleting non-existent destination."""
        response = client.delete("/telemetry/export/destinations/nonexistent")
        assert response.status_code == 404


class TestTestDestination:
    """Tests for POST /telemetry/export/destinations/{destination_id}/test."""

    def test_test_destination_success(self, client):
        """Test successful connectivity test."""
        # Create first
        destination = {
            "name": "Test Target",
            "endpoint": "https://httpbin.org/status/200",
            "format": "otlp",
            "signals": ["metrics"],
            "auth_type": "none",
        }
        create_response = client.post("/telemetry/export/destinations", json=destination)
        dest_id = create_response.json()["data"]["id"]

        # Mock httpx to avoid actual network call
        with patch("ciris_engine.logic.adapters.api.routes.telemetry_export.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_httpx.AsyncClient.return_value = mock_client

            response = client.post(f"/telemetry/export/destinations/{dest_id}/test")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["success"] is True

    def test_test_destination_not_found(self, client):
        """Test 404 for testing non-existent destination."""
        response = client.post("/telemetry/export/destinations/nonexistent/test")
        assert response.status_code == 404


class TestAuthRedaction:
    """Tests for auth value redaction in responses."""

    def test_auth_value_redacted_in_list(self, client):
        """Test that auth values are redacted in list response."""
        destination = {
            "name": "Secret Dest",
            "endpoint": "https://example.com",
            "format": "otlp",
            "signals": ["metrics"],
            "auth_type": "bearer",
            "auth_value": "super_secret_token_123",
        }
        client.post("/telemetry/export/destinations", json=destination)

        response = client.get("/telemetry/export/destinations")
        assert response.status_code == 200
        dest = response.json()["data"]["destinations"][0]
        assert dest["auth_value"] == "***REDACTED***"

    def test_auth_value_redacted_in_get(self, client):
        """Test that auth values are redacted in get response."""
        destination = {
            "name": "Secret Dest 2",
            "endpoint": "https://example.com",
            "format": "otlp",
            "signals": ["metrics"],
            "auth_type": "basic",
            "auth_value": "user:password",
        }
        create_response = client.post("/telemetry/export/destinations", json=destination)
        dest_id = create_response.json()["data"]["id"]

        response = client.get(f"/telemetry/export/destinations/{dest_id}")
        assert response.status_code == 200
        assert response.json()["data"]["auth_value"] == "***REDACTED***"


class TestInputValidation:
    """Tests for input validation."""

    def test_interval_min_validation(self, client):
        """Test that interval must be >= 10 seconds."""
        destination = {
            "name": "Test",
            "endpoint": "https://example.com",
            "format": "otlp",
            "signals": ["metrics"],
            "interval_seconds": 5,  # Below minimum
        }
        response = client.post("/telemetry/export/destinations", json=destination)
        assert response.status_code == 422

    def test_interval_max_validation(self, client):
        """Test that interval must be <= 3600 seconds."""
        destination = {
            "name": "Test",
            "endpoint": "https://example.com",
            "format": "otlp",
            "signals": ["metrics"],
            "interval_seconds": 7200,  # Above maximum
        }
        response = client.post("/telemetry/export/destinations", json=destination)
        assert response.status_code == 422

    def test_name_max_length_validation(self, client):
        """Test that name must be <= 64 characters."""
        destination = {
            "name": "A" * 100,  # Too long
            "endpoint": "https://example.com",
            "format": "otlp",
            "signals": ["metrics"],
        }
        response = client.post("/telemetry/export/destinations", json=destination)
        assert response.status_code == 422

    def test_empty_name_validation(self, client):
        """Test that name cannot be empty."""
        destination = {
            "name": "",
            "endpoint": "https://example.com",
            "format": "otlp",
            "signals": ["metrics"],
        }
        response = client.post("/telemetry/export/destinations", json=destination)
        assert response.status_code == 422
