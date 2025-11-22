"""
Setup wizard endpoints for CIRIS first-run and reconfiguration.

Provides GUI-based setup wizard accessible at /v1/setup/*.
Replaces the CLI wizard for pip-installed CIRIS agents.
"""

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ciris_engine.logic.setup.first_run import get_default_config_path, is_first_run
from ciris_engine.logic.setup.wizard import create_env_file, generate_encryption_key
from ciris_engine.schemas.api.responses import SuccessResponse

from ..dependencies.auth import AuthContext, get_auth_context

router = APIRouter(prefix="/setup", tags=["setup"])

# ============================================================================
# Request/Response Schemas
# ============================================================================


class LLMProvider(BaseModel):
    """LLM provider configuration."""

    id: str = Field(..., description="Provider ID (openai, local, other)")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Provider description")
    requires_api_key: bool = Field(..., description="Whether API key is required")
    requires_base_url: bool = Field(..., description="Whether base URL is required")
    requires_model: bool = Field(..., description="Whether model name is required")
    default_base_url: Optional[str] = Field(None, description="Default base URL if applicable")
    default_model: Optional[str] = Field(None, description="Default model name if applicable")
    examples: List[str] = Field(default_factory=list, description="Example configurations")


class AgentTemplate(BaseModel):
    """Agent identity template."""

    id: str = Field(..., description="Template ID")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Template description")
    identity: str = Field(..., description="Agent identity/purpose")
    example_use_cases: List[str] = Field(default_factory=list, description="Example use cases")


class AdapterConfig(BaseModel):
    """Adapter configuration."""

    id: str = Field(..., description="Adapter ID (api, cli, discord, reddit)")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Adapter description")
    enabled_by_default: bool = Field(False, description="Whether enabled by default")
    required_env_vars: List[str] = Field(default_factory=list, description="Required environment variables")
    optional_env_vars: List[str] = Field(default_factory=list, description="Optional environment variables")


class SetupStatusResponse(BaseModel):
    """Setup status information."""

    is_first_run: bool = Field(..., description="Whether this is first run")
    config_exists: bool = Field(..., description="Whether config file exists")
    config_path: Optional[str] = Field(None, description="Path to config file if exists")
    setup_required: bool = Field(..., description="Whether setup is required")


class LLMValidationRequest(BaseModel):
    """Request to validate LLM configuration."""

    provider: str = Field(..., description="Provider ID (openai, local, other)")
    api_key: str = Field(..., description="API key")
    base_url: Optional[str] = Field(None, description="Base URL for OpenAI-compatible endpoints")
    model: Optional[str] = Field(None, description="Model name")


class LLMValidationResponse(BaseModel):
    """Response from LLM validation."""

    valid: bool = Field(..., description="Whether configuration is valid")
    message: str = Field(..., description="Validation message")
    error: Optional[str] = Field(None, description="Error details if validation failed")


class SetupCompleteRequest(BaseModel):
    """Request to complete setup."""

    # LLM Configuration
    llm_provider: str = Field(..., description="LLM provider ID")
    llm_api_key: str = Field(..., description="LLM API key")
    llm_base_url: Optional[str] = Field(None, description="LLM base URL")
    llm_model: Optional[str] = Field(None, description="LLM model name")

    # Template Selection
    template_id: str = Field(default="general", description="Agent template ID")

    # Adapter Configuration
    enabled_adapters: List[str] = Field(default=["api"], description="List of enabled adapters")
    adapter_config: Dict[str, Any] = Field(default_factory=dict, description="Adapter-specific configuration")

    # User Configuration - Dual Password Support
    admin_username: str = Field(default="admin", description="New user's username")
    admin_password: str = Field(..., description="New user's password (min 8 characters)")
    system_admin_password: Optional[str] = Field(
        None, description="System admin password to replace default (min 8 characters, optional)"
    )

    # Application Configuration
    agent_port: int = Field(default=8080, description="Agent API port")


