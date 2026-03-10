"""
CIRIS Hosted Services URL Configuration.

Centralized configuration for CIRIS infrastructure URLs (proxy, billing, agents, lens).
All code that needs CIRIS service URLs should import from this module.

Supports X regions with Y endpoints each. The configuration uses a regions-based structure:
{
    "proxy": {
        "regions": [
            {"name": "na", "endpoints": ["https://..."], "priority": 1},
            {"name": "eu", "endpoints": ["https://..."], "priority": 2}
        ]
    }
}

Environment variable overrides:
- CIRIS_PROXY_URL: Override primary proxy URL
- CIRIS_BILLING_URL: Override primary billing URL (also: CIRIS_BILLING_API_URL for backward compat)
- CIRIS_AGENTS_URL: Override primary agents URL
- CIRIS_LENS_URL: Override primary lens URL
"""

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

ServiceType = Literal["proxy", "billing", "agents", "lens"]

# Type for the config structure
_ConfigType = Dict[str, Any]


@dataclass
class ServiceEndpoint:
    """Represents a single service endpoint with metadata."""

    url: str
    region: str
    priority: int

    def __str__(self) -> str:
        return f"{self.url} ({self.region}, priority={self.priority})"


@lru_cache(maxsize=1)
def _load_config() -> _ConfigType:
    """Load the CIRIS services configuration from JSON."""
    config_path = Path(__file__).parent / "CIRIS_SERVICES.json"
    with open(config_path) as f:
        result: _ConfigType = json.load(f)
        return result


def get_all_service_endpoints(service: ServiceType) -> List[ServiceEndpoint]:
    """Get all endpoints for a service across all regions, sorted by priority.

    This is the primary API for getting CIRIS service endpoints. It returns
    all endpoints in priority order, allowing the caller to implement
    failover logic.

    Args:
        service: The service type ("proxy", "billing", "agents", "lens")

    Returns:
        List of ServiceEndpoint objects sorted by priority (lowest first)

    Example:
        >>> endpoints = get_all_service_endpoints("proxy")
        >>> for ep in endpoints:
        ...     print(f"{ep.region}: {ep.url}")
        na: https://llm01.ciris-services-1.ai
        eu: https://llm01.ciris-services-eu-1.com
    """
    config = _load_config()
    service_config = config.get(service, {})
    regions = service_config.get("regions", [])

    endpoints: List[ServiceEndpoint] = []
    for region in regions:
        region_name = region.get("name", "unknown")
        priority = region.get("priority", 99)
        for url in region.get("endpoints", []):
            endpoints.append(ServiceEndpoint(url=url, region=region_name, priority=priority))

    # Sort by priority (lower = higher priority)
    endpoints.sort(key=lambda ep: ep.priority)
    return endpoints


def get_all_proxy_endpoints() -> List[ServiceEndpoint]:
    """Get all proxy endpoints across all regions, sorted by priority.

    Convenience function for the most common use case.

    Returns:
        List of ServiceEndpoint objects for the proxy service
    """
    return get_all_service_endpoints("proxy")


def get_service_url(service: ServiceType, use_fallback: bool = False) -> str:
    """Get the URL for a CIRIS service (legacy API, uses first/second endpoint).

    Args:
        service: The service type ("proxy", "billing", "agents", "lens")
        use_fallback: If True, return the second-priority URL instead of primary

    Returns:
        The service URL string

    Note:
        Prefer using get_all_service_endpoints() for new code to support
        proper multi-region failover.
    """
    endpoints = get_all_service_endpoints(service)
    if not endpoints:
        # Fallback to legacy config
        config = _load_config()
        legacy = config.get(service, {}).get("_legacy", {})
        return str(legacy.get("fallback" if use_fallback else "primary", ""))

    if use_fallback and len(endpoints) > 1:
        return endpoints[1].url
    return endpoints[0].url if endpoints else ""


def is_ciris_proxy_url(url: str) -> bool:
    """Check if a URL is a CIRIS proxy endpoint.

    Useful for determining if a configured LLM endpoint is part of
    the CIRIS infrastructure (and thus shares auth/failover) or is
    a completely different provider.

    Args:
        url: The URL to check

    Returns:
        True if the URL is a known CIRIS proxy endpoint
    """
    if not url:
        return False

    # Get all known CIRIS proxy URLs
    endpoints = get_all_proxy_endpoints()
    known_urls = {ep.url.rstrip("/") for ep in endpoints}

    # Normalize the input URL
    normalized = url.rstrip("/")
    # Also check without /v1 suffix
    if normalized.endswith("/v1"):
        normalized_base = normalized[:-3]
    else:
        normalized_base = normalized

    return normalized in known_urls or normalized_base in known_urls


def get_ciris_proxy_hostnames() -> List[str]:
    """Get all CIRIS proxy hostnames for URL matching.

    Returns:
        List of hostname strings (e.g., ["ciris-services-1.ai", "ciris-services-eu-1.com"])
    """
    from urllib.parse import urlparse

    endpoints = get_all_proxy_endpoints()
    hostnames = set()
    for ep in endpoints:
        parsed = urlparse(ep.url)
        if parsed.hostname:
            hostnames.add(parsed.hostname)
    return list(hostnames)


def get_proxy_url(use_fallback: bool = False) -> str:
    """Get the CIRIS LLM proxy URL.

    Checks CIRIS_PROXY_URL environment variable first, then falls back to config.
    """
    env_url = os.environ.get("CIRIS_PROXY_URL")
    if env_url and not use_fallback:
        return env_url
    return get_service_url("proxy", use_fallback)


def get_billing_url(use_fallback: bool = False) -> str:
    """Get the CIRIS billing service URL.

    Checks CIRIS_BILLING_API_URL and CIRIS_BILLING_URL environment variables first,
    then falls back to config.
    """
    # Check both env vars for backward compatibility
    env_url = os.environ.get("CIRIS_BILLING_API_URL") or os.environ.get("CIRIS_BILLING_URL")
    if env_url and not use_fallback:
        return env_url
    return get_service_url("billing", use_fallback)


def get_agents_url(use_fallback: bool = False) -> str:
    """Get the CIRIS agents service URL.

    Checks CIRIS_AGENTS_URL environment variable first, then falls back to config.
    """
    env_url = os.environ.get("CIRIS_AGENTS_URL")
    if env_url and not use_fallback:
        return env_url
    return get_service_url("agents", use_fallback)


def get_lens_url(use_fallback: bool = False) -> str:
    """Get the CIRIS lens service URL.

    Checks CIRIS_LENS_URL environment variable first, then falls back to config.
    """
    env_url = os.environ.get("CIRIS_LENS_URL")
    if env_url and not use_fallback:
        return env_url
    return get_service_url("lens", use_fallback)


# Convenience constants for import (primary URLs)
DEFAULT_PROXY_URL = get_proxy_url(use_fallback=False)
FALLBACK_PROXY_URL = get_proxy_url(use_fallback=True)
DEFAULT_BILLING_URL = get_billing_url(use_fallback=False)
FALLBACK_BILLING_URL = get_billing_url(use_fallback=True)


__all__ = [
    "get_service_url",
    "get_proxy_url",
    "get_billing_url",
    "get_agents_url",
    "get_lens_url",
    "DEFAULT_PROXY_URL",
    "FALLBACK_PROXY_URL",
    "DEFAULT_BILLING_URL",
    "FALLBACK_BILLING_URL",
]
