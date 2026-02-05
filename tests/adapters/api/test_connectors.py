"""Comprehensive tests for connector management API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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

        response = client_with_auth.post("/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers)

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

        response = client_with_auth.post("/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers)

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

        response = client_with_auth.post("/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_sql_connector_requires_admin(self, client_with_auth):
        """Test that connector registration requires admin privileges."""
        # Try to register without auth (should get 401)
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

        # Test without authentication
        response = client_with_auth.post("/v1/connectors/sql", json=request_data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_register_non_sql_connector_via_sql_endpoint_fails(self, client_with_auth):
        """Test that non-SQL connectors are rejected at SQL endpoint."""
        request_data = {
            "connector_type": "rest",  # Should use /connectors, not /connectors/sql
            "config": {"connector_name": "REST API", "base_url": "https://api.example.com"},
        }

        response = client_with_auth.post("/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers)

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
        response = client_with_auth.post("/v1/connectors/nonexistent/test", headers=client_with_auth.auth_headers)

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


class TestValidationHelpers:
    """Test validation helper functions directly."""

    def test_validate_rest_config_success(self):
        """Test valid REST config passes validation."""
        config = {"connector_name": "My API", "base_url": "https://api.example.com", "auth_type": "bearer"}
        # Should not raise
        connectors._validate_rest_config(config)

    def test_validate_rest_config_missing_fields(self):
        """Test REST config with missing fields raises HTTPException."""
        config = {"connector_name": "My API"}
        with pytest.raises(Exception) as exc_info:
            connectors._validate_rest_config(config)
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    def test_validate_rest_config_invalid_auth_type(self):
        """Test REST config with invalid auth type raises HTTPException."""
        config = {"connector_name": "My API", "base_url": "https://api.example.com", "auth_type": "kerberos"}
        with pytest.raises(Exception) as exc_info:
            connectors._validate_rest_config(config)
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    def test_validate_sql_config_success(self):
        """Test valid SQL config passes validation."""
        config = {
            "connector_name": "DB",
            "database_type": "postgres",
            "host": "localhost",
            "port": 5432,
            "database": "db",
            "username": "user",
            "password": "pass",
        }
        # Should not raise
        connectors._validate_sql_config(config)


class TestConnectionStringGeneration:
    """Test SQL connection string generation for different database types."""

    def test_register_sqlite_connector(self, client_with_auth):
        """Test SQLite connector generates correct connection string path."""
        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "SQLite DB",
                "database_type": "sqlite",
                "host": "localhost",
                "port": 0,
                "database": "/tmp/test.db",
                "username": "user",
                "password": "pass",
            },
        }
        response = client_with_auth.post("/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["connector_id"].startswith("sql_sqlite_")

    def test_register_mysql_connector(self, client_with_auth):
        """Test MySQL connector registration."""
        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "MySQL DB",
                "database_type": "mysql",
                "host": "localhost",
                "port": 3306,
                "database": "mydb",
                "username": "user",
                "password": "pass",
            },
        }
        response = client_with_auth.post("/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["connector_id"].startswith("sql_mysql_")

    def test_register_mssql_connector(self, client_with_auth):
        """Test MSSQL connector registration (generic connection string)."""
        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "MSSQL DB",
                "database_type": "mssql",
                "host": "localhost",
                "port": 1433,
                "database": "mydb",
                "username": "sa",
                "password": "pass",
            },
        }
        response = client_with_auth.post("/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["connector_id"].startswith("sql_mssql_")


class TestToolBusIntegration:
    """Test connector registration with tool bus."""

    def test_register_with_tool_bus_success(self, client_with_auth):
        """Test that tool bus registration is attempted when tool_bus is available."""
        mock_tool_bus = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_tool_bus.execute_tool = AsyncMock(return_value=mock_result)
        client_with_auth.app.state.tool_bus = mock_tool_bus

        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Bus Test DB",
                "database_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "db",
                "username": "user",
                "password": "pass",
            },
        }
        response = client_with_auth.post("/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers)
        assert response.status_code == status.HTTP_200_OK
        mock_tool_bus.execute_tool.assert_called_once()

    def test_register_with_tool_bus_failure(self, client_with_auth):
        """Test graceful handling when tool bus registration fails."""
        mock_tool_bus = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Connection refused"
        mock_tool_bus.execute_tool = AsyncMock(return_value=mock_result)
        client_with_auth.app.state.tool_bus = mock_tool_bus

        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Fail Bus DB",
                "database_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "db",
                "username": "user",
                "password": "pass",
            },
        }
        response = client_with_auth.post("/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers)
        # Should still succeed even though tool bus registration failed
        assert response.status_code == status.HTTP_200_OK

    def test_register_with_tool_bus_exception(self, client_with_auth):
        """Test graceful handling when tool bus throws exception."""
        mock_tool_bus = MagicMock()
        mock_tool_bus.execute_tool = AsyncMock(side_effect=RuntimeError("Bus unavailable"))
        client_with_auth.app.state.tool_bus = mock_tool_bus

        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Exception Bus DB",
                "database_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "db",
                "username": "user",
                "password": "pass",
            },
        }
        response = client_with_auth.post("/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers)
        # Should still succeed even if tool bus throws
        assert response.status_code == status.HTTP_200_OK


class TestTestConnectorTypes:
    """Test connector testing for different connector types."""

    def test_test_connector_updates_status(self, client_with_auth):
        """Test that testing a connector updates its status fields."""
        # Register
        request_data = {
            "connector_type": "sql",
            "config": {
                "connector_name": "Status Test DB",
                "database_type": "postgres",
                "host": "localhost",
                "port": 5432,
                "database": "db",
                "username": "user",
                "password": "pass",
            },
        }
        reg = client_with_auth.post("/v1/connectors/sql", json=request_data, headers=client_with_auth.auth_headers)
        connector_id = reg.json()["data"]["connector_id"]

        # Test it
        test_resp = client_with_auth.post(f"/v1/connectors/{connector_id}/test", headers=client_with_auth.auth_headers)
        assert test_resp.status_code == status.HTTP_200_OK
        data = test_resp.json()["data"]
        assert data["success"] is True
        assert data["tested_at"] is not None
        assert data["latency_ms"] >= 0

        # Verify status was updated in registry
        list_resp = client_with_auth.get("/v1/connectors/", headers=client_with_auth.auth_headers)
        connector = list_resp.json()["data"]["connectors"][0]
        assert connector["last_tested"] is not None
        assert connector["last_test_result"] == "success"

    def test_test_connector_requires_admin(self, client_with_auth):
        """Test that testing requires admin auth."""
        response = client_with_auth.post("/v1/connectors/some_id/test")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_connector_requires_admin(self, client_with_auth):
        """Test that updating requires admin auth."""
        response = client_with_auth.patch("/v1/connectors/some_id", json={"enabled": False})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestHelperFunctions:
    """Test internal helper functions."""

    @pytest.mark.asyncio
    async def test_test_sql_connector_no_tool_bus(self):
        """Test SQL connector test when tool bus is not available."""
        success, message = await connectors._test_sql_connector("test_id", None)
        assert success is True
        assert "skipped" in message.lower()

    @pytest.mark.asyncio
    async def test_test_sql_connector_with_tool_bus_success(self):
        """Test SQL connector test with successful tool bus query."""
        mock_bus = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_bus.execute_tool = AsyncMock(return_value=mock_result)

        success, message = await connectors._test_sql_connector("test_id", mock_bus)
        assert success is True
        assert "successful" in message.lower()

    @pytest.mark.asyncio
    async def test_test_sql_connector_with_tool_bus_failure(self):
        """Test SQL connector test with failed tool bus query."""
        mock_bus = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Connection refused"
        mock_bus.execute_tool = AsyncMock(return_value=mock_result)

        success, message = await connectors._test_sql_connector("test_id", mock_bus)
        assert success is False

    @pytest.mark.asyncio
    async def test_test_sql_connector_with_tool_bus_exception(self):
        """Test SQL connector test with tool bus exception."""
        mock_bus = MagicMock()
        mock_bus.execute_tool = AsyncMock(side_effect=RuntimeError("Error"))

        success, message = await connectors._test_sql_connector("test_id", mock_bus)
        assert success is False
        assert "error" in message.lower()

    def test_test_rest_connector(self):
        """Test REST connector test (simulated)."""
        success, message = connectors._test_rest_connector()
        assert success is True
        assert "rest" in message.lower()