class SetupConfigResponse(BaseModel):
    """Current setup configuration."""

    # LLM Configuration
    llm_provider: Optional[str] = Field(None, description="Current LLM provider")
    llm_base_url: Optional[str] = Field(None, description="Current LLM base URL")
    llm_model: Optional[str] = Field(None, description="Current LLM model")
    llm_api_key_set: bool = Field(False, description="Whether API key is configured")

    # Template
    template_id: Optional[str] = Field(None, description="Current template ID")

    # Adapters
    enabled_adapters: List[str] = Field(default_factory=list, description="Currently enabled adapters")

    # Application
    agent_port: int = Field(default=8080, description="Current agent port")


class CreateUserRequest(BaseModel):
    """Request to create initial admin user."""

    username: str = Field(..., description="Admin username")
    password: str = Field(..., description="Admin password (min 8 characters)")


class ChangePasswordRequest(BaseModel):
    """Request to change admin password."""

    old_password: str = Field(..., description="Current password")
    new_password: str = Field(..., description="New password (min 8 characters)")


# ============================================================================
# Helper Functions
# ============================================================================


def _is_setup_allowed_without_auth() -> bool:
    """Check if setup endpoints should be accessible without authentication.

    Returns True during first-run (no config exists).
    Returns False after setup (config exists, requires auth).
    """
    return is_first_run()


def _get_llm_providers() -> List[LLMProvider]:
    """Get list of supported LLM providers."""
    return [
        LLMProvider(
            id="openai",
            name="OpenAI",
            description="Official OpenAI API (GPT-4, GPT-3.5, etc.)",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=False,
            default_base_url=None,
            default_model="gpt-4",
            examples=[
                "Standard OpenAI API",
                "Azure OpenAI Service",
            ],
        ),
        LLMProvider(
            id="local",
            name="Local LLM",
            description="Local LLM server (Ollama, LM Studio, vLLM, etc.)",
            requires_api_key=False,
            requires_base_url=True,
            requires_model=True,
            default_base_url="http://localhost:11434",
            default_model="llama3",
            examples=[
                "Ollama: http://localhost:11434",
                "LM Studio: http://localhost:1234/v1",
                "vLLM: http://localhost:8000/v1",
                "LocalAI: http://localhost:8080/v1",
            ],
        ),
        LLMProvider(
            id="other",
            name="OpenAI-Compatible Provider",
            description="Any OpenAI-compatible API endpoint",
            requires_api_key=True,
            requires_base_url=True,
            requires_model=True,
            default_base_url=None,
            default_model=None,
            examples=[
                "Together AI: https://api.together.xyz/v1",
                "Groq: https://api.groq.com/openai/v1",
                "Fireworks: https://api.fireworks.ai/inference/v1",
                "Anyscale: https://api.endpoints.anyscale.com/v1",
            ],
        ),
    ]


def _get_agent_templates() -> List[AgentTemplate]:
    """Get list of available agent templates."""
    return [
        AgentTemplate(
            id="general",
            name="General Purpose Assistant",
            description="Versatile AI assistant for general tasks",
            identity="I am a helpful AI assistant designed to support you with various tasks.",
            example_use_cases=[
                "Personal productivity",
                "Information lookup",
                "General conversation",
            ],
        ),
        AgentTemplate(
            id="moderator",
            name="Community Moderator",
            description="AI moderator for Discord/Reddit communities",
            identity="I am a community moderator focused on maintaining healthy, respectful discussions.",
            example_use_cases=[
                "Discord server moderation",
                "Reddit community management",
                "Content policy enforcement",
            ],
        ),
        AgentTemplate(
            id="researcher",
            name="Research Assistant",
            description="AI assistant specialized in research and analysis",
            identity="I am a research assistant focused on helping you find, analyze, and synthesize information.",
            example_use_cases=[
                "Literature review",
                "Data analysis",
                "Fact-checking",
            ],
        ),
        AgentTemplate(
            id="developer",
            name="Developer Assistant",
            description="AI assistant for software development",
            identity="I am a developer assistant focused on helping with code, documentation, and technical tasks.",
            example_use_cases=[
                "Code review",
                "Documentation writing",
                "Debugging assistance",
            ],
        ),
        AgentTemplate(
            id="custom",
            name="Custom Identity",
            description="Define your own agent identity and purpose",
            identity="",
            example_use_cases=[
                "Specialized domain expert",
                "Custom workflow automation",
                "Unique use case",
            ],
        ),
    ]


