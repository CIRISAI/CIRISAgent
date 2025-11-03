"""Comprehensive tests for connector management API endpoints."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.routes import connectors


@pytest.fixture
def client_with_auth(test_db):
    """Create test client with admin authentication."""
    app = create_app()

    # Mock authentication
    from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService, User

    auth_service = APIAuthService()
    admin_user = User(
        wa_id="test_admin",
        name="Test Admin",
        auth_type="password",
        api_role="ADMIN",
        created_at=datetime.now(timezone.utc),
        is_active=True,
    )
    auth_service._users[admin_user.wa_id] = admin_user
    app.state.auth_service = auth_service

    client = TestClient(app)

    # Login and get token
    login_response = client.post("/v1/auth/login", json={"username": "admin", "password": "ciris_admin_password"})
    token = login_response.json()["access_token"]

    client.auth_headers = {"Authorization": f"Bearer {token}"}
    client.app = app

    # Clear connector registry before each test
    connectors._connector_registry.clear()

    yield client


class TestRegisterSQLConnector:
    """Test SQL connector registration."""

    def test_register_sql_connector_success(self, client_with_auth):
        """Test successful SQL connector registration."""
        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Test Postgres DB",
                "database_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "test_db",
                "username": "test_user",
                "password": "test_password",
                "ssl_enabled": True,
            },
        }

        response = client_with_auth.post(
            "/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["connector_id"].startswith("sql_postgres_")
        assert data["data"]["connector_type"] == "sql"
        assert data["data"]["connector_name"] == "Test Postgres DB"
        assert data["data"]["status"] == "registered"

    def test_register_sql_connector_missing_fields_fails(self, client_with_auth):
        """Test that missing required fields are rejected."""
        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Incomplete DB",
                "database_type": "postgres",
                # Missing host, port, database, username, password
            },
        }

        response = client_with_auth.post(
            "/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_sql_connector_invalid_database_type_fails(self, client_with_auth):
        """Test that invalid database type is rejected."""
        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Invalid DB",
                "database_type": "mongodb",  # Not a valid SQL type
                "host": "localhost",
                "port": 27017,
                "database": "test",
                "username": "user",
                "password": "pass",
            },
        }

        response = client_with_auth.post(
            "/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_sql_connector_requires_admin(self, client_with_auth):
        """Test that connector registration requires admin privileges."""
        # Create non-admin user
        from ciris_engine.logic.adapters.api.services.auth_service import User

        observer_user = User(
            wa_id="test_observer",
            name="Test Observer",
            auth_type="password",
            api_role="OBSERVER",
            created_at=datetime.now(timezone.utc),
            is_active=True,
        )
        client_with_auth.app.state.auth_service._users[observer_user.wa_id] = observer_user

        # Login as observer
        login_response = client_with_auth.post(
            "/v1/auth/login", json={"username": "observer", "password": "observer_password"}
        )
        observer_token = login_response.json()["access_token"]
        observer_headers = {"Authorization": f"Bearer {observer_token}"}

        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Test DB",
                "database_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "test",
                "username": "user",
                "password": "pass",
            },
        }

        response = client_with_auth.post("/v1/connectors/sql", json=request_data, headers=observer_headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_register_non_sql_connector_via_sql_endpoint_fails(self, client_with_auth):
        """Test that non-SQL connectors are rejected at SQL endpoint."""
        request_data = {
            "connector_type": "rest",  # Should use /connectors, not /connectors/sql
            "config": {"connector_name": "REST API", "base_url": "https://api.example.com"},
        }

        response = client_with_auth.post(
            "/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestListConnectors:
    """Test listing connectors."""

    def test_list_empty_connectors(self, client_with_auth):
        """Test listing when no connectors are registered."""
        response = client_with_auth.get("/v1/connectors/", headers=client_with_auth.auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["total"] == 0
        assert data["data"]["connectors"] == []

    def test_list_connectors_after_registration(self, client_with_auth):
        """Test listing connectors after registering some."""
        # Register 2 connectors
        for i in range(2):
            request_data = {
                "connector_type": "sql",
                "config": {
                    "connector_name": f"Test DB {i+1}",
                    "database_type": "postgres",
                    "host": f"db{i+1}.example.com",
                    "port": 5432,
                    "database": f"db{i+1}",
                    "username": "user",
                    "password": "pass",
                },
            }
            client_with_auth.post("/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers)

        # List all
        response = client_with_auth.get("/v1/connectors/", headers=client_with_auth.auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["total"] == 2
        assert len(data["data"]["connectors"]) == 2

    def test_list_connectors_filtered_by_type(self, client_with_auth):
        """Test listing connectors filtered by type."""
        # Register SQL connector
        sql_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "SQL DB",
                "database_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "db",
                "username": "user",
                "password": "pass",
            },
        }
        client_with_auth.post("/v1/connectors/sql", json=sql_data, headers=client_with_auth.auth_headers)

        # List filtered by SQL
        response = client_with_auth.get("/v1/connectors/?connector_type=sql", headers=client_with_auth.auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["total"] == 1
        assert data["data"]["connectors"][0]["connector_type"] == "sql"

    def test_list_connectors_requires_admin(self, client_with_auth):
        """Test that listing requires admin privileges."""
        # Try without auth
        response = client_with_auth.get("/v1/connectors/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestTestConnector:
    """Test connector testing endpoint."""

    def test_test_connector_success(self, client_with_auth):
        """Test testing a connector."""
        # Register connector first
        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Test DB",
                "database_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "db",
                "username": "user",
                "password": "pass",
            },
        }
        register_response = client_with_auth.post(
            "/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers
        )
        connector_id = register_response.json()["data"]["connector_id"]

        # Test connector
        test_response = client_with_auth.post(
            f"/v1/connectors/{connector_id}/test", headers=client_with_auth.auth_headers
        )

        assert test_response.status_code == status.HTTP_200_OK
        data = test_response.json()
        # Will be success because we're simulating
        assert data["data"]["connector_id"] == connector_id
        assert "message" in data["data"]
        assert "latency_ms" in data["data"]

    def test_test_nonexistent_connector_fails(self, client_with_auth):
        """Test testing non-existent connector."""
        response = client_with_auth.post(
            "/v1/connectors/nonexistent/test", headers=client_with_auth.auth_headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestUpdateConnector:
    """Test connector update endpoint."""

    def test_update_connector_config(self, client_with_auth):
        """Test updating connector configuration."""
        # Register connector
        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Test DB",
                "database_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "db",
                "username": "user",
                "password": "pass",
            },
        }
        register_response = client_with_auth.post(
            "/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers
        )
        connector_id = register_response.json()["data"]["connector_id"]

        # Update config
        update_data = {"config": {"host": "newhost.example.com", "port": 5433}}

        update_response = client_with_auth.patch(
            f"/v1/connectors/{connector_id}", json=update_data, headers=client_with_auth.auth_headers
        )

        assert update_response.status_code == status.HTTP_200_OK
        data = update_response.json()
        assert data["success"] is True
        assert data["data"]["connector_id"] == connector_id

    def test_update_connector_enable_disable(self, client_with_auth):
        """Test enabling/disabling connector."""
        # Register connector
        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Test DB",
                "database_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "db",
                "username": "user",
                "password": "pass",
            },
        }
        register_response = client_with_auth.post(
            "/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers
        )
        connector_id = register_response.json()["data"]["connector_id"]

        # Disable
        update_response = client_with_auth.patch(
            f"/v1/connectors/{connector_id}", json={"enabled": False}, headers=client_with_auth.auth_headers
        )

        assert update_response.status_code == status.HTTP_200_OK
        data = update_response.json()
        assert data["data"]["enabled"] is False
        assert data["data"]["status"] == "disabled"

    def test_update_nonexistent_connector_fails(self, client_with_auth):
        """Test updating non-existent connector."""
        update_data = {"config": {"host": "newhost.example.com"}}

        response = client_with_auth.patch(
            "/v1/connectors/nonexistent", json=update_data, headers=client_with_auth.auth_headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDeleteConnector:
    """Test connector deletion endpoint."""

    def test_delete_connector_success(self, client_with_auth):
        """Test successful connector deletion."""
        # Register connector
        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Test DB",
                "database_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "db",
                "username": "user",
                "password": "pass",
            },
        }
        register_response = client_with_auth.post(
            "/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers
        )
        connector_id = register_response.json()["data"]["connector_id"]

        # Delete
        delete_response = client_with_auth.delete(
            f"/v1/connectors/{connector_id}", headers=client_with_auth.auth_headers
        )

        assert delete_response.status_code == status.HTTP_200_OK
        data = delete_response.json()
        assert data["success"] is True
        assert data["data"]["connector_id"] == connector_id

        # Verify deleted
        list_response = client_with_auth.get("/v1/connectors/", headers=client_with_auth.auth_headers)
        assert list_response.json()["data"]["total"] == 0

    def test_delete_nonexistent_connector_fails(self, client_with_auth):
        """Test deleting non-existent connector."""
        response = client_with_auth.delete("/v1/connectors/nonexistent", headers=client_with_auth.auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_requires_admin(self, client_with_auth):
        """Test that deletion requires admin privileges."""
        # Try without proper auth
        response = client_with_auth.delete("/v1/connectors/some_id")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestConnectorIntegration:
    """Integration tests for connector management flow."""

    def test_complete_connector_lifecycle(self, client_with_auth):
        """Test complete connector lifecycle: register, list, test, update, delete."""
        # 1. Register
        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Lifecycle Test DB",
                "database_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "test_db",
                "username": "test_user",
                "password": "test_password",
            },
        }
        register_response = client_with_auth.post(
            "/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers
        )
        assert register_response.status_code == status.HTTP_200_OK
        connector_id = register_response.json()["data"]["connector_id"]

        # 2. List
        list_response = client_with_auth.get("/v1/connectors/", headers=client_with_auth.auth_headers)
        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.json()["data"]["total"] == 1

        # 3. Test
        test_response = client_with_auth.post(
            f"/v1/connectors/{connector_id}/test", headers=client_with_auth.auth_headers
        )
        assert test_response.status_code == status.HTTP_200_OK

        # 4. Update
        update_response = client_with_auth.patch(
            f"/v1/connectors/{connector_id}",
            json={"config": {"port": 5433}},
            headers=client_with_auth.auth_headers,
        )
        assert update_response.status_code == status.HTTP_200_OK

        # 5. Delete
        delete_response = client_with_auth.delete(
            f"/v1/connectors/{connector_id}", headers=client_with_auth.auth_headers
        )
        assert delete_response.status_code == status.HTTP_200_OK

        # 6. Verify deleted
        list_response = client_with_auth.get("/v1/connectors/", headers=client_with_auth.auth_headers)
        assert list_response.json()["data"]["total"] == 0
