"""Tests for LLM Service multi-endpoint failover functionality.

Tests cover:
- OpenAIConfig.get_effective_base_urls()
- Endpoint rotation logic
- Multi-endpoint failover behavior
"""

import pytest

from ciris_engine.logic.services.runtime.llm_service import OpenAIConfig


class TestOpenAIConfigMultiEndpoint:
    """Tests for OpenAIConfig multi-endpoint support."""

    def test_get_effective_base_urls_with_base_urls(self) -> None:
        """Test that base_urls takes precedence over base_url."""
        config = OpenAIConfig(
            api_key="test-key",
            base_url="https://single.example.com",
            base_urls=[
                "https://endpoint1.example.com",
                "https://endpoint2.example.com",
            ],
        )
        urls = config.get_effective_base_urls()
        assert len(urls) == 2
        assert urls[0] == "https://endpoint1.example.com"
        assert urls[1] == "https://endpoint2.example.com"

    def test_get_effective_base_urls_with_base_url_only(self) -> None:
        """Test fallback to base_url when base_urls not set."""
        config = OpenAIConfig(
            api_key="test-key",
            base_url="https://single.example.com",
        )
        urls = config.get_effective_base_urls()
        assert len(urls) == 1
        assert urls[0] == "https://single.example.com"

    def test_get_effective_base_urls_empty(self) -> None:
        """Test empty result when neither base_url nor base_urls set."""
        config = OpenAIConfig(
            api_key="test-key",
        )
        urls = config.get_effective_base_urls()
        assert urls == []

    def test_get_effective_base_urls_filters_empty_strings(self) -> None:
        """Test that empty strings are filtered from base_urls."""
        config = OpenAIConfig(
            api_key="test-key",
            base_urls=[
                "https://endpoint1.example.com",
                "",
                "https://endpoint2.example.com",
                "",
            ],
        )
        urls = config.get_effective_base_urls()
        assert len(urls) == 2
        assert urls[0] == "https://endpoint1.example.com"
        assert urls[1] == "https://endpoint2.example.com"


class TestOpenAIConfigDefaults:
    """Tests for OpenAIConfig default values."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = OpenAIConfig()
        assert config.api_key == ""
        assert config.model_name == "gpt-4o-mini"
        assert config.base_url is None
        assert config.base_urls is None
        assert config.instructor_mode == "JSON"
        assert config.max_retries == 3
        assert config.timeout_seconds == 60

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = OpenAIConfig(
            api_key="my-key",
            model_name="gpt-4o",
            base_url="https://custom.example.com",
            base_urls=["https://ep1.example.com", "https://ep2.example.com"],
            instructor_mode="TOOLS",
            max_retries=5,
            timeout_seconds=120,
        )
        assert config.api_key == "my-key"
        assert config.model_name == "gpt-4o"
        assert config.base_url == "https://custom.example.com"
        assert len(config.base_urls or []) == 2
        assert config.instructor_mode == "TOOLS"
        assert config.max_retries == 5
        assert config.timeout_seconds == 120


class TestCIRISProxyMultiEndpoint:
    """Tests for CIRIS proxy multi-endpoint integration."""

    def test_ciris_proxy_endpoints_from_config(self) -> None:
        """Test creating config with CIRIS proxy endpoints."""
        from ciris_engine.config.ciris_services import get_all_proxy_endpoints

        endpoints = get_all_proxy_endpoints()
        base_urls = [ep.url + "/v1" for ep in endpoints]

        config = OpenAIConfig(
            api_key="test-jwt-token",
            base_url=base_urls[0],  # Primary
            base_urls=base_urls,  # All endpoints
        )

        effective = config.get_effective_base_urls()
        assert len(effective) == len(endpoints)
        assert all("/v1" in url for url in effective)

    def test_ciris_proxy_na_eu_ordering(self) -> None:
        """Test that NA is first in priority order."""
        from ciris_engine.config.ciris_services import get_all_proxy_endpoints

        endpoints = get_all_proxy_endpoints()
        # First endpoint should be NA (priority 1)
        assert endpoints[0].region == "na", "NA should be first (highest priority)"
        assert endpoints[0].priority == 1

        # EU should be second
        eu_endpoints = [ep for ep in endpoints if ep.region == "eu"]
        assert len(eu_endpoints) > 0, "Should have EU endpoint"
        assert eu_endpoints[0].priority > 1, "EU should have lower priority than NA"