def _get_available_adapters() -> List[AdapterConfig]:
    """Get list of available adapters."""
    return [
        AdapterConfig(
            id="api",
            name="Web API",
            description="RESTful API server with built-in web interface",
            enabled_by_default=True,
            required_env_vars=[],
            optional_env_vars=["CIRIS_API_PORT", "NEXT_PUBLIC_API_BASE_URL"],
        ),
        AdapterConfig(
            id="cli",
            name="Command Line",
            description="Interactive command-line interface",
            enabled_by_default=False,
            required_env_vars=[],
            optional_env_vars=[],
        ),
        AdapterConfig(
            id="discord",
            name="Discord Bot",
            description="Discord bot integration for server moderation and interaction",
            enabled_by_default=False,
            required_env_vars=["DISCORD_BOT_TOKEN"],
            optional_env_vars=["DISCORD_CHANNEL_ID", "DISCORD_GUILD_ID"],
        ),
        AdapterConfig(
            id="reddit",
            name="Reddit Integration",
            description="Reddit bot for r/ciris monitoring and interaction",
            enabled_by_default=False,
            required_env_vars=[
                "CIRIS_REDDIT_CLIENT_ID",
                "CIRIS_REDDIT_CLIENT_SECRET",
                "CIRIS_REDDIT_USERNAME",
                "CIRIS_REDDIT_PASSWORD",
            ],
            optional_env_vars=["CIRIS_REDDIT_SUBREDDIT"],
        ),
    ]


async def _validate_llm_connection(config: LLMValidationRequest) -> LLMValidationResponse:
    """Validate LLM configuration by attempting a connection.

    Args:
        config: LLM configuration to validate

    Returns:
        Validation response with success/failure status
    """
    try:
        # Import OpenAI client
        from openai import AsyncOpenAI

        # Build client configuration
        client_kwargs: Dict[str, Any] = {}

        if config.base_url:
            client_kwargs["base_url"] = config.base_url

        # For local LLMs, api_key can be "local" or any placeholder
        # For OpenAI/commercial, validate format
        if config.provider == "openai":
            if not config.api_key or config.api_key == "your_openai_api_key_here":
                return LLMValidationResponse(
                    valid=False,
                    message="Invalid API key",
                    error="OpenAI requires a valid API key starting with 'sk-'",
                )
        elif config.provider == "local":
            # Local LLM doesn't require real API key
            client_kwargs["api_key"] = config.api_key or "local"
        else:
            # Other providers need API key
            if not config.api_key:
                return LLMValidationResponse(
                    valid=False, message="API key required", error="This provider requires an API key"
                )

        client_kwargs["api_key"] = config.api_key

        # Create client
        client = AsyncOpenAI(**client_kwargs)

        # Attempt to list models (lightweight check)
        try:
            models = await client.models.list()
            model_count = len(models.data) if hasattr(models, "data") else 0

            return LLMValidationResponse(
                valid=True,
                message=f"Connection successful! Found {model_count} available models.",
                error=None,
            )
        except Exception as e:
            error_str = str(e)

            # Check for common errors
            if "401" in error_str or "Unauthorized" in error_str:
                return LLMValidationResponse(
                    valid=False,
                    message="Authentication failed",
                    error="Invalid API key. Please check your credentials.",
                )
            elif "404" in error_str or "Not Found" in error_str:
                return LLMValidationResponse(
                    valid=False,
                    message="Endpoint not found",
                    error=f"Could not reach {config.base_url}. Please check the URL.",
                )
            elif "timeout" in error_str.lower():
                return LLMValidationResponse(
                    valid=False,
                    message="Connection timeout",
                    error="Could not connect to LLM server. Please check if it's running.",
                )
            else:
                return LLMValidationResponse(valid=False, message="Connection failed", error=f"Error: {error_str}")

    except Exception as e:
        return LLMValidationResponse(valid=False, message="Validation error", error=str(e))


