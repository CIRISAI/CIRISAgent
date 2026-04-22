"""LLM Provider Persistence - CRUD operations for runtime LLM providers.

Provides helpers to persist LLM provider configurations to:
1. GraphConfigService (graph database) - primary persistence for runtime providers

Standard .env env vars (OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL) are used
for bootstrap only and are managed separately by the setup wizard.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Config key used in GraphConfigService
RUNTIME_PROVIDERS_CONFIG_KEY = "runtime_llm_providers"

# Env var name for disabling CIRIS services
CIRIS_SERVICES_DISABLED_VAR = "CIRIS_SERVICES_DISABLED"

# Maximum number of providers allowed
MAX_PROVIDERS = 5


class LLMProviderConfig(BaseModel):
    """Configuration for a runtime LLM provider."""

    provider_id: str = Field(..., description="Provider type (e.g., 'local', 'openai', 'anthropic')")
    base_url: str = Field(..., description="API base URL")
    model: str = Field(default="default", description="Model name")
    api_key: str = Field(default="", description="API key (empty for local)")
    priority: str = Field(default="fallback", description="Priority level")
    enabled: bool = Field(default=True, description="Whether this provider is enabled")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for persistence."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMProviderConfig":
        """Create from dict."""
        return cls(**data)


@dataclass
class PersistenceResult:
    """Result of a persistence operation."""

    success: bool
    graph_persisted: bool = False
    env_persisted: bool = False
    error: Optional[str] = None


# =============================================================================
# .env File Operations (for bootstrap env vars only)
# =============================================================================


def _get_env_path() -> Optional[Path]:
    """Get the .env file path."""
    try:
        from ciris_engine.logic.setup.first_run import get_default_config_path

        return get_default_config_path()
    except Exception as e:
        logger.warning(f"Could not determine .env path: {e}")
        return None


def _transform_local_provider_line(line: str) -> str:
    """Transform a line for local provider deletion.

    Clears all env vars that could create a local LLM provider:
    - CIRIS_MOBILE_LOCAL_LLM_ENABLED -> false
    - OPENAI_API_BASE with localhost/127.0.0.1 -> commented out
    - OPENAI_API_KEY when "local" -> commented out
    - OPENAI_MODEL -> commented out (if other local vars present)
    - NEXT_PUBLIC_API_BASE_URL with localhost -> commented out
    """
    stripped = line.strip()
    # Already commented
    if stripped.startswith("#"):
        return line
    # Disable mobile local LLM
    if stripped.startswith("CIRIS_MOBILE_LOCAL_LLM_ENABLED="):
        return "CIRIS_MOBILE_LOCAL_LLM_ENABLED=false"
    # Comment out local OpenAI-compatible server config
    if stripped.startswith("OPENAI_API_BASE="):
        if "localhost" in stripped.lower() or "127.0.0.1" in stripped:
            return f"# {line}  # Disabled by provider deletion"
    if stripped.startswith("OPENAI_API_KEY="):
        # "local" is a placeholder key for local servers
        if '="local"' in stripped or "='local'" in stripped:
            return f"# {line}  # Disabled by provider deletion"
    if stripped.startswith("OPENAI_MODEL="):
        # Comment out model when clearing local provider
        return f"# {line}  # Disabled by provider deletion"
    if stripped.startswith("NEXT_PUBLIC_API_BASE_URL=") and "localhost" in stripped.lower():
        return f"# {line}  # Disabled by provider deletion"
    return line


def _transform_cloud_provider_line(line: str) -> str:
    """Transform a line for cloud provider deletion."""
    stripped = line.strip()
    if stripped.startswith("NEXT_PUBLIC_API_BASE_URL=") and "localhost" not in stripped.lower():
        return f"# {line}  # Disabled by provider deletion"
    return line


def clear_primary_provider_env_vars(is_local: bool = False) -> bool:
    """Clear env vars that create the primary LLM provider on startup.

    This is called when deleting local_primary or ciris_primary to ensure
    the provider is not re-created on next restart.

    Args:
        is_local: If True, clear local provider vars (CIRIS_MOBILE_LOCAL_LLM_ENABLED).
                  If False, clear cloud provider vars (NEXT_PUBLIC_API_BASE_URL).

    Returns:
        True if successfully updated
    """
    env_path = _get_env_path()
    if not env_path or not env_path.exists():
        logger.warning("Cannot clear primary provider env vars - .env not found")
        return False

    try:
        content = env_path.read_text()
        lines = content.splitlines()

        transform_fn = _transform_local_provider_line if is_local else _transform_cloud_provider_line
        new_lines = [transform_fn(line) for line in lines]

        provider_type = "local" if is_local else "cloud"
        logger.info(f"Cleared {provider_type} primary provider env vars")

        env_path.write_text("\n".join(new_lines) + "\n")
        return True

    except Exception as e:
        logger.warning(f"Failed to clear primary provider env vars: {e}")
        return False


def set_ciris_services_disabled(disabled: bool) -> bool:
    """Set CIRIS_SERVICES_DISABLED flag in .env file.

    Args:
        disabled: True to disable CIRIS services, False to re-enable

    Returns:
        True if successfully persisted
    """
    env_path = _get_env_path()
    if not env_path:
        logger.warning("Cannot set CIRIS services disabled - .env path unknown")
        return False

    if not env_path.exists():
        logger.warning("Cannot set CIRIS services disabled - .env not found")
        return False

    try:
        # Read existing content
        content = env_path.read_text()
        lines = content.splitlines()

        # Remove existing CIRIS_SERVICES_DISABLED line
        new_lines = [line for line in lines if not line.strip().startswith(f"{CIRIS_SERVICES_DISABLED_VAR}=")]

        # Add new line
        value = "true" if disabled else "false"
        new_lines.append(f"{CIRIS_SERVICES_DISABLED_VAR}={value}")

        # Write back
        env_path.write_text("\n".join(new_lines) + "\n")
        logger.info(f"Set CIRIS_SERVICES_DISABLED={value} in .env")
        return True

    except Exception as e:
        logger.warning(f"Failed to set CIRIS services disabled in .env: {e}")
        return False


def get_ciris_services_disabled() -> bool:
    """Check if CIRIS services are disabled.

    Returns:
        True if CIRIS services are disabled
    """
    import os

    return os.environ.get(CIRIS_SERVICES_DISABLED_VAR, "").lower() in ("true", "1", "yes")


# =============================================================================
# Graph Config Operations (Primary Persistence)
# =============================================================================


async def read_providers_from_graph(config_service: Any) -> dict[str, LLMProviderConfig]:
    """Read runtime LLM providers from GraphConfigService.

    Args:
        config_service: GraphConfigService instance

    Returns:
        Dict mapping provider_name -> LLMProviderConfig
    """
    if not config_service:
        return {}

    try:
        existing_config = await config_service.get_config(RUNTIME_PROVIDERS_CONFIG_KEY)
        if existing_config and existing_config.value.dict_value:
            data = dict(existing_config.value.dict_value)
            return {name: LLMProviderConfig.from_dict(config) for name, config in data.items()}
        return {}
    except Exception as e:
        logger.warning(f"Failed to read runtime providers from graph: {e}")
        return {}


async def write_providers_to_graph(
    config_service: Any,
    providers: dict[str, LLMProviderConfig],
    updated_by: str = "llm_provider_crud",
) -> bool:
    """Write runtime LLM providers to GraphConfigService.

    Args:
        config_service: GraphConfigService instance
        providers: Dict mapping provider_name -> LLMProviderConfig
        updated_by: Attribution for the update

    Returns:
        True if successfully persisted
    """
    if not config_service:
        logger.warning("Cannot persist to graph - config_service not available")
        return False

    try:
        providers_dict = {name: cfg.to_dict() for name, cfg in providers.items()}
        await config_service.set_config(
            key=RUNTIME_PROVIDERS_CONFIG_KEY,
            value=providers_dict,
            updated_by=updated_by,
        )
        logger.info(f"Persisted {len(providers)} runtime LLM provider(s) to graph")
        return True
    except Exception as e:
        logger.warning(f"Failed to persist runtime providers to graph: {e}")
        return False


# =============================================================================
# CRUD Operations (Graph-based)
# =============================================================================


async def list_providers(config_service: Optional[Any] = None) -> dict[str, LLMProviderConfig]:
    """List all persisted runtime LLM providers.

    Args:
        config_service: Optional GraphConfigService instance

    Returns:
        Dict mapping provider_name -> LLMProviderConfig
    """
    if config_service:
        return await read_providers_from_graph(config_service)
    return {}


async def get_provider(name: str, config_service: Optional[Any] = None) -> Optional[LLMProviderConfig]:
    """Get a specific provider by name.

    Args:
        name: Provider name
        config_service: Optional GraphConfigService instance

    Returns:
        LLMProviderConfig if found, None otherwise
    """
    providers = await list_providers(config_service)
    return providers.get(name)


async def create_provider(
    name: str,
    config: LLMProviderConfig,
    config_service: Optional[Any] = None,
) -> PersistenceResult:
    """Create a new runtime LLM provider.

    Args:
        name: Provider name (unique identifier)
        config: Provider configuration
        config_service: Optional GraphConfigService instance

    Returns:
        PersistenceResult with success status
    """
    # Load existing providers
    providers = await list_providers(config_service)

    # Check if already exists
    if name in providers:
        return PersistenceResult(success=False, error=f"Provider '{name}' already exists")

    # Check limit
    if len(providers) >= MAX_PROVIDERS:
        return PersistenceResult(
            success=False,
            error=f"Maximum of {MAX_PROVIDERS} providers allowed. Remove one first.",
        )

    # Add new provider
    providers[name] = config

    # Persist to graph
    graph_ok = await write_providers_to_graph(config_service, providers)

    return PersistenceResult(
        success=graph_ok,
        graph_persisted=graph_ok,
    )


async def update_provider(
    name: str,
    config: LLMProviderConfig,
    config_service: Optional[Any] = None,
) -> PersistenceResult:
    """Update an existing runtime LLM provider.

    Args:
        name: Provider name
        config: New provider configuration
        config_service: Optional GraphConfigService instance

    Returns:
        PersistenceResult with success status
    """
    # Load existing providers
    providers = await list_providers(config_service)

    # Check if exists
    if name not in providers:
        return PersistenceResult(success=False, error=f"Provider '{name}' not found")

    # Update provider
    providers[name] = config

    # Persist to graph
    graph_ok = await write_providers_to_graph(config_service, providers)

    return PersistenceResult(
        success=graph_ok,
        graph_persisted=graph_ok,
    )


async def delete_provider(
    name: str,
    config_service: Optional[Any] = None,
) -> PersistenceResult:
    """Delete a runtime LLM provider.

    Args:
        name: Provider name
        config_service: Optional GraphConfigService instance

    Returns:
        PersistenceResult with success status
    """
    # Load existing providers
    providers = await list_providers(config_service)

    if name not in providers:
        # Also try to clear legacy env vars for known provider names
        if name == "local_primary" or "local" in name.lower():
            clear_primary_provider_env_vars(is_local=True)
            return PersistenceResult(success=True, env_persisted=True)
        elif name == "ciris_primary" or "ciris" in name.lower():
            clear_primary_provider_env_vars(is_local=False)
            return PersistenceResult(success=True, env_persisted=True)
        return PersistenceResult(
            success=False,
            error=f"Provider '{name}' not found",
        )

    # Remove provider
    del providers[name]

    # Persist to graph
    graph_ok = await write_providers_to_graph(config_service, providers)

    # Also clear legacy env vars for known provider names
    if name == "local_primary" or "local" in name.lower():
        clear_primary_provider_env_vars(is_local=True)
    elif name == "ciris_primary" or "ciris" in name.lower():
        clear_primary_provider_env_vars(is_local=False)

    return PersistenceResult(
        success=graph_ok,
        graph_persisted=graph_ok,
    )


async def upsert_provider(
    name: str,
    config: LLMProviderConfig,
    config_service: Optional[Any] = None,
) -> PersistenceResult:
    """Create or update a runtime LLM provider.

    Args:
        name: Provider name
        config: Provider configuration
        config_service: Optional GraphConfigService instance

    Returns:
        PersistenceResult with success status
    """
    # Load existing providers
    providers = await list_providers(config_service)

    # Check limit if adding new
    if name not in providers and len(providers) >= MAX_PROVIDERS:
        return PersistenceResult(
            success=False,
            error=f"Maximum of {MAX_PROVIDERS} providers allowed. Remove one first.",
        )

    # Add/update provider
    providers[name] = config

    # Persist to graph
    graph_ok = await write_providers_to_graph(config_service, providers)

    return PersistenceResult(
        success=graph_ok,
        graph_persisted=graph_ok,
    )


async def clear_all_providers(
    config_service: Optional[Any] = None,
) -> PersistenceResult:
    """Remove all runtime LLM providers.

    Args:
        config_service: Optional GraphConfigService instance

    Returns:
        PersistenceResult with success status
    """
    empty_providers: dict[str, LLMProviderConfig] = {}

    graph_ok = await write_providers_to_graph(config_service, empty_providers)

    return PersistenceResult(
        success=graph_ok,
        graph_persisted=graph_ok,
    )


async def get_enabled_providers(
    config_service: Optional[Any] = None,
) -> dict[str, LLMProviderConfig]:
    """Get only enabled providers.

    Args:
        config_service: Optional GraphConfigService instance

    Returns:
        Dict of enabled providers
    """
    providers = await list_providers(config_service)
    return {name: cfg for name, cfg in providers.items() if cfg.enabled}


async def disable_provider(
    name: str,
    config_service: Optional[Any] = None,
) -> PersistenceResult:
    """Disable a provider without removing it.

    Args:
        name: Provider name to disable
        config_service: Optional GraphConfigService instance

    Returns:
        PersistenceResult with success status
    """
    providers = await list_providers(config_service)

    if name not in providers:
        return PersistenceResult(
            success=False,
            error=f"Provider '{name}' not found",
        )

    providers[name].enabled = False

    graph_ok = await write_providers_to_graph(config_service, providers)
    logger.info(f"Disabled provider '{name}'")

    return PersistenceResult(
        success=graph_ok,
        graph_persisted=graph_ok,
    )


# =============================================================================
# Adapter Enable/Disable Persistence (CIRIS_ADAPTER)
# =============================================================================
# Manages the CIRIS_ADAPTER env var to enable/disable adapters persistently.

CIRIS_ADAPTER_VAR = "CIRIS_ADAPTER"


def read_enabled_adapters_from_env() -> list[str]:
    """Read enabled adapter list from CIRIS_ADAPTER env var.

    Returns:
        List of enabled adapter names
    """
    env_path = _get_env_path()
    if not env_path or not env_path.exists():
        return []

    try:
        content = env_path.read_text()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith(f"{CIRIS_ADAPTER_VAR}="):
                value = line[len(f"{CIRIS_ADAPTER_VAR}=") :]
                # Remove surrounding quotes
                if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
                    value = value[1:-1]
                if value:
                    return [a.strip() for a in value.split(",") if a.strip()]
        return []
    except Exception as e:
        logger.warning(f"Failed to read enabled adapters from env: {e}")
        return []


def write_enabled_adapters_to_env(adapters: list[str]) -> bool:
    """Write enabled adapter list to CIRIS_ADAPTER env var.

    Args:
        adapters: List of adapter names to enable

    Returns:
        True if successfully written
    """
    env_path = _get_env_path()
    if not env_path:
        logger.warning("Cannot write adapters - .env path unknown")
        return False

    try:
        if env_path.exists():
            content = env_path.read_text()
            lines = content.splitlines()
        else:
            lines = []

        # Remove existing CIRIS_ADAPTER line
        new_lines = [line for line in lines if not line.strip().startswith(f"{CIRIS_ADAPTER_VAR}=")]

        # Add new line
        adapters_str = ",".join(adapters)
        new_lines.append(f"{CIRIS_ADAPTER_VAR}={adapters_str}")

        env_path.write_text("\n".join(new_lines) + "\n")
        logger.info(f"Wrote {len(adapters)} adapters to {CIRIS_ADAPTER_VAR}")
        return True

    except Exception as e:
        logger.warning(f"Failed to write adapters to env: {e}")
        return False


def disable_adapter_in_env(adapter_name: str) -> bool:
    """Remove an adapter from the enabled list in .env.

    Args:
        adapter_name: Name of adapter to disable

    Returns:
        True if successfully disabled
    """
    adapters = read_enabled_adapters_from_env()

    if adapter_name not in adapters:
        logger.info(f"Adapter '{adapter_name}' already disabled")
        return True

    adapters.remove(adapter_name)
    result = write_enabled_adapters_to_env(adapters)

    if result:
        logger.info(f"Disabled adapter '{adapter_name}' in env")
    return result


def enable_adapter_in_env(adapter_name: str) -> bool:
    """Add an adapter to the enabled list in .env.

    Args:
        adapter_name: Name of adapter to enable

    Returns:
        True if successfully enabled
    """
    adapters = read_enabled_adapters_from_env()

    if adapter_name in adapters:
        logger.info(f"Adapter '{adapter_name}' already enabled")
        return True

    adapters.append(adapter_name)
    result = write_enabled_adapters_to_env(adapters)

    if result:
        logger.info(f"Enabled adapter '{adapter_name}' in env")
    return result
