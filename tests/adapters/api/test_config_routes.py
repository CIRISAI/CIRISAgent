"""
Config Routes Tests

Comprehensive tests for config API endpoints, focusing on:
- wrap_config_value() helper function
- TypeScript SDK-compatible value wrapping
- All config endpoints (list, get, update, delete)
- Edge cases and type conversion
"""

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes.config import (
    ConfigItemResponse,
    ConfigListResponse,
    ConfigUpdate,
    delete_config,
    get_config,
    list_configs,
    update_config,
    wrap_config_value,
)
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.services.nodes import ConfigNode, ConfigValue


class TestWrapConfigValue:
    """Test the wrap_config_value() helper function."""

    def test_wrap_none_value(self):
        """Test wrapping None values."""
        wrapped = wrap_config_value(None)
        assert wrapped.string_value is None
        assert wrapped.int_value is None
        assert wrapped.float_value is None
        assert wrapped.bool_value is None
        assert wrapped.list_value is None
        assert wrapped.dict_value is None

    def test_wrap_string_value(self):
        """Test wrapping string values."""
        wrapped = wrap_config_value("hello world")
        assert wrapped.string_value == "hello world"
        assert wrapped.int_value is None
        assert wrapped.float_value is None
        assert wrapped.bool_value is None
        assert wrapped.list_value is None
        assert wrapped.dict_value is None

    def test_wrap_int_value(self):
        """Test wrapping integer values."""
        wrapped = wrap_config_value(42)
        assert wrapped.string_value is None
        assert wrapped.int_value == 42
        assert wrapped.float_value is None
        assert wrapped.bool_value is None
        assert wrapped.list_value is None
        assert wrapped.dict_value is None

    def test_wrap_float_value(self):
        """Test wrapping float values."""
        wrapped = wrap_config_value(3.14159)
        assert wrapped.string_value is None
        assert wrapped.int_value is None
        assert wrapped.float_value == 3.14159
        assert wrapped.bool_value is None
        assert wrapped.list_value is None
        assert wrapped.dict_value is None

    def test_wrap_bool_value_true(self):
        """Test wrapping boolean True value."""
        wrapped = wrap_config_value(True)
        assert wrapped.string_value is None
        assert wrapped.int_value is None
        assert wrapped.float_value is None
        assert wrapped.bool_value is True
        assert wrapped.list_value is None
        assert wrapped.dict_value is None

    def test_wrap_bool_value_false(self):
        """Test wrapping boolean False value."""
        wrapped = wrap_config_value(False)
        assert wrapped.string_value is None
        assert wrapped.int_value is None
        assert wrapped.float_value is None
        assert wrapped.bool_value is False
        assert wrapped.list_value is None
        assert wrapped.dict_value is None

    def test_wrap_list_value(self):
        """Test wrapping list values."""
        test_list = ["a", "b", "c"]
        wrapped = wrap_config_value(test_list)
        assert wrapped.string_value is None
        assert wrapped.int_value is None
        assert wrapped.float_value is None
        assert wrapped.bool_value is None
        assert wrapped.list_value == test_list
        assert wrapped.dict_value is None

    def test_wrap_dict_value(self):
        """Test wrapping dict values."""
        test_dict = {"key1": "value1", "key2": 42}
        wrapped = wrap_config_value(test_dict)
        assert wrapped.string_value is None
        assert wrapped.int_value is None
        assert wrapped.float_value is None
        assert wrapped.bool_value is None
        assert wrapped.list_value is None
        assert wrapped.dict_value == test_dict

    def test_wrap_already_wrapped_value(self):
        """Test wrapping an already-wrapped ConfigValueWrapper (safety check)."""
        from ciris_engine.schemas.services.nodes import ConfigValue as ConfigValueWrapper

        original = ConfigValueWrapper(string_value="test")
        wrapped = wrap_config_value(original)

        # Should return the same wrapped value
        assert wrapped is original
        assert wrapped.string_value == "test"

    def test_wrap_empty_string(self):
        """Test wrapping empty string."""
        wrapped = wrap_config_value("")
        assert wrapped.string_value == ""
        assert wrapped.int_value is None

    def test_wrap_zero(self):
        """Test wrapping zero integer."""
        wrapped = wrap_config_value(0)
        assert wrapped.int_value == 0
        assert wrapped.bool_value is None

    def test_wrap_empty_list(self):
        """Test wrapping empty list."""
        wrapped = wrap_config_value([])
        assert wrapped.list_value == []
        assert wrapped.string_value is None

    def test_wrap_empty_dict(self):
        """Test wrapping empty dict."""
        wrapped = wrap_config_value({})
        assert wrapped.dict_value == {}
        assert wrapped.string_value is None

    def test_wrap_nested_dict(self):
        """Test wrapping nested dictionary."""
        nested_dict = {"outer": {"inner": {"deep": "value"}}}
        wrapped = wrap_config_value(nested_dict)
        assert wrapped.dict_value == nested_dict

    def test_wrap_mixed_list(self):
        """Test wrapping list with mixed types."""
        mixed_list = [1, "two", 3.0, True, False]
        wrapped = wrap_config_value(mixed_list)
        assert wrapped.list_value == mixed_list

    def test_wrap_custom_object_fallback(self):
        """Test wrapping custom object falls back to string conversion."""

        class CustomObject:
            def __str__(self):
                return "custom_repr"

        obj = CustomObject()
        wrapped = wrap_config_value(obj)
        assert wrapped.string_value == "custom_repr"


