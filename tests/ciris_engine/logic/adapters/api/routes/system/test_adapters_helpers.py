"""Tests for adapter listing helper functions."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from ciris_engine.logic.adapters.api.routes.system.adapters import (
    _convert_adapter_to_status,
    _create_auto_adapter_info,
    _get_auto_loaded_adapters,
)
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig
from ciris_engine.schemas.services.core.runtime import AdapterInfo, AdapterStatus


class TestCreateAutoAdapterInfo:
    """Tests for _create_auto_adapter_info helper."""

    def test_creates_adapter_info(self):
        """Creates AdapterInfo with correct fields."""
        service_type = Mock()
        service_type.value = "tool"

        result = _create_auto_adapter_info("test_adapter", service_type)

        assert isinstance(result, AdapterInfo)
        assert result.adapter_id == "test_adapter_auto"
        assert result.adapter_type == "TEST_ADAPTER"
        assert result.status == AdapterStatus.RUNNING

    def test_sets_service_type(self):
        """Sets services_registered from service type."""
        service_type = Mock()
        service_type.value = "wise_authority"

        result = _create_auto_adapter_info("wa_adapter", service_type)

        assert result.services_registered == ["wise_authority"]

    def test_sets_default_values(self):
        """Sets default values for counters and tools."""
        service_type = Mock()
        service_type.value = "tool"

        result = _create_auto_adapter_info("adapter", service_type)

        assert result.messages_processed == 0
        assert result.error_count == 0
        assert result.last_error is None
        assert result.tools == []


class TestGetAutoLoadedAdapters:
    """Tests for _get_auto_loaded_adapters helper."""

    def test_returns_empty_for_no_providers(self):
        """Returns empty list when no providers."""
        service_registry = Mock()
        service_registry.get_providers_by_type.return_value = []
        seen_ids: set = set()

        result = _get_auto_loaded_adapters(service_registry, seen_ids)

        assert result == []

    def test_skips_non_auto_loaded(self):
        """Skips providers without auto_loaded metadata."""
        service_registry = Mock()
        service_registry.get_providers_by_type.return_value = [
            {"metadata": {"auto_loaded": False}},
            {"metadata": {}},
        ]
        seen_ids: set = set()

        result = _get_auto_loaded_adapters(service_registry, seen_ids)

        assert result == []

    def test_includes_auto_loaded(self):
        """Includes providers with auto_loaded=True."""
        service_registry = Mock()
        service_registry.get_providers_by_type.return_value = [
            {"metadata": {"auto_loaded": True, "adapter": "test_adapter"}},
        ]
        seen_ids: set = set()

        result = _get_auto_loaded_adapters(service_registry, seen_ids)

        assert len(result) == 1
        assert result[0].adapter_id == "test_adapter_auto"

    def test_skips_already_seen(self):
        """Skips adapters already in seen_ids."""
        service_registry = Mock()
        service_registry.get_providers_by_type.return_value = [
            {"metadata": {"auto_loaded": True, "adapter": "existing"}},
        ]
        seen_ids = {"existing_auto"}

        result = _get_auto_loaded_adapters(service_registry, seen_ids)

        assert result == []

    def test_adds_to_seen_ids(self):
        """Adds new adapter IDs to seen_ids set."""
        service_registry = Mock()
        service_registry.get_providers_by_type.return_value = [
            {"metadata": {"auto_loaded": True, "adapter": "new_adapter"}},
        ]
        seen_ids: set = set()

        _get_auto_loaded_adapters(service_registry, seen_ids)

        assert "new_adapter_auto" in seen_ids

    def test_handles_provider_exception(self):
        """Handles exceptions from get_providers_by_type gracefully."""
        service_registry = Mock()
        service_registry.get_providers_by_type.side_effect = Exception("Provider error")
        seen_ids: set = set()

        result = _get_auto_loaded_adapters(service_registry, seen_ids)

        assert result == []


class TestConvertAdapterToStatus:
    """Tests for _convert_adapter_to_status helper."""

    def _create_adapter_info(
        self,
        adapter_id: str = "test",
        status: AdapterStatus = AdapterStatus.RUNNING,
        messages_processed: int = 0,
        error_count: int = 0,
        started_at: datetime = None,
        config_params: AdapterConfig = None,
    ) -> AdapterInfo:
        """Create a test AdapterInfo."""
        return AdapterInfo(
            adapter_id=adapter_id,
            adapter_type="TEST",
            status=status,
            started_at=started_at or datetime.now(timezone.utc),
            config_params=config_params,
            services_registered=["test"],
            messages_processed=messages_processed,
            error_count=error_count,
            last_error=None,
            tools=[],
        )

    def test_converts_running_status(self):
        """Correctly identifies running status."""
        adapter = self._create_adapter_info(status=AdapterStatus.RUNNING)

        result = _convert_adapter_to_status(adapter)

        assert result.is_running is True

    def test_converts_stopped_status(self):
        """Correctly identifies stopped status."""
        adapter = self._create_adapter_info(status=AdapterStatus.STOPPED)

        result = _convert_adapter_to_status(adapter)

        assert result.is_running is False

    def test_uses_adapter_config_if_available(self):
        """Uses config_params from adapter if available."""
        config = AdapterConfig(adapter_type="CUSTOM", enabled=True, settings={"key": "value"})
        adapter = self._create_adapter_info(config_params=config)

        result = _convert_adapter_to_status(adapter)

        assert result.config_params == config

    def test_creates_default_config_if_missing(self):
        """Creates default config if adapter has none."""
        adapter = self._create_adapter_info(config_params=None)

        result = _convert_adapter_to_status(adapter)

        assert result.config_params is not None
        assert result.config_params.adapter_type == "TEST"

    def test_no_metrics_when_zero_counts(self):
        """No metrics when messages_processed and error_count are 0."""
        adapter = self._create_adapter_info(messages_processed=0, error_count=0)

        result = _convert_adapter_to_status(adapter)

        assert result.metrics is None

    def test_includes_metrics_when_messages_processed(self):
        """Includes metrics when messages have been processed."""
        adapter = self._create_adapter_info(messages_processed=10, error_count=0)

        result = _convert_adapter_to_status(adapter)

        assert result.metrics is not None
        assert result.metrics.messages_processed == 10

    def test_includes_metrics_when_errors(self):
        """Includes metrics when there are errors."""
        adapter = self._create_adapter_info(messages_processed=0, error_count=5)

        result = _convert_adapter_to_status(adapter)

        assert result.metrics is not None
        assert result.metrics.errors_count == 5

    def test_calculates_uptime(self):
        """Calculates uptime from started_at."""
        started = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        adapter = self._create_adapter_info(started_at=started, messages_processed=1)

        result = _convert_adapter_to_status(adapter)

        assert result.metrics is not None
        assert result.metrics.uptime_seconds > 0

    def test_preserves_adapter_fields(self):
        """Preserves adapter_id, adapter_type, services_registered."""
        adapter = self._create_adapter_info(adapter_id="my_adapter")

        result = _convert_adapter_to_status(adapter)

        assert result.adapter_id == "my_adapter"
        assert result.adapter_type == "TEST"
        assert result.services_registered == ["test"]
