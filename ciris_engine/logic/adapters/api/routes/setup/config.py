"""Configuration endpoints for CIRIS setup.

This module provides endpoints for reading and updating agent configuration.
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ciris_engine.schemas.api.responses import SuccessResponse

from .._common import RESPONSES_401_500, RESPONSES_403, RESPONSES_500, AuthAdminDep
from .helpers import _is_setup_allowed_without_auth
from .models import SetupCompleteRequest, SetupConfigResponse


def _sanitize_env_value(value: str) -> str:
    """Sanitize a value for safe inclusion in .env file.

    Prevents injection attacks by escaping/removing dangerous characters.
    This breaks the taint chain from user input to file write.

    Args:
        value: Raw value to sanitize

    Returns:
        Sanitized value safe for .env file
    """
    # Remove newlines and carriage returns (prevent multi-line injection)
    sanitized = value.replace("\n", "").replace("\r", "")
    # Escape double quotes
    sanitized = sanitized.replace('"', '\\"')
    # Escape backslashes (prevent escape sequence injection)
    sanitized = sanitized.replace("\\", "\\\\")
    return sanitized


def _validate_provider_name(provider: str) -> str:
    """Validate and normalize LLM provider name.

    Only allow known provider names to prevent injection.

    Args:
        provider: User-provided provider name

    Returns:
        Validated provider name

    Raises:
        ValueError: If provider is not in allowlist
    """
    # Allowlist of known providers
    allowed_providers = frozenset(
        {
            "openai",
            "anthropic",
            "google",
            "openrouter",
            "local",
            "groq",
            "together",
            "mistral",
            "cohere",
            "azure",
            "ollama",
        }
    )
    normalized = provider.lower().strip()
    if normalized not in allowed_providers:
        # Allow custom providers but validate format (alphanumeric + underscore only)
        if not re.match(r"^[a-z][a-z0-9_]*$", normalized):
            raise ValueError(f"Invalid provider name format: {provider}")
    return normalized


def _validate_config_path(config_path: Path) -> Path:
    """Validate that config path is within allowed directories.

    SECURITY: This breaks the taint chain by:
    1. Validating the path against an allowlist of known config directories
    2. Returning a NEW Path object constructed from validated components

    The returned Path is constructed from the resolved string, which SonarCloud
    recognizes as breaking the taint chain from user-controlled input.

    Args:
        config_path: Path from get_default_config_path()

    Returns:
        New validated Path object (breaks taint chain)

    Raises:
        ValueError: If path is not within allowed directories
    """
    # Resolve to absolute path and normalize
    resolved = config_path.resolve()

    # Allowlist of parent directories where config files may exist
    allowed_parents = [
        Path.home() / "ciris",  # User install: ~/ciris/.env
        Path.home() / "Documents" / "ciris",  # iOS default: ~/Documents/ciris/.env
        Path("/app"),  # Managed/Docker: /app/.env
        Path("/etc/ciris"),  # System config: /etc/ciris/.env
    ]

    # Add cwd/ciris for development mode
    try:
        allowed_parents.append(Path.cwd() / "ciris")
        allowed_parents.append(Path.cwd())  # Legacy dev mode support
    except OSError:
        pass  # cwd may not be accessible

    # Add CIRIS_HOME if set (Android/iOS/custom installs)
    ciris_home = os.environ.get("CIRIS_HOME")
    if ciris_home:
        allowed_parents.append(Path(ciris_home))

    # Resolve all allowed parents
    resolved_allowed = []
    for parent in allowed_parents:
        try:
            resolved_allowed.append(parent.resolve())
        except (OSError, RuntimeError):
            pass  # Skip inaccessible paths

    # Check if config path is within any allowed parent
    for allowed_parent in resolved_allowed:
        try:
            # Verify path is within allowed directory
            relative_path = resolved.relative_to(allowed_parent)
            # SECURITY: Construct NEW Path from validated allowed_parent + relative_path
            # This breaks the taint chain by creating a path from known-safe components
            validated_path = allowed_parent / relative_path
            return validated_path
        except ValueError:
            continue  # Not under this parent, try next

    # Path not in any allowed directory
    raise ValueError(f"Config path not in allowed directory: {resolved}")


class UpdateLlmConfigRequest(BaseModel):
    """Request to update LLM configuration only."""

    llm_provider: str = Field(..., description="LLM provider ID (openai, openrouter, anthropic, etc.)")
    llm_api_key: Optional[str] = Field(None, description="API key (omit to keep existing)")
    llm_base_url: Optional[str] = Field(None, description="Custom base URL (for OpenRouter, local, etc.)")
    llm_model: Optional[str] = Field(None, description="Model name")


logger = logging.getLogger(__name__)


# Mapping from explicit env var values to canonical provider names.
_PROVIDER_ALIASES: dict[str, str] = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "google": "google",
    "gemini": "google",
    "openai": "openai",
    "openrouter": "openrouter",
    "groq": "groq",
    "together": "together",
    "openai_compatible": "other",
}

# Substrings in OPENAI_API_BASE that identify a provider.
# Order matters: first match wins.
_BASE_URL_PATTERNS: list[tuple[str, str]] = [
    ("openrouter.ai", "openrouter"),
    ("groq.com", "groq"),
    ("together.xyz", "together"),
    ("together.ai", "together"),
    ("mistral.ai", "mistral"),
    ("deepseek.com", "deepseek"),
    ("cohere", "cohere"),
    ("localhost", "local"),
    ("127.0.0.1", "local"),
]

# Env vars that indicate an API key is set, keyed by provider.
_PROVIDER_KEY_VARS: dict[str, list[str]] = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "mockllm": [],
    "ciris_proxy": [],
    "local": [],
}

_TRUTHY = {"true", "1", "yes", "on"}


def _is_mock_llm(request: Request) -> bool:
    """Check if mock LLM is active via runtime flag or env var."""
    runtime = getattr(request.app.state, "runtime", None)
    if runtime and "mock_llm" in getattr(runtime, "modules_to_load", []):
        return True
    return os.getenv("CIRIS_MOCK_LLM", "").lower() in _TRUTHY


def _detect_from_explicit_env() -> str | None:
    """Resolve an explicitly-set CIRIS_LLM_PROVIDER / LLM_PROVIDER value."""
    raw = (os.getenv("CIRIS_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "").lower()
    if not raw:
        return None
    return _PROVIDER_ALIASES.get(raw, raw)  # pass through unknown values


def _detect_from_api_keys() -> str | None:
    """Auto-detect provider from well-known API key env vars."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        return "google"
    return None


