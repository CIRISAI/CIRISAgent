"""Tests for CIRIS hosted services URL configuration.

Tests cover:
- Multi-region endpoint configuration
- Service endpoint retrieval and ordering
- CIRIS proxy URL detection
- Hostname extraction
- Environment variable overrides
"""

import os
from unittest.mock import patch

import pytest

from ciris_engine.config.ciris_services import (
    ServiceEndpoint,
    get_all_proxy_endpoints,
    get_all_service_endpoints,
    get_billing_url,
    get_ciris_proxy_hostnames,
    get_proxy_url,
    is_ciris_proxy_url,
)


class TestServiceEndpoint:
    """Tests for ServiceEndpoint dataclass."""

    def test_service_endpoint_creation(self) -> None:
        """Test creating a ServiceEndpoint."""
        endpoint = ServiceEndpoint(
            url="https://llm01.ciris-services-1.ai",
            region="na",
            priority=1,
        )
        assert endpoint.url == "https://llm01.ciris-services-1.ai"
        assert endpoint.region == "na"
        assert endpoint.priority == 1

    def test_service_endpoint_str(self) -> None:
        """Test string representation of ServiceEndpoint."""
        endpoint = ServiceEndpoint(
            url="https://llm01.ciris-services-1.ai",
            region="na",
            priority=1,
        )
        assert "https://llm01.ciris-services-1.ai" in str(endpoint)
        assert "na" in str(endpoint)
        assert "priority=1" in str(endpoint)


class TestGetAllServiceEndpoints:
    """Tests for get_all_service_endpoints function."""

    def test_proxy_endpoints_sorted_by_priority(self) -> None:
        """Test that proxy endpoints are returned sorted by priority."""
        endpoints = get_all_service_endpoints("proxy")
        assert len(endpoints) >= 2, "Should have at least 2 proxy regions"
        # Verify sorted by priority (lower = higher priority)
        priorities = [ep.priority for ep in endpoints]
        assert priorities == sorted(priorities), "Endpoints should be sorted by priority"

    def test_billing_endpoints_exist(self) -> None:
        """Test that billing endpoints are available."""
        endpoints = get_all_service_endpoints("billing")
        assert len(endpoints) >= 1, "Should have at least 1 billing endpoint"

    def test_agents_endpoints_exist(self) -> None:
        """Test that agents endpoints are available."""
        endpoints = get_all_service_endpoints("agents")
        assert len(endpoints) >= 1, "Should have at least 1 agents endpoint"

    def test_lens_endpoints_exist(self) -> None:
        """Test that lens endpoints are available."""
        endpoints = get_all_service_endpoints("lens")
        assert len(endpoints) >= 1, "Should have at least 1 lens endpoint"

    def test_unknown_service_returns_empty(self) -> None:
        """Test that unknown service returns empty list."""
        # Using type: ignore because we're testing invalid input
        endpoints = get_all_service_endpoints("nonexistent")  # type: ignore
        assert endpoints == []


class TestGetAllProxyEndpoints:
    """Tests for get_all_proxy_endpoints convenience function."""

    def test_returns_same_as_get_all_service_endpoints(self) -> None:
        """Test that convenience function returns same results."""
        proxy_endpoints = get_all_proxy_endpoints()
        service_endpoints = get_all_service_endpoints("proxy")
        assert len(proxy_endpoints) == len(service_endpoints)
        for i, ep in enumerate(proxy_endpoints):
            assert ep.url == service_endpoints[i].url
            assert ep.region == service_endpoints[i].region

    def test_returns_multiple_regions(self) -> None:
        """Test that multiple regions are returned."""
        endpoints = get_all_proxy_endpoints()
        regions = {ep.region for ep in endpoints}
        assert len(regions) >= 2, "Should have at least 2 regions (na, eu)"


class TestIsCirisProxyUrl:
    """Tests for is_ciris_proxy_url function."""

    def test_detects_na_proxy_url(self) -> None:
        """Test detection of NA proxy URL."""
        assert is_ciris_proxy_url("https://llm01.ciris-services-1.ai")
        assert is_ciris_proxy_url("https://llm01.ciris-services-1.ai/")
        assert is_ciris_proxy_url("https://llm01.ciris-services-1.ai/v1")

    def test_detects_eu_proxy_url(self) -> None:
        """Test detection of EU proxy URL."""
        assert is_ciris_proxy_url("https://llm01.ciris-services-eu-1.com")
        assert is_ciris_proxy_url("https://llm01.ciris-services-eu-1.com/")
        assert is_ciris_proxy_url("https://llm01.ciris-services-eu-1.com/v1")

    def test_rejects_non_ciris_urls(self) -> None:
        """Test rejection of non-CIRIS URLs."""
        assert not is_ciris_proxy_url("https://api.openai.com")
        assert not is_ciris_proxy_url("https://openrouter.ai/api/v1")
        assert not is_ciris_proxy_url("http://localhost:11434/v1")

    def test_handles_empty_url(self) -> None:
        """Test handling of empty URL."""
        assert not is_ciris_proxy_url("")
        assert not is_ciris_proxy_url(None)  # type: ignore