class TestListConfigsEndpoint:
    """Test the list_configs endpoint."""

    @pytest.mark.asyncio
    async def test_list_configs_success(self):
        """Test successful config listing with wrapped values."""
        # Mock request with config_service
        mock_request = MagicMock()
        mock_config_service = AsyncMock()
        mock_config_service.list_configs.return_value = {
            "test.string": "hello",
            "test.int": 42,
            "test.bool": True,
            "test.dict": {"key": "value"},
        }
        mock_request.app.state.config_service = mock_config_service

        # Mock auth context
        mock_auth = MagicMock()
        mock_auth.role = UserRole.ADMIN

        # Call endpoint
        response = await list_configs(mock_request, prefix=None, auth=mock_auth)

        # Verify response structure
        assert response.data.total == 4
        assert len(response.data.configs) == 4

        # Verify each config is properly wrapped
        config_dict = {c.key: c for c in response.data.configs}

        # String value
        assert config_dict["test.string"].value.string_value == "hello"
        assert config_dict["test.string"].value.int_value is None

        # Int value
        assert config_dict["test.int"].value.int_value == 42
        assert config_dict["test.int"].value.string_value is None

        # Bool value
        assert config_dict["test.bool"].value.bool_value is True
        assert config_dict["test.bool"].value.int_value is None

        # Dict value
        assert config_dict["test.dict"].value.dict_value == {"key": "value"}
        assert config_dict["test.dict"].value.string_value is None

    @pytest.mark.asyncio
    async def test_list_configs_with_prefix(self):
        """Test config listing with prefix filter."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()
        mock_config_service.list_configs.return_value = {
            "system.debug": True,
            "system.log_level": "INFO",
            "user.name": "test",
        }
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.role = UserRole.ADMIN

        # Call with prefix
        response = await list_configs(mock_request, prefix="system", auth=mock_auth)

        # Should only return system.* configs
        assert response.data.total == 2
        keys = [c.key for c in response.data.configs]
        assert "system.debug" in keys
        assert "system.log_level" in keys
        assert "user.name" not in keys

    @pytest.mark.asyncio
    async def test_list_configs_service_unavailable(self):
        """Test error when config service is not available."""
        mock_request = MagicMock()
        mock_request.app.state.config_service = None

        mock_auth = MagicMock()
        mock_auth.role = UserRole.ADMIN

        with pytest.raises(HTTPException) as exc_info:
            await list_configs(mock_request, prefix=None, auth=mock_auth)

        assert exc_info.value.status_code == 503


class TestGetConfigEndpoint:
    """Test the get_config endpoint."""

    @pytest.mark.asyncio
    async def test_get_config_string_value(self):
        """Test getting config with string value (critical fix test)."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()

        # Mock ConfigNode with ConfigValue wrapper containing primitive
        mock_config_node = MagicMock(spec=ConfigNode)
        mock_config_node.value = MagicMock(spec=ConfigValue)
        mock_config_node.value.value = "test_string"  # Critical: .value.value extraction
        mock_config_node.updated_at = datetime.now(timezone.utc)
        mock_config_node.updated_by = "test_user"

        mock_config_service.get_config.return_value = mock_config_node
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.role = UserRole.ADMIN

        # Call endpoint
        response = await get_config(mock_request, key="test.key", auth=mock_auth)

        # Verify wrapped value
        assert response.data.key == "test.key"
        assert response.data.value.string_value == "test_string"
        assert response.data.value.int_value is None

    @pytest.mark.asyncio
    async def test_get_config_int_value(self):
        """Test getting config with integer value."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()

        mock_config_node = MagicMock(spec=ConfigNode)
        mock_config_node.value = MagicMock(spec=ConfigValue)
        mock_config_node.value.value = 42
        mock_config_node.updated_at = datetime.now(timezone.utc)
        mock_config_node.updated_by = "test_user"

        mock_config_service.get_config.return_value = mock_config_node
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.role = UserRole.ADMIN

        response = await get_config(mock_request, key="test.int", auth=mock_auth)

        assert response.data.value.int_value == 42
        assert response.data.value.string_value is None

    @pytest.mark.asyncio
    async def test_get_config_dict_value(self):
        """Test getting config with dictionary value."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()

        test_dict = {"host": "localhost", "port": 8080}
        mock_config_node = MagicMock(spec=ConfigNode)
        mock_config_node.value = MagicMock(spec=ConfigValue)
        mock_config_node.value.value = test_dict
        mock_config_node.updated_at = datetime.now(timezone.utc)
        mock_config_node.updated_by = "system"

        mock_config_service.get_config.return_value = mock_config_node
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.role = UserRole.ADMIN

        response = await get_config(mock_request, key="adapter.settings", auth=mock_auth)

        assert response.data.value.dict_value == test_dict
        assert response.data.value.string_value is None

    @pytest.mark.asyncio
    async def test_get_config_not_found(self):
        """Test getting non-existent config."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()
        mock_config_service.get_config.return_value = None
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.role = UserRole.ADMIN

        with pytest.raises(HTTPException) as exc_info:
            await get_config(mock_request, key="nonexistent.key", auth=mock_auth)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_config_service_unavailable(self):
        """Test error when config service is not available."""
        mock_request = MagicMock()
        mock_request.app.state.config_service = None

        mock_auth = MagicMock()
        mock_auth.role = UserRole.ADMIN

        with pytest.raises(HTTPException) as exc_info:
            await get_config(mock_request, key="test.key", auth=mock_auth)

        assert exc_info.value.status_code == 503


class TestUpdateConfigEndpoint:
    """Test the update_config endpoint."""

    @pytest.mark.asyncio
    async def test_update_config_string(self):
        """Test updating config with string value."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.user_id = "test_user"
        mock_auth.role = UserRole.ADMIN

        body = ConfigUpdate(value="new_value", reason="test update")

        response = await update_config(mock_request, body, key="test.key", auth=mock_auth)

        # Verify service was called
        mock_config_service.set_config.assert_called_once_with(
            key="test.key", value="new_value", updated_by="test_user"
        )

        # Verify wrapped response
        assert response.data.key == "test.key"
        assert response.data.value.string_value == "new_value"
        assert response.data.value.int_value is None

    @pytest.mark.asyncio
    async def test_update_config_int(self):
        """Test updating config with integer value."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.user_id = "test_user"
        mock_auth.role = UserRole.ADMIN

        body = ConfigUpdate(value=100)

        response = await update_config(mock_request, body, key="test.count", auth=mock_auth)

        assert response.data.value.int_value == 100
        assert response.data.value.string_value is None

    @pytest.mark.asyncio
    async def test_update_config_dict(self):
        """Test updating config with dictionary value."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.user_id = "admin"
        mock_auth.role = UserRole.ADMIN

        config_dict = {"enabled": True, "timeout": 30}
        body = ConfigUpdate(value=config_dict)

        response = await update_config(mock_request, body, key="service.settings", auth=mock_auth)

        assert response.data.value.dict_value == config_dict

    @pytest.mark.asyncio
    async def test_update_config_requires_admin(self):
        """Test that updating non-sensitive config requires ADMIN role."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.user_id = "test_user"
        mock_auth.role = UserRole.OBSERVER  # Insufficient

        body = ConfigUpdate(value="test")

        with pytest.raises(HTTPException) as exc_info:
            await update_config(mock_request, body, key="test.key", auth=mock_auth)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_update_sensitive_config_requires_system_admin(self):
        """Test that updating sensitive config requires SYSTEM_ADMIN role."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.user_id = "admin"
        mock_auth.role = UserRole.ADMIN  # Not enough for sensitive

        body = ConfigUpdate(value="secret_value")

        with pytest.raises(HTTPException) as exc_info:
            # Sensitive keys contain "secret", "password", "token", "key", "credential"
            await update_config(mock_request, body, key="api.secret_key", auth=mock_auth)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_update_system_config_requires_system_admin(self):
        """Test that updating system.* config requires SYSTEM_ADMIN role."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.user_id = "admin"
        mock_auth.role = UserRole.ADMIN  # Not enough for system.*

        body = ConfigUpdate(value="test")

        with pytest.raises(HTTPException) as exc_info:
            await update_config(mock_request, body, key="system.debug", auth=mock_auth)

        assert exc_info.value.status_code == 403


class TestDeleteConfigEndpoint:
    """Test the delete_config endpoint."""

    @pytest.mark.asyncio
    async def test_delete_config_success(self):
        """Test successful config deletion."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()
        mock_config_service.delete_config = AsyncMock()
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.user_id = "admin"
        mock_auth.role = UserRole.ADMIN

        response = await delete_config(mock_request, key="test.key", auth=mock_auth)

        mock_config_service.delete_config.assert_called_once_with("test.key")
        assert response.data["status"] == "deleted"
        assert response.data["key"] == "test.key"

    @pytest.mark.asyncio
    async def test_delete_config_fallback_to_set_none(self):
        """Test config deletion falls back to set_config(None) if delete_config not available."""
        mock_request = MagicMock()

        # Create a mock service without delete_config method
        class MockConfigService:
            async def set_config(self, key, value, updated_by):
                pass

        mock_config_service = MockConfigService()
        mock_config_service.set_config = AsyncMock()
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.user_id = "admin"
        mock_auth.role = UserRole.ADMIN

        response = await delete_config(mock_request, key="test.key", auth=mock_auth)

        # Should call set_config with None
        mock_config_service.set_config.assert_called_once_with("test.key", None, updated_by="admin")
        assert response.data["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_sensitive_config_requires_system_admin(self):
        """Test that deleting sensitive config requires SYSTEM_ADMIN role."""
        mock_request = MagicMock()
        mock_config_service = AsyncMock()
        mock_request.app.state.config_service = mock_config_service

        mock_auth = MagicMock()
        mock_auth.user_id = "admin"
        mock_auth.role = UserRole.ADMIN  # Not enough

        with pytest.raises(HTTPException) as exc_info:
            # Use a key that matches sensitive pattern: ends with _token
            await delete_config(mock_request, key="api_token", auth=mock_auth)

        assert exc_info.value.status_code == 403
        assert "sensitive" in str(exc_info.value.detail).lower()