def _detect_from_base_url() -> str | None:
    """Identify provider from OPENAI_API_BASE substring patterns."""
    base_url = os.getenv("OPENAI_API_BASE", "")
    if not base_url:
        return None
    for pattern, provider in _BASE_URL_PATTERNS:
        if pattern in base_url:
            return provider
    return "other"


def _detect_llm_provider(request: Request) -> str:
    """Detect the active LLM provider for display in the UI.

    Priority: mock > explicit env > API key > base URL > CIRIS proxy > default.
    """
    if _is_mock_llm(request):
        return "mockllm"

    for detector in (_detect_from_explicit_env, _detect_from_api_keys, _detect_from_base_url):
        result = detector()
        if result is not None:
            return result

    if os.getenv("CIRIS_PROXY_URL") or os.getenv("CIRIS_PROXY_ENABLED", "").lower() in _TRUTHY:
        return "ciris_proxy"

    return "openai"


def _detect_api_key_set(provider: str) -> bool:
    """Check whether *any* relevant API key env var is set for the given provider.

    Falls back to OPENAI_API_KEY for providers not in the lookup table
    (most OpenAI-compatible services reuse that key).
    """
    key_vars = _PROVIDER_KEY_VARS.get(provider, ["OPENAI_API_KEY"])
    return any(os.getenv(v) for v in key_vars)


router = APIRouter()


