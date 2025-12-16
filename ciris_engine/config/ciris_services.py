"""
CIRIS Hosted Services URL Configuration.

Centralized configuration for CIRIS infrastructure URLs (proxy, billing, agents, lens).
All code that needs CIRIS service URLs should import from this module.

Environment variable overrides:
- CIRIS_PROXY_URL: Override primary proxy URL
- CIRIS_BILLING_URL: Override primary billing URL (also: CIRIS_BILLING_API_URL for backward compat)
- CIRIS_AGENTS_URL: Override primary agents URL
- CIRIS_LENS_URL: Override primary lens URL
"""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Literal

ServiceType = Literal["proxy", "billing", "agents", "lens"]

# Type for the config structure
_ConfigType = Dict[str, Dict[str, str]]


@lru_cache(maxsize=1)
def _load_config() -> _ConfigType:
    """Load the CIRIS services configuration from JSON."""
    config_path = Path(__file__).parent / "CIRIS_SERVICES.json"
    with open(config_path) as f:
        result: _ConfigType = json.load(f)
        return result


def get_service_url(service: ServiceType, use_fallback: bool = False) -> str:
    """Get the URL for a CIRIS service.

    Args:
        service: The service type ("proxy", "billing", "agents", "lens")
        use_fallback: If True, return the EU fallback URL instead of primary

    Returns:
        The service URL string
    """
    config = _load_config()
    endpoint = "fallback" if use_fallback else "primary"
    return str(config[service][endpoint])


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
