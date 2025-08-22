"""
Tests for adapter validation and tool provider counting fixes.

This module tests the fixes for:
1. RuntimeAdapterStatus validation errors
2. Tool provider deduplication
3. Metadata in tool listing responses
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes import system
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, AdapterMetrics, RuntimeAdapterStatus


class TestAdapterValidation:
    """Test adapter validation fixes."""

    def test_adapter_metrics_object_validation(self):
        """Test that AdapterMetrics is passed as object, not dict."""
        # Create valid AdapterMetrics object
        metrics = AdapterMetrics(
            messages_processed=100,
            errors_count=5,
            uptime_seconds=3600.0,
            last_error="Test error",
            last_error_time=datetime.now(timezone.utc),
        )

        # Create RuntimeAdapterStatus with metrics object
        config = AdapterConfig(adapter_type="test", enabled=True, settings={})

        # This should not raise validation error
        status = RuntimeAdapterStatus(
            adapter_id="test_adapter",
            adapter_type="test",
            is_running=True,
            loaded_at=datetime.now(timezone.utc),
            services_registered=["test_service"],
            config_params=config,
            metrics=metrics,  # Pass object, not dict
            last_activity=datetime.now(timezone.utc),
            tools=["test_tool"],
        )

        assert status.metrics == metrics
        assert status.metrics.messages_processed == 100

    def test_adapter_listing_with_metrics(self, app, client):
        """Test that adapter listing properly formats metrics."""
        # Router already included by app fixture

        # Mock runtime control service with async method
        mock_runtime = MagicMock()
        mock_adapter_info = MagicMock()
        mock_adapter_info.adapter_id = "test_adapter"
        mock_adapter_info.adapter_type = "api"
        mock_adapter_info.status = "RUNNING"
        mock_adapter_info.started_at = datetime.now(timezone.utc)
        mock_adapter_info.messages_processed = 50
        mock_adapter_info.error_count = 2
        mock_adapter_info.last_error = "Test error"
        mock_adapter_info.tools = ["tool1", "tool2"]

        # Make list_adapters async
        async def async_list_adapters():
            return [mock_adapter_info]

        mock_runtime.list_adapters = async_list_adapters

        app.state.main_runtime_control_service = mock_runtime

        # Use dev auth credentials
        response = client.get("/v1/system/adapters", headers={"Authorization": "Bearer admin:ciris_admin_password"})

        assert response.status_code == 200
        data = response.json()

        assert "data" in data
        assert "adapters" in data["data"]
        adapters = data["data"]["adapters"]

        assert len(adapters) == 1
        adapter = adapters[0]

        # Verify metrics is present and valid
        assert "metrics" in adapter
        if adapter["metrics"]:
            assert adapter["metrics"]["messages_processed"] == 50
            assert adapter["metrics"]["errors_count"] == 2


class TestToolProviderCounting:
    """Test tool provider counting and deduplication."""

    def test_tool_provider_deduplication(self, app, client):
        """Test that duplicate tool providers are deduplicated."""
        # Router already included by app fixture

        # Mock service registry with duplicate providers
        mock_registry = MagicMock()
        mock_registry._services = {}

        # Create mock tool providers (including duplicates)
        from ciris_engine.schemas.runtime.enums import ServiceType

        mock_provider1 = MagicMock()
        mock_provider1.instance = MagicMock(spec=["get_all_tool_info"])
        mock_provider1.instance.__class__.__name__ = "APIToolService"
        # Create proper mock tool objects with actual values
        tool1 = MagicMock()
        tool1.name = "tool1"
        tool1.description = "Tool 1"
        tool1.parameters = None
        tool1.category = "general"
        tool1.cost = 0.0
        tool1.when_to_use = None

        tool2 = MagicMock()
        tool2.name = "tool2"
        tool2.description = "Tool 2"
        tool2.parameters = None
        tool2.category = "general"
        tool2.cost = 0.0
        tool2.when_to_use = None

        mock_provider1.instance.get_all_tool_info = AsyncMock(return_value=[tool1, tool2])

        mock_provider2 = MagicMock()
        mock_provider2.instance = MagicMock(spec=["get_all_tool_info"])
        mock_provider2.instance.__class__.__name__ = "SecretsToolService"
        tool3 = MagicMock()
        tool3.name = "recall_secret"
        tool3.description = "Recall secret"
        tool3.parameters = None
        tool3.category = "general"
        tool3.cost = 0.0
        tool3.when_to_use = None

        mock_provider2.instance.get_all_tool_info = AsyncMock(return_value=[tool3])

        # Duplicate provider (should be deduplicated)
        mock_provider3 = MagicMock()
        mock_provider3.instance = MagicMock(spec=["get_all_tool_info"])
        mock_provider3.instance.__class__.__name__ = "APIToolService"
        tool4 = MagicMock()
        tool4.name = "tool3"
        tool4.description = "Tool 3"
        tool4.parameters = None
        tool4.category = "general"
        tool4.cost = 0.0
        tool4.when_to_use = None

        mock_provider3.instance.get_all_tool_info = AsyncMock(return_value=[tool4])

        mock_registry._services[ServiceType.TOOL] = [
            mock_provider1,
            mock_provider2,
            mock_provider3,  # Duplicate APIToolService
        ]

        mock_registry.get_provider_info = MagicMock(return_value={"services": {}})

        app.state.service_registry = mock_registry

        # Use dev auth credentials
        response = client.get("/v1/system/tools", headers={"Authorization": "Bearer admin:ciris_admin_password"})

        assert response.status_code == 200
        data = response.json()

        # Check metadata
        assert "metadata" in data
        metadata = data["metadata"]

        # Should have only 2 unique providers (APIToolService and SecretsToolService)
        assert metadata["provider_count"] == 2
        assert set(metadata["providers"]) == {"APIToolService", "SecretsToolService"}

        # Should have 4 total tools
        assert metadata["total_tools"] == 4
        assert len(data["data"]) == 4

    def test_tool_deduplication_same_name(self, app, client):
        """Test that tools with same name from different providers are deduplicated."""
        # Router already included by app fixture

        mock_registry = MagicMock()
        mock_registry._services = {}

        from ciris_engine.schemas.runtime.enums import ServiceType

        # Two providers offering the same tool
        mock_provider1 = MagicMock()
        mock_provider1.instance = MagicMock(spec=["get_all_tool_info"])
        mock_provider1.instance.__class__.__name__ = "Provider1"
        shared_tool1 = MagicMock()
        shared_tool1.name = "shared_tool"
        shared_tool1.description = "Shared tool"
        shared_tool1.parameters = None
        shared_tool1.category = "general"
        shared_tool1.cost = 0.0
        shared_tool1.when_to_use = None

        mock_provider1.instance.get_all_tool_info = AsyncMock(return_value=[shared_tool1])

        mock_provider2 = MagicMock()
        mock_provider2.instance = MagicMock(spec=["get_all_tool_info"])
        mock_provider2.instance.__class__.__name__ = "Provider2"
        shared_tool2 = MagicMock()
        shared_tool2.name = "shared_tool"
        shared_tool2.description = "Shared tool"
        shared_tool2.parameters = None
        shared_tool2.category = "general"
        shared_tool2.cost = 0.0
        shared_tool2.when_to_use = None

        mock_provider2.instance.get_all_tool_info = AsyncMock(return_value=[shared_tool2])

        mock_registry._services[ServiceType.TOOL] = [
            mock_provider1,
            mock_provider2,
        ]

        mock_registry.get_provider_info = MagicMock(return_value={"services": {}})

        app.state.service_registry = mock_registry

        # Use dev auth credentials
        response = client.get("/v1/system/tools", headers={"Authorization": "Bearer admin:ciris_admin_password"})

        assert response.status_code == 200
        data = response.json()

        # Should have only 1 tool (deduplicated)
        assert len(data["data"]) == 1

        # Provider should list both providers
        tool = data["data"][0]
        assert "Provider1" in tool["provider"]
        assert "Provider2" in tool["provider"]

    def test_empty_tool_list(self, app, client):
        """Test handling of empty tool list."""
        # Router already included by app fixture

        # Mock registry with no tool providers
        mock_registry = MagicMock()
        mock_registry._services = {}
        mock_registry.get_provider_info = MagicMock(return_value={"services": {}})

        app.state.service_registry = mock_registry

        # Use dev auth credentials
        response = client.get("/v1/system/tools", headers={"Authorization": "Bearer admin:ciris_admin_password"})

        assert response.status_code == 200
        data = response.json()

        assert data["data"] == []

        if "metadata" in data:
            assert data["metadata"]["provider_count"] == 0
            assert data["metadata"]["total_tools"] == 0
            assert data["metadata"]["providers"] == []
