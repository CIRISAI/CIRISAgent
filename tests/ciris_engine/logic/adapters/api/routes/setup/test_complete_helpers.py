"""Tests for setup completion helper functions."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.adapters.api.routes.setup.complete import (
    _write_accord_metrics_config,
    _write_adapter_specific_config,
    _write_location_config,
    _write_location_sharing_consent,
    _write_mobile_local_llm_config,
)


def _create_mock_setup(**kwargs):
    """Create a mock SetupCompleteRequest with given attributes."""
    mock = MagicMock()
    # Set defaults
    mock.enabled_adapters = kwargs.get("enabled_adapters", [])
    mock.llm_provider = kwargs.get("llm_provider", "openai")
    mock.llm_model = kwargs.get("llm_model", None)
    mock.adapter_config = kwargs.get("adapter_config", None)
    mock.location_city = kwargs.get("location_city", None)
    mock.location_region = kwargs.get("location_region", None)
    mock.location_country = kwargs.get("location_country", None)
    mock.location_latitude = kwargs.get("location_latitude", None)
    mock.location_longitude = kwargs.get("location_longitude", None)
    mock.timezone = kwargs.get("timezone", None)
    mock.share_location_in_traces = kwargs.get("share_location_in_traces", False)
    return mock


class TestWriteAccordMetricsConfig:
    """Tests for _write_accord_metrics_config function."""

    def test_writes_nothing_when_adapter_not_enabled(self) -> None:
        """Test that nothing is written when accord metrics adapter is not enabled."""
        f = StringIO()
        setup = _create_mock_setup(enabled_adapters=["api", "discord"])

        _write_accord_metrics_config(f, setup)

        assert f.getvalue() == ""

    def test_writes_consent_when_adapter_enabled(self) -> None:
        """Test that consent is written when accord metrics adapter is enabled."""
        f = StringIO()
        setup = _create_mock_setup(enabled_adapters=["ciris_accord_metrics"])

        _write_accord_metrics_config(f, setup)

        content = f.getvalue()
        assert "CIRIS_ACCORD_METRICS_CONSENT=true" in content
        assert "CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP=" in content
        assert "Accord Metrics Consent" in content


class TestWriteMobileLocalLlmConfig:
    """Tests for _write_mobile_local_llm_config function."""

    def test_writes_nothing_when_not_enabled(self) -> None:
        """Test that nothing is written when mobile_local_llm is not enabled."""
        f = StringIO()
        setup = _create_mock_setup(enabled_adapters=["api"], llm_provider="openai")

        _write_mobile_local_llm_config(f, setup)

        assert f.getvalue() == ""

    def test_writes_config_when_adapter_enabled(self) -> None:
        """Test config is written when mobile_local_llm adapter is enabled."""
        f = StringIO()
        setup = _create_mock_setup(enabled_adapters=["mobile_local_llm"])

        _write_mobile_local_llm_config(f, setup)

        content = f.getvalue()
        assert "CIRIS_MOBILE_LOCAL_LLM_ENABLED=true" in content
        assert "Mobile Local LLM" in content

    def test_writes_config_when_provider_is_mobile_local(self) -> None:
        """Test config is written when llm_provider is mobile_local."""
        f = StringIO()
        setup = _create_mock_setup(enabled_adapters=[], llm_provider="mobile_local")

        _write_mobile_local_llm_config(f, setup)

        content = f.getvalue()
        assert "CIRIS_MOBILE_LOCAL_LLM_ENABLED=true" in content

    def test_writes_model_when_provided(self) -> None:
        """Test that model is written when provided."""
        f = StringIO()
        setup = _create_mock_setup(enabled_adapters=["mobile_local_llm"], llm_model="gemma-4-e4b")

        _write_mobile_local_llm_config(f, setup)

        content = f.getvalue()
        assert 'CIRIS_MOBILE_LOCAL_LLM_MODEL="gemma-4-e4b"' in content

    def test_no_model_when_not_provided(self) -> None:
        """Test that model line is not written when not provided."""
        f = StringIO()
        setup = _create_mock_setup(enabled_adapters=["mobile_local_llm"], llm_model=None)

        _write_mobile_local_llm_config(f, setup)

        content = f.getvalue()
        assert "CIRIS_MOBILE_LOCAL_LLM_MODEL" not in content


class TestWriteAdapterSpecificConfig:
    """Tests for _write_adapter_specific_config function."""

    def test_writes_nothing_when_no_config(self) -> None:
        """Test that nothing is written when adapter_config is None."""
        f = StringIO()
        setup = _create_mock_setup(adapter_config=None)

        _write_adapter_specific_config(f, setup)

        assert f.getvalue() == ""

    def test_writes_nothing_when_empty_config(self) -> None:
        """Test that nothing is written when adapter_config is empty."""
        f = StringIO()
        setup = _create_mock_setup(adapter_config={})

        _write_adapter_specific_config(f, setup)

        assert f.getvalue() == ""

    def test_maps_home_assistant_keys(self) -> None:
        """Test that Home Assistant keys are properly mapped."""
        f = StringIO()
        setup = _create_mock_setup(
            adapter_config={
                "access_token": "test_token",
                "refresh_token": "refresh_token",
                "base_url": "http://homeassistant.local:8123",
                "client_id": "ciris_client",
            }
        )

        _write_adapter_specific_config(f, setup)

        content = f.getvalue()
        assert "HOME_ASSISTANT_TOKEN=test_token" in content
        assert "HOME_ASSISTANT_REFRESH_TOKEN=refresh_token" in content
        assert "HOME_ASSISTANT_URL=http://homeassistant.local:8123" in content
        assert "HOME_ASSISTANT_CLIENT_ID=ciris_client" in content

    def test_preserves_unmapped_keys(self) -> None:
        """Test that unmapped keys are preserved as-is."""
        f = StringIO()
        setup = _create_mock_setup(
            adapter_config={
                "custom_key": "custom_value",
            }
        )

        _write_adapter_specific_config(f, setup)

        content = f.getvalue()
        assert "custom_key=custom_value" in content


class TestWriteLocationConfig:
    """Tests for _write_location_config function."""

    def test_writes_nothing_when_no_location(self) -> None:
        """Test that nothing is written when no location fields are set."""
        f = StringIO()
        setup = _create_mock_setup()

        _write_location_config(f, setup)

        assert f.getvalue() == ""

    def test_writes_city_only(self) -> None:
        """Test writing city only."""
        f = StringIO()
        setup = _create_mock_setup(location_city="Seattle")

        _write_location_config(f, setup)

        content = f.getvalue()
        assert 'CIRIS_USER_CITY="Seattle"' in content
        assert "CIRIS_USER_REGION" not in content
        assert "CIRIS_USER_COUNTRY" not in content

    def test_writes_full_location(self) -> None:
        """Test writing full location with city, region, country."""
        f = StringIO()
        setup = _create_mock_setup(location_city="Seattle", location_region="WA", location_country="US")

        _write_location_config(f, setup)

        content = f.getvalue()
        assert 'CIRIS_USER_CITY="Seattle"' in content
        assert 'CIRIS_USER_REGION="WA"' in content
        assert 'CIRIS_USER_COUNTRY="US"' in content
        assert 'CIRIS_USER_LOCATION="Seattle, WA, US"' in content

    def test_writes_partial_location_display(self) -> None:
        """Test location display with partial info (no city)."""
        f = StringIO()
        setup = _create_mock_setup(location_region="WA", location_country="US")

        _write_location_config(f, setup)

        content = f.getvalue()
        assert 'CIRIS_USER_REGION="WA"' in content
        assert 'CIRIS_USER_COUNTRY="US"' in content
        assert 'CIRIS_USER_LOCATION="WA, US"' in content

    def test_writes_coordinates(self) -> None:
        """Test writing latitude and longitude."""
        f = StringIO()
        setup = _create_mock_setup(location_latitude=47.6062, location_longitude=-122.3321)

        _write_location_config(f, setup)

        content = f.getvalue()
        assert 'CIRIS_USER_LATITUDE="47.6062"' in content
        assert 'CIRIS_USER_LONGITUDE="-122.3321"' in content

    def test_writes_timezone(self) -> None:
        """Test writing timezone."""
        f = StringIO()
        setup = _create_mock_setup(timezone="America/Los_Angeles")

        _write_location_config(f, setup)

        content = f.getvalue()
        assert 'CIRIS_USER_TIMEZONE="America/Los_Angeles"' in content

    def test_zero_coordinates_are_written(self) -> None:
        """Test that zero coordinates are written (not treated as falsy)."""
        f = StringIO()
        setup = _create_mock_setup(location_latitude=0.0, location_longitude=0.0)

        _write_location_config(f, setup)

        content = f.getvalue()
        assert 'CIRIS_USER_LATITUDE="0.0"' in content
        assert 'CIRIS_USER_LONGITUDE="0.0"' in content


class TestWriteLocationSharingConsent:
    """Tests for _write_location_sharing_consent function."""

    def test_writes_nothing_when_not_sharing(self) -> None:
        """Test that nothing is written when share_location_in_traces is False."""
        f = StringIO()
        setup = _create_mock_setup(share_location_in_traces=False)

        _write_location_sharing_consent(f, setup)

        assert f.getvalue() == ""

    def test_writes_consent_when_sharing(self) -> None:
        """Test that consent is written when share_location_in_traces is True."""
        f = StringIO()
        setup = _create_mock_setup(share_location_in_traces=True)

        _write_location_sharing_consent(f, setup)

        content = f.getvalue()
        assert "CIRIS_SHARE_LOCATION_IN_TRACES=true" in content
        assert "CIRIS_LOCATION_CONSENT_TIMESTAMP=" in content
        assert "Location Data Sharing Consent" in content