def _save_pending_users(setup: SetupCompleteRequest, config_dir: Path) -> None:
    """Save pending user creation info for initialization service.

    Args:
        setup: Setup configuration with user info
        config_dir: Directory where .env file is saved
    """
    pending_users_file = config_dir / ".ciris_pending_users.json"

    # Prepare user creation data
    users_data = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "new_user": {
            "username": setup.admin_username,
            "password": setup.admin_password,  # Will be hashed by auth service
            "role": "ADMIN",  # New user gets admin role
        },
    }

    # Add system admin password update if provided
    if setup.system_admin_password:
        users_data["system_admin"] = {
            "username": "admin",  # Default system admin username
            "password": setup.system_admin_password,  # Will be hashed by auth service
        }

    # Save to JSON file
    with open(pending_users_file, "w") as f:
        json.dump(users_data, f, indent=2)


def _save_setup_config(setup: SetupCompleteRequest, config_path: Path) -> None:
    """Save setup configuration to .env file.

    Args:
        setup: Setup configuration
        config_path: Path to save .env file
    """
    # Determine LLM provider type for env file generation
    llm_provider = setup.llm_provider
    llm_api_key = setup.llm_api_key
    llm_base_url = setup.llm_base_url or ""
    llm_model = setup.llm_model or ""

    # Create .env file using existing wizard logic
    create_env_file(
        save_path=config_path,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        agent_port=setup.agent_port,
    )

    # Append template and adapter configuration
    with open(config_path, "a") as f:
        # Template selection
        f.write(f"\n# Agent Template\n")
        f.write(f"CIRIS_TEMPLATE={setup.template_id}\n")

        # Adapter configuration
        f.write(f"\n# Enabled Adapters\n")
        adapters_str = ",".join(setup.enabled_adapters)
        f.write(f"CIRIS_ADAPTER={adapters_str}\n")

        # Adapter-specific environment variables
        if setup.adapter_config:
            f.write(f"\n# Adapter-Specific Configuration\n")
            for key, value in setup.adapter_config.items():
                f.write(f"{key}={value}\n")


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/status", response_model=SuccessResponse[SetupStatusResponse])
async def get_setup_status() -> SuccessResponse[SetupStatusResponse]:
    """Check setup status.

    Returns information about whether setup is required.
    This endpoint is always accessible without authentication.
    """
    first_run = is_first_run()
    config_path = get_default_config_path()
    config_exists = config_path.exists()

    status = SetupStatusResponse(
        is_first_run=first_run,
        config_exists=config_exists,
        config_path=str(config_path) if config_exists else None,
        setup_required=first_run,
    )

    return SuccessResponse(data=status)


@router.get("/providers", response_model=SuccessResponse[List[LLMProvider]])
async def list_providers() -> SuccessResponse[List[LLMProvider]]:
    """List available LLM providers.

    Returns configuration templates for supported LLM providers.
    This endpoint is always accessible without authentication.
    """
    providers = _get_llm_providers()
    return SuccessResponse(data=providers)


@router.get("/templates", response_model=SuccessResponse[List[AgentTemplate]])
async def list_templates() -> SuccessResponse[List[AgentTemplate]]:
    """List available agent templates.

    Returns pre-configured agent identity templates.
    This endpoint is always accessible without authentication.
    """
    templates = _get_agent_templates()
    return SuccessResponse(data=templates)