@router.get("/config", responses=RESPONSES_401_500)
async def get_current_config(request: Request) -> SuccessResponse[SetupConfigResponse]:
    """Get current configuration.

    Returns current setup configuration for editing.
    Requires authentication if setup is already completed.
    """
    # If not first-run, require authentication
    if not _is_setup_allowed_without_auth():
        # Manually get auth context from request
        try:
            from ...dependencies.auth import get_auth_context, get_auth_service

            # Extract authorization header and auth service manually since we're not using Depends()
            authorization = request.headers.get("Authorization")
            auth_service = get_auth_service(request)
            auth = await get_auth_context(request, authorization, auth_service)
            if auth is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Authentication failed for /setup/config: {e}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    # Get template from CLI flag (via runtime config) or environment variable
    # CLI --template flag takes precedence on first-run before .env exists
    template_id = os.getenv("CIRIS_TEMPLATE")
    if not template_id:
        runtime = getattr(request.app.state, "runtime", None)
        if runtime and hasattr(runtime, "essential_config") and runtime.essential_config:
            template_id = getattr(runtime.essential_config, "default_template", None)
    if not template_id:
        template_id = "default"

    # Detect LLM provider using same logic as LLM service
    llm_provider = _detect_llm_provider(request)

    # Get user location from environment (safely handle invalid values)
    latitude_str = os.getenv("CIRIS_USER_LATITUDE")
    longitude_str = os.getenv("CIRIS_USER_LONGITUDE")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    if latitude_str:
        try:
            latitude = float(latitude_str)
        except ValueError:
            pass  # Invalid format, fall back to None
    if longitude_str:
        try:
            longitude = float(longitude_str)
        except ValueError:
            pass  # Invalid format, fall back to None

    config = SetupConfigResponse(
        llm_provider=llm_provider,
        llm_base_url=os.getenv("OPENAI_API_BASE"),
        llm_model=os.getenv("OPENAI_MODEL"),
        llm_api_key_set=_detect_api_key_set(llm_provider),
        backup_llm_base_url=os.getenv("CIRIS_OPENAI_API_BASE_2"),
        backup_llm_model=os.getenv("CIRIS_OPENAI_MODEL_NAME_2"),
        backup_llm_api_key_set=bool(os.getenv("CIRIS_OPENAI_API_KEY_2")),
        template_id=template_id,
        enabled_adapters=os.getenv("CIRIS_ADAPTER", "api").split(","),
        agent_port=int(os.getenv("CIRIS_API_PORT", "8080")),
        location_country=os.getenv("CIRIS_USER_COUNTRY"),
        location_region=os.getenv("CIRIS_USER_REGION"),
        location_city=os.getenv("CIRIS_USER_CITY"),
        location_latitude=latitude,
        location_longitude=longitude,
        timezone=os.getenv("CIRIS_USER_TIMEZONE"),
        has_coordinates=latitude is not None and longitude is not None,
    )

    return SuccessResponse(data=config)


