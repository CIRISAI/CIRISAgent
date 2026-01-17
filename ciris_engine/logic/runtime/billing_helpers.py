"""
Billing provider helpers for CIRISRuntime.

Handles billing provider initialization, token refresh, and LLM service token management
for CIRIS proxy authentication.
"""

import logging
import os
from typing import Any, Callable, Optional

from ciris_engine.config.ciris_services import get_billing_url
from ciris_engine.schemas.runtime.enums import ServiceType

logger = logging.getLogger(__name__)

# Domain identifiers for CIRIS proxy services (LLM, billing)
# Includes legacy ciris.ai and new ciris-services infrastructure
CIRIS_PROXY_DOMAINS = ("ciris.ai", "ciris-services")


def is_using_ciris_proxy() -> bool:
    """Check if runtime is configured to use CIRIS proxy."""
    llm_base_url = os.getenv("OPENAI_API_BASE", "")
    return any(domain in llm_base_url for domain in CIRIS_PROXY_DOMAINS)


def create_billing_token_handler(credit_provider: Any) -> Callable[..., Any]:
    """Create handler for billing token refresh signals."""

    async def handle_billing_token_refreshed(signal: str, resource: str) -> None:
        new_token = os.getenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "")
        if new_token and credit_provider:
            credit_provider.update_google_id_token(new_token)
            logger.info("Updated billing provider with refreshed Google ID token")

    return handle_billing_token_refreshed


def create_llm_token_handler(runtime: Any) -> Callable[..., Any]:
    """Create handler for LLM service token refresh signals."""

    async def handle_llm_token_refreshed(signal: str, resource: str) -> None:
        new_token = os.getenv("OPENAI_API_KEY", "")
        if not new_token:
            logger.warning("[LLM_TOKEN] No OPENAI_API_KEY in env after token refresh")
            return

        update_llm_services_token(runtime, new_token)

    return handle_llm_token_refreshed


def update_llm_services_token(runtime: Any, new_token: str) -> None:
    """Update all LLM services that use CIRIS proxy with new token."""
    if runtime.service_registry:
        llm_services = runtime.service_registry.get_services_by_type(ServiceType.LLM)
        for service in llm_services:
            update_service_token_if_ciris_proxy(service, new_token)

    if runtime.llm_service:
        update_service_token_if_ciris_proxy(runtime.llm_service, new_token, is_primary=True)


def update_service_token_if_ciris_proxy(service: Any, new_token: str, is_primary: bool = False) -> None:
    """Update a service's API key if it uses CIRIS proxy."""
    if not hasattr(service, "openai_config") or not service.openai_config:
        return
    if not hasattr(service, "update_api_key"):
        return

    base_url = getattr(service.openai_config, "base_url", "") or ""
    if not any(domain in base_url for domain in CIRIS_PROXY_DOMAINS):
        return

    service.update_api_key(new_token)
    label = "primary LLM service" if is_primary else type(service).__name__
    logger.info(f"Updated {label} with refreshed token")


def get_resource_monitor_for_billing(runtime: Any) -> Optional[Any]:
    """Get resource monitor service for billing initialization.

    Returns the resource monitor service or None if not available.
    Uses Any type since we access implementation-specific attributes
    (credit_provider, signal_bus) not in the protocol.
    """
    if not runtime.service_initializer:
        logger.warning("Cannot reinitialize billing - service_initializer not available")
        return None

    resource_monitor = runtime.service_initializer.resource_monitor_service
    if not resource_monitor:
        logger.warning("Cannot reinitialize billing - resource_monitor_service not available")
        return None

    return resource_monitor


def create_billing_provider(google_id_token: str) -> Any:
    """Create and configure the CIRIS billing provider."""
    from ciris_engine.logic.services.infrastructure.resource_monitor import CIRISBillingProvider

    base_url = get_billing_url()
    timeout = float(os.getenv("CIRIS_BILLING_TIMEOUT_SECONDS", "5.0"))
    cache_ttl = int(os.getenv("CIRIS_BILLING_CACHE_TTL_SECONDS", "15"))
    fail_open = os.getenv("CIRIS_BILLING_FAIL_OPEN", "false").lower() == "true"

    def get_fresh_token() -> str:
        return os.getenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "")

    return CIRISBillingProvider(
        google_id_token=google_id_token,
        token_refresh_callback=get_fresh_token,
        base_url=base_url,
        timeout_seconds=timeout,
        cache_ttl_seconds=cache_ttl,
        fail_open=fail_open,
    )


async def reinitialize_billing_provider(runtime: Any) -> None:
    """Reinitialize billing provider after setup completes.

    Called during resume_from_first_run to set up billing now that
    environment variables (OPENAI_API_BASE, CIRIS_BILLING_GOOGLE_ID_TOKEN)
    are available from the newly created .env file.
    """
    resource_monitor = get_resource_monitor_for_billing(runtime)
    if not resource_monitor:
        return

    is_android = "ANDROID_DATA" in os.environ
    using_ciris_proxy = is_using_ciris_proxy()

    logger.info(f"Billing provider check: is_android={is_android}, using_ciris_proxy={using_ciris_proxy}")
    logger.info(f"  OPENAI_API_BASE={os.getenv('OPENAI_API_BASE', '')}")

    if not (is_android and using_ciris_proxy):
        logger.info("Billing provider not needed (not using CIRIS proxy or not Android)")
        return

    google_id_token = os.getenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "")
    if not google_id_token:
        logger.warning("Android using CIRIS LLM proxy without Google ID token - billing provider not configured")
        return

    credit_provider = create_billing_provider(google_id_token)
    resource_monitor.credit_provider = credit_provider

    # Register token refresh handlers
    resource_monitor.signal_bus.register("token_refreshed", create_billing_token_handler(credit_provider))
    logger.info("Reinitialized CIRISBillingProvider with JWT auth (CIRIS LLM proxy)")
    logger.info("Registered token_refreshed handler for billing provider")

    resource_monitor.signal_bus.register("token_refreshed", create_llm_token_handler(runtime))
    logger.info("Registered token_refreshed handler for LLM service")
