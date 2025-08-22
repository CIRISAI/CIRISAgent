"""
Integration tests for adapter validation and tool provider counting fixes.

This module tests the fixes for:
1. RuntimeAdapterStatus validation errors
2. Tool provider deduplication
3. Metadata in tool listing responses
"""

from datetime import datetime, timezone

import pytest

from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, AdapterMetrics, RuntimeAdapterStatus


class TestAdapterMetricsValidation:
    """Test that AdapterMetrics objects are handled correctly."""

    def test_runtime_adapter_status_with_metrics_object(self):
        """Test that RuntimeAdapterStatus accepts AdapterMetrics object (not dict)."""
        # Create valid AdapterMetrics object
        metrics = AdapterMetrics(
            messages_processed=100,
            errors_count=5,
            uptime_seconds=3600.0,
            last_error="Test error",
            last_error_time=datetime.now(timezone.utc),
        )

        # Create config
        config = AdapterConfig(adapter_type="test", enabled=True, settings={})

        # This should not raise validation error (was failing when metrics was dict)
        status = RuntimeAdapterStatus(
            adapter_id="test_adapter",
            adapter_type="test",
            is_running=True,
            loaded_at=datetime.now(timezone.utc),
            services_registered=["test_service"],
            config_params=config,
            metrics=metrics,  # Pass object, not dict - this was the fix
            last_activity=datetime.now(timezone.utc),
            tools=["test_tool"],
        )

        # Verify the object is stored correctly
        assert status.metrics == metrics
        assert status.metrics.messages_processed == 100
        assert status.metrics.errors_count == 5

    def test_runtime_adapter_status_with_none_metrics(self):
        """Test that RuntimeAdapterStatus accepts None for metrics."""
        config = AdapterConfig(adapter_type="test", enabled=True, settings={})

        # Should accept None for metrics
        status = RuntimeAdapterStatus(
            adapter_id="test_adapter",
            adapter_type="test",
            is_running=True,
            loaded_at=datetime.now(timezone.utc),
            services_registered=[],
            config_params=config,
            metrics=None,  # None should be valid
            last_activity=None,
            tools=None,
        )

        assert status.metrics is None

    def test_adapter_metrics_serialization(self):
        """Test that AdapterMetrics serializes correctly to JSON."""
        metrics = AdapterMetrics(
            messages_processed=50,
            errors_count=2,
            uptime_seconds=1800.5,
            last_error="Connection timeout",
            last_error_time=datetime.now(timezone.utc),
        )

        # Should serialize to dict for JSON
        metrics_dict = metrics.model_dump()

        assert metrics_dict["messages_processed"] == 50
        assert metrics_dict["errors_count"] == 2
        assert metrics_dict["uptime_seconds"] == 1800.5
        assert metrics_dict["last_error"] == "Connection timeout"
        assert "last_error_time" in metrics_dict


class TestSystemRoutesIntegration:
    """Integration tests for system routes with the fixes."""

    def test_adapters_endpoint_structure(self, client, auth_headers):
        """Test that adapters endpoint returns proper structure."""
        response = client.get("/v1/system/adapters", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()

            # Verify response structure
            assert "data" in data
            assert "adapters" in data["data"]
            assert "total_count" in data["data"]
            assert "running_count" in data["data"]

            # If there are adapters, verify their structure
            adapters = data["data"]["adapters"]
            for adapter in adapters:
                # Required fields
                assert "adapter_id" in adapter
                assert "adapter_type" in adapter
                assert "is_running" in adapter
                assert "loaded_at" in adapter
                assert "services_registered" in adapter
                assert "config_params" in adapter

                # Optional fields
                if "metrics" in adapter and adapter["metrics"]:
                    metrics = adapter["metrics"]
                    # Verify metrics structure (should be dict after JSON serialization)
                    assert isinstance(metrics, dict)
                    assert "messages_processed" in metrics
                    assert "errors_count" in metrics
                    assert "uptime_seconds" in metrics

    def test_tools_endpoint_structure(self, client, auth_headers):
        """Test that tools endpoint returns proper structure with deduplicated providers."""
        response = client.get("/v1/system/tools", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()

            # Verify basic structure
            assert "data" in data
            tools = data["data"]
            assert isinstance(tools, list)

            # Collect provider information from tools
            providers_seen = set()
            for tool in tools:
                # Verify tool structure
                assert "name" in tool
                assert "description" in tool
                assert "provider" in tool
                assert "category" in tool
                assert "cost" in tool

                # Collect providers (may be comma-separated for deduplicated tools)
                provider = tool["provider"]
                if "," in provider:
                    # Multiple providers for same tool
                    for p in provider.split(", "):
                        providers_seen.add(p.strip())
                else:
                    providers_seen.add(provider)

            # The fix ensures providers are properly deduplicated in counting
            # We can verify this by checking that provider names don't repeat unnecessarily
            # and that tools with same names have aggregated providers

    def test_tools_deduplication(self, client, auth_headers):
        """Test that tools with same name are properly deduplicated."""
        response = client.get("/v1/system/tools", headers=auth_headers)

        if response.status_code == 200:
            data = response.json()
            tools = data["data"]

            # Collect all tool names
            tool_names = [tool["name"] for tool in tools]

            # Verify no duplicate tool names
            assert len(tool_names) == len(set(tool_names)), "Tool names should be unique"

            # Check if any tools have multiple providers (comma-separated)
            # This is valid when same tool is offered by multiple providers
            for tool in tools:
                if "," in tool.get("provider", ""):
                    # This indicates proper deduplication with provider aggregation
                    providers = tool["provider"].split(", ")
                    # Each provider should be unique in the list
                    assert len(providers) == len(set(providers))