@router.put(
    "/config",
    responses={**RESPONSES_403, **RESPONSES_500},
)
async def update_config(
    setup: SetupCompleteRequest,
    auth: AuthAdminDep,
) -> SuccessResponse[Dict[str, str]]:
    """Update configuration.

    Updates setup configuration after initial setup.
    Requires admin authentication (enforced by AuthAdminDep).
    """
    from .complete import _save_setup_config

    # Note: Admin role check is performed by AuthAdminDep dependency
    _ = auth  # Used for auth enforcement

    try:
        # Save updated configuration (path determined internally)
        config_path = _save_setup_config(setup)

        return SuccessResponse(
            data={
                "status": "updated",
                "message": "Configuration updated successfully",
                "config_path": str(config_path),
                "next_steps": "Restart the agent to apply changes",
            }
        )

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/llm",
    responses={**RESPONSES_403, **RESPONSES_500},
)
async def update_llm_config(
    request: Request,
    body: UpdateLlmConfigRequest,
    auth: AuthAdminDep,
) -> SuccessResponse[Dict[str, str]]:
    """Update LLM configuration only.

    Updates just the LLM provider, API key, base URL, and model in the .env file.
    This is a simpler alternative to PUT /setup/config for BYOK users who
    just want to change their LLM settings without going through the full wizard.

    Requires admin authentication.
    """
    from ciris_engine.logic.setup.first_run import get_default_config_path

    from .llm_validation import _get_provider_base_url

    _ = auth  # Used for auth enforcement

    try:
        config_path = get_default_config_path()
        if not config_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Configuration file not found. Run setup wizard first.",
            )

        # SECURITY: Validate config path is within allowed directories.
        # This breaks the taint chain by returning a NEW Path constructed from
        # validated components (allowed_parent / relative_path).
        try:
            config_path = _validate_config_path(config_path)
        except ValueError as e:
            logger.error("Config path validation failed")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid config path")

        # SECURITY: Validate and sanitize all user input before file operations.
        # This breaks the taint chain from HTTP request to file write.
        try:
            safe_provider = _validate_provider_name(body.llm_provider)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        safe_api_key = _sanitize_env_value(body.llm_api_key) if body.llm_api_key else None
        safe_model = _sanitize_env_value(body.llm_model) if body.llm_model else None

        # Read existing .env content
        content = config_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        new_lines = []

        # Track what we've updated
        updated_provider = False
        updated_key = False
        updated_base = False
        updated_model = False

        # Get the effective base URL (use provider default if not specified)
        raw_base_url = _get_provider_base_url(body.llm_provider, body.llm_base_url) or ""
        safe_base_url = _sanitize_env_value(raw_base_url) if raw_base_url else ""

        # Determine which API key env var to use based on provider
        # anthropic → ANTHROPIC_API_KEY, google → GOOGLE_API_KEY, others → OPENAI_API_KEY
        provider_key_mapping = {
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
        }
        target_key_var = provider_key_mapping.get(safe_provider, "OPENAI_API_KEY")

        for line in lines:
            stripped = line.strip()

            # Update the appropriate provider-specific API key
            # For anthropic: ANTHROPIC_API_KEY, for google: GOOGLE_API_KEY, else: OPENAI_API_KEY
            if stripped.startswith(f"{target_key_var}=") or stripped.startswith(f"# {target_key_var}="):
                if safe_api_key:
                    new_lines.append(f'{target_key_var}="{safe_api_key}"')
                    updated_key = True
                else:
                    new_lines.append(line)  # Keep existing
                    updated_key = True
                continue

            # Also handle OPENAI_API_KEY for non-openai providers (comment it out or keep as-is)
            if target_key_var != "OPENAI_API_KEY" and (
                stripped.startswith("OPENAI_API_KEY=") or stripped.startswith("# OPENAI_API_KEY=")
            ):
                new_lines.append(line)  # Keep existing OPENAI_API_KEY unchanged
                continue

            # Update or uncomment OPENAI_API_BASE
            if stripped.startswith("OPENAI_API_BASE=") or stripped.startswith("# OPENAI_API_BASE="):
                if safe_base_url:
                    new_lines.append(f'OPENAI_API_BASE="{safe_base_url}"')
                else:
                    new_lines.append(f'# OPENAI_API_BASE=""')
                updated_base = True
                continue

            # Update or uncomment OPENAI_MODEL
            if stripped.startswith("OPENAI_MODEL=") or stripped.startswith("# OPENAI_MODEL="):
                if safe_model:
                    new_lines.append(f'OPENAI_MODEL="{safe_model}"')
                else:
                    new_lines.append(line)  # Keep existing
                updated_model = True
                continue

            # Update LLM_PROVIDER if present
            if stripped.startswith("LLM_PROVIDER=") or stripped.startswith("# LLM_PROVIDER="):
                new_lines.append(f'LLM_PROVIDER="{safe_provider}"')
                updated_provider = True
                continue

            # Keep other lines unchanged
            new_lines.append(line)

        # Add missing keys if not found (using sanitized values)
        if not updated_key and safe_api_key:
            new_lines.append(f'{target_key_var}="{safe_api_key}"')
        if not updated_base and safe_base_url:
            new_lines.append(f'OPENAI_API_BASE="{safe_base_url}"')
        if not updated_model and safe_model:
            new_lines.append(f'OPENAI_MODEL="{safe_model}"')
        if not updated_provider:
            new_lines.append(f'LLM_PROVIDER="{safe_provider}"')

        # Write updated content
        new_content = "\n".join(new_lines)
        if not new_content.endswith("\n"):
            new_content += "\n"
        config_path.write_text(new_content, encoding="utf-8")

        # Trigger config reload signal for the Python runtime
        reload_file = config_path.parent / ".config_reload"
        import time

        reload_file.write_text(str(time.time()), encoding="utf-8")

        # Log update without user-controlled data to prevent log injection (CWE-117)
        logger.info("LLM config updated successfully")

        return SuccessResponse(
            data={
                "status": "updated",
                "message": "LLM configuration updated successfully",
                "provider": safe_provider,
                "base_url": safe_base_url or "(default)",
                "model": safe_model or "(unchanged)",
                "config_path": str(config_path),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update LLM config: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