class TestGetCirisProxyHostnames:
    """Tests for get_ciris_proxy_hostnames function."""

    def test_returns_hostnames(self) -> None:
        """Test that hostnames are extracted correctly."""
        hostnames = get_ciris_proxy_hostnames()
        assert len(hostnames) >= 2, "Should have at least 2 hostnames"
        # Check that these are actual hostnames (not full URLs)
        for hostname in hostnames:
            assert not hostname.startswith("http")
            assert "ciris-services" in hostname

    def test_unique_hostnames(self) -> None:
        """Test that hostnames are unique."""
        hostnames = get_ciris_proxy_hostnames()
        assert len(hostnames) == len(set(hostnames)), "Hostnames should be unique"


class TestGetProxyUrl:
    """Tests for get_proxy_url function."""

    def test_returns_primary_by_default(self) -> None:
        """Test that primary URL is returned by default."""
        url = get_proxy_url(use_fallback=False)
        assert url, "Should return a URL"
        assert "ciris-services" in url

    def test_returns_fallback_when_requested(self) -> None:
        """Test that fallback URL is returned when requested."""
        primary = get_proxy_url(use_fallback=False)
        fallback = get_proxy_url(use_fallback=True)
        # Primary and fallback should be different
        assert primary != fallback, "Primary and fallback should be different URLs"

    def test_env_override_takes_precedence(self) -> None:
        """Test that environment variable overrides config."""
        custom_url = "https://custom-proxy.example.com"
        with patch.dict(os.environ, {"CIRIS_PROXY_URL": custom_url}):
            url = get_proxy_url(use_fallback=False)
            assert url == custom_url

    def test_env_override_ignored_for_fallback(self) -> None:
        """Test that env override is ignored when requesting fallback."""
        custom_url = "https://custom-proxy.example.com"
        with patch.dict(os.environ, {"CIRIS_PROXY_URL": custom_url}):
            url = get_proxy_url(use_fallback=True)
            # Should return the config fallback, not the env override
            assert url != custom_url
            assert "ciris-services" in url


class TestGetBillingUrl:
    """Tests for get_billing_url function."""

    def test_returns_billing_url(self) -> None:
        """Test that billing URL is returned."""
        url = get_billing_url()
        assert url, "Should return a URL"
        assert "billing" in url or "ciris-services" in url

    def test_env_override_ciris_billing_api_url(self) -> None:
        """Test CIRIS_BILLING_API_URL environment override."""
        custom_url = "https://custom-billing.example.com"
        with patch.dict(os.environ, {"CIRIS_BILLING_API_URL": custom_url}):
            url = get_billing_url(use_fallback=False)
            assert url == custom_url

    def test_env_override_ciris_billing_url(self) -> None:
        """Test CIRIS_BILLING_URL environment override (backward compat)."""
        custom_url = "https://custom-billing.example.com"
        with patch.dict(os.environ, {"CIRIS_BILLING_URL": custom_url}):
            url = get_billing_url(use_fallback=False)
            assert url == custom_url


class TestMultiEndpointIntegration:
    """Integration tests for multi-endpoint support."""

    def test_endpoint_list_matches_config(self) -> None:
        """Test that endpoint list matches JSON config structure."""
        endpoints = get_all_proxy_endpoints()
        # Verify we have NA and EU regions
        regions = {ep.region for ep in endpoints}
        assert "na" in regions, "Should have NA region"
        assert "eu" in regions, "Should have EU region"

    def test_priority_ordering_na_before_eu(self) -> None:
        """Test that NA has higher priority (lower number) than EU."""
        endpoints = get_all_proxy_endpoints()
        na_priority = next((ep.priority for ep in endpoints if ep.region == "na"), 999)
        eu_priority = next((ep.priority for ep in endpoints if ep.region == "eu"), 999)
        assert na_priority < eu_priority, "NA should have higher priority than EU"

    def test_endpoints_have_valid_urls(self) -> None:
        """Test that all endpoints have valid HTTPS URLs."""
        endpoints = get_all_proxy_endpoints()
        for ep in endpoints:
            assert ep.url.startswith("https://"), f"Endpoint should use HTTPS: {ep.url}"
            assert "ciris-services" in ep.url, f"Should be CIRIS URL: {ep.url}"
