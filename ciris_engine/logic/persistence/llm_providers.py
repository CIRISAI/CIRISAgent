"""LLM Provider Persistence - CRUD operations for runtime LLM providers.

Provides helpers to persist LLM provider configurations to both:
1. GraphConfigService (graph database)
2. .env file (RUNTIME_LLM_PROVIDERS_JSON)

This enables runtime-added providers to survive restarts.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Config key used in GraphConfigService
RUNTIME_PROVIDERS_CONFIG_KEY = "runtime_llm_providers"

# Env var name for .env file persistence
RUNTIME_PROVIDERS_ENV_VAR = "RUNTIME_LLM_PROVIDERS_JSON"

# Env var name for disabling CIRIS services
CIRIS_SERVICES_DISABLED_VAR = "CIRIS_SERVICES_DISABLED"


class LLMProviderConfig(BaseModel):
    """Configuration for a runtime LLM provider."""

    provider_id: str = Field(..., description="Provider type (e.g., 'local', 'openai')")
    base_url: str = Field(..., description="API base URL")
    model: str = Field(default="default", description="Model name")
    api_key: str = Field(default="", description="API key (empty for local)")
    priority: str = Field(default="fallback", description="Priority level")

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
# .env File Operations
# =============================================================================


def _get_env_path() -> Optional[Path]:
    """Get the .env file path."""
    try:
        from ciris_engine.logic.setup.first_run import get_default_config_path

        return get_default_config_path()
    except Exception as e:
        logger.warning(f"Could not determine .env path: {e}")
        return None


def read_providers_from_env() -> dict[str, LLMProviderConfig]:
    """Read runtime LLM providers from .env file.

    Returns:
        Dict mapping provider_name -> LLMProviderConfig
    """
    env_path = _get_env_path()
    if not env_path or not env_path.exists():
        return {}

    try:
        content = env_path.read_text()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith(f"{RUNTIME_PROVIDERS_ENV_VAR}="):
                # Extract JSON value (handle both quoted and unquoted)
                value = line[len(f"{RUNTIME_PROVIDERS_ENV_VAR}=") :]
                # Remove surrounding quotes if present
                if (value.startswith("'") and value.endswith("'")) or (
                    value.startswith('"') and value.endswith('"')
                ):
                    value = value[1:-1]

                if value:
                    data = json.loads(value)
                    return {
                        name: LLMProviderConfig.from_dict(config)
                        for name, config in data.items()
                    }
        return {}
    except Exception as e:
        logger.warning(f"Failed to read runtime providers from .env: {e}")
        return {}


def write_providers_to_env(providers: dict[str, LLMProviderConfig]) -> bool:
    """Write runtime LLM providers to .env file.

    Args:
        providers: Dict mapping provider_name -> LLMProviderConfig

    Returns:
        True if successfully persisted
    """
    env_path = _get_env_path()
    if not env_path:
        logger.warning("Cannot persist runtime providers - .env path unknown")
        return False

    if not env_path.exists():
        logger.warning("Cannot persist runtime providers - .env not found")
        return False

    try:
        # Read existing content
        content = env_path.read_text()
        lines = content.splitlines()

        # Remove existing RUNTIME_LLM_PROVIDERS_JSON line
        new_lines = [
            line
            for line in lines
            if not line.strip().startswith(f"{RUNTIME_PROVIDERS_ENV_VAR}=")
        ]

        # Add new runtime providers line (or skip if empty)
        if providers:
            providers_dict = {name: cfg.to_dict() for name, cfg in providers.items()}
            providers_json = json.dumps(providers_dict)
            new_lines.append(f"\n{RUNTIME_PROVIDERS_ENV_VAR}='{providers_json}'")

        # Write back
        env_path.write_text("\n".join(new_lines) + "\n")
        logger.info(f"Persisted {len(providers)} runtime LLM provider(s) to .env")
        return True

    except Exception as e:
        logger.warning(f"Failed to persist runtime providers to .env: {e}")
        return False


def _transform_local_provider_line(line: str) -> str:
    """Transform a line for local provider deletion."""
    stripped = line.strip()
    if stripped.startswith("CIRIS_MOBILE_LOCAL_LLM_ENABLED="):
        return "CIRIS_MOBILE_LOCAL_LLM_ENABLED=false"
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
        new_lines = [
            line
            for line in lines
            if not line.strip().startswith(f"{CIRIS_SERVICES_DISABLED_VAR}=")
        ]

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
# Graph Config Operations
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
            return {
                name: LLMProviderConfig.from_dict(config)
                for name, config in data.items()
            }
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
# CRUD Operations (Combined .env + Graph)
# =============================================================================


async def list_providers(config_service: Optional[Any] = None) -> dict[str, LLMProviderConfig]:
    """List all persisted runtime LLM providers.

    Reads from both graph and .env, with graph taking precedence.

    Args:
        config_service: Optional GraphConfigService instance

    Returns:
        Dict mapping provider_name -> LLMProviderConfig
    """
    # Try graph first (more reliable)
    if config_service:
        providers = await read_providers_from_graph(config_service)
        if providers:
            return providers

    # Fall back to .env
    return read_providers_from_env()


async def get_provider(
    name: str, config_service: Optional[Any] = None
) -> Optional[LLMProviderConfig]:
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

    Persists to both graph and .env.

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
        return PersistenceResult(
            success=False, error=f"Provider '{name}' already exists"
        )

    # Add new provider
    providers[name] = config

    # Persist to both stores
    graph_ok = await write_providers_to_graph(config_service, providers)
    env_ok = write_providers_to_env(providers)

    return PersistenceResult(
        success=graph_ok or env_ok,
        graph_persisted=graph_ok,
        env_persisted=env_ok,
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
        return PersistenceResult(
            success=False, error=f"Provider '{name}' not found"
        )

    # Update provider
    providers[name] = config

    # Persist to both stores
    graph_ok = await write_providers_to_graph(config_service, providers)
    env_ok = write_providers_to_env(providers)

    return PersistenceResult(
        success=graph_ok or env_ok,
        graph_persisted=graph_ok,
        env_persisted=env_ok,
    )


async def delete_provider(
    name: str,
    config_service: Optional[Any] = None,
) -> PersistenceResult:
    """Delete a runtime LLM provider.

    For primary providers (local_primary, ciris_primary), also clears the
    env vars that would re-create them on restart.

    Args:
        name: Provider name
        config_service: Optional GraphConfigService instance

    Returns:
        PersistenceResult with success status
    """
    # Handle primary providers specially - clear their env vars
    # These are created from NEXT_PUBLIC_API_BASE_URL, CIRIS_MOBILE_LOCAL_LLM_ENABLED, etc.
    # and won't be in the RUNTIME_LLM_PROVIDERS_JSON
    primary_env_cleared = False
    if name == "local_primary":
        primary_env_cleared = clear_primary_provider_env_vars(is_local=True)
        logger.info(f"Cleared local primary provider env vars: {primary_env_cleared}")
    elif name == "ciris_primary":
        primary_env_cleared = clear_primary_provider_env_vars(is_local=False)
        logger.info(f"Cleared cloud primary provider env vars: {primary_env_cleared}")

    # Load existing runtime providers
    providers = await list_providers(config_service)

    # For primary providers, they may not be in runtime providers list
    # (created from individual env vars, not RUNTIME_LLM_PROVIDERS_JSON)
    if name not in providers:
        if primary_env_cleared:
            # Primary provider was handled via env var clearing
            return PersistenceResult(
                success=True,
                env_persisted=True,
                graph_persisted=False,
            )
        return PersistenceResult(
            success=False, error=f"Provider '{name}' not found"
        )

    # Remove provider from runtime list
    del providers[name]

    # Persist to both stores
    graph_ok = await write_providers_to_graph(config_service, providers)
    env_ok = write_providers_to_env(providers)

    return PersistenceResult(
        success=graph_ok or env_ok or primary_env_cleared,
        graph_persisted=graph_ok,
        env_persisted=env_ok or primary_env_cleared,
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

    # Add/update provider
    providers[name] = config

    # Persist to both stores
    graph_ok = await write_providers_to_graph(config_service, providers)
    env_ok = write_providers_to_env(providers)

    return PersistenceResult(
        success=graph_ok or env_ok,
        graph_persisted=graph_ok,
        env_persisted=env_ok,
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
    env_ok = write_providers_to_env(empty_providers)

    return PersistenceResult(
        success=graph_ok or env_ok,
        graph_persisted=graph_ok,
        env_persisted=env_ok,
    )