@router.get("/adapters", response_model=SuccessResponse[List[AdapterConfig]])
async def list_adapters() -> SuccessResponse[List[AdapterConfig]]:
    """List available adapters.

    Returns configuration for available communication adapters.
    This endpoint is always accessible without authentication.
    """
    adapters = _get_available_adapters()
    return SuccessResponse(data=adapters)


@router.post("/validate-llm", response_model=SuccessResponse[LLMValidationResponse])
async def validate_llm(config: LLMValidationRequest) -> SuccessResponse[LLMValidationResponse]:
    """Validate LLM configuration.

    Tests the provided LLM configuration by attempting a connection.
    This endpoint is always accessible without authentication during first-run.
    """
    validation_result = await _validate_llm_connection(config)
    return SuccessResponse(data=validation_result)


@router.post("/complete", response_model=SuccessResponse[Dict[str, str]])
async def complete_setup(setup: SetupCompleteRequest) -> SuccessResponse[Dict[str, str]]:
    """Complete initial setup.

    Saves configuration and creates initial admin user.
    Only accessible during first-run (no authentication required).
    After setup, authentication is required for reconfiguration.
    """
    # Only allow during first-run
    if not is_first_run():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup already completed. Use PUT /v1/setup/config to update configuration.",
        )

    # Validate new user password strength
    if len(setup.admin_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="New user password must be at least 8 characters"
        )

    # Validate system admin password strength if provided
    if setup.system_admin_password and len(setup.system_admin_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="System admin password must be at least 8 characters"
        )

    try:
        # Get config path
        config_path = get_default_config_path()
        config_dir = config_path.parent

        # Ensure directory exists
        config_dir.mkdir(parents=True, exist_ok=True)

        # Save configuration
        _save_setup_config(setup, config_path)

        # Save pending user creation (will be processed on next startup)
        _save_pending_users(setup, config_dir)

        # Build next steps message
        next_steps = "Restart the agent to apply configuration and create user accounts"
        if setup.system_admin_password:
            next_steps += ". The default admin password will be updated."

        return SuccessResponse(
            data={
                "status": "completed",
                "message": "Setup completed successfully",
                "config_path": str(config_path),
                "username": setup.admin_username,
                "next_steps": next_steps,
            }
        )

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/config", response_model=SuccessResponse[SetupConfigResponse])
async def get_current_config(request: Request) -> SuccessResponse[SetupConfigResponse]:
    """Get current configuration.

    Returns current setup configuration for editing.
    Requires authentication if setup is already completed.
    """
    # If not first-run, require authentication
    if not _is_setup_allowed_without_auth():
        # Manually get auth context from request
        try:
            from ..dependencies.auth import get_auth_context

            auth = await get_auth_context(request)
            if auth is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    # Read current config from environment
    config = SetupConfigResponse(
        llm_provider="openai" if os.getenv("OPENAI_API_BASE") is None else "other",
        llm_base_url=os.getenv("OPENAI_API_BASE"),
        llm_model=os.getenv("OPENAI_MODEL"),
        llm_api_key_set=bool(os.getenv("OPENAI_API_KEY")),
        template_id=os.getenv("CIRIS_TEMPLATE", "general"),
        enabled_adapters=os.getenv("CIRIS_ADAPTER", "api").split(","),
        agent_port=int(os.getenv("CIRIS_API_PORT", "8080")),
    )

    return SuccessResponse(data=config)


@router.put("/config", response_model=SuccessResponse[Dict[str, str]])
async def update_config(
    setup: SetupCompleteRequest, auth: AuthContext = Depends(get_auth_context)
) -> SuccessResponse[Dict[str, str]]:
    """Update configuration.

    Updates setup configuration after initial setup.
    Requires admin authentication.
    """
    # Check for admin role
    from ciris_engine.schemas.api.auth import UserRole

    if auth.role.level < UserRole.ADMIN.level:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    try:
        # Get config path
        config_path = get_default_config_path()

        # Save updated configuration
        _save_setup_config(setup, config_path)

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
