"""
Setup wizard endpoints for CIRIS first-run and reconfiguration.

Provides GUI-based setup wizard accessible at /v1/setup/*.
Replaces the CLI wizard for pip-installed CIRIS agents.
"""

import json
import logging
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
logger = logging.getLogger(__name__)

# Constants
FIELD_DESC_DISPLAY_NAME = "Display name"

# ============================================================================
# Request/Response Schemas
# ============================================================================


class LLMProvider(BaseModel):
    """LLM provider configuration."""

    id: str = Field(..., description="Provider ID (openai, local, other)")
    name: str = Field(..., description=FIELD_DESC_DISPLAY_NAME)
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
    name: str = Field(..., description=FIELD_DESC_DISPLAY_NAME)
    description: str = Field(..., description="Template description")
    identity: str = Field(..., description="Agent identity/purpose")
    example_use_cases: List[str] = Field(default_factory=list, description="Example use cases")
    supported_sops: List[str] = Field(
        default_factory=list, description="Supported Standard Operating Procedures (SOPs) for ticket workflows"
    )

    # Book VI Stewardship (REQUIRED for all templates)
    stewardship_tier: int = Field(
        ..., ge=1, le=5, description="Book VI Stewardship Tier (1-5, higher = more oversight)"
    )
    creator_id: str = Field(..., description="Creator/team identifier who signed this template")
    signature: str = Field(..., description="Cryptographic signature verifying template authenticity")


class AdapterConfig(BaseModel):
    """Adapter configuration."""

    id: str = Field(..., description="Adapter ID (api, cli, discord, reddit)")
    name: str = Field(..., description=FIELD_DESC_DISPLAY_NAME)
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

    # Primary LLM Configuration
    llm_provider: str = Field(..., description="LLM provider ID")
    llm_api_key: str = Field(..., description="LLM API key")
    llm_base_url: Optional[str] = Field(None, description="LLM base URL")
    llm_model: Optional[str] = Field(None, description="LLM model name")

    # Backup/Secondary LLM Configuration (Optional)
    backup_llm_api_key: Optional[str] = Field(None, description="Backup LLM API key (CIRIS_OPENAI_API_KEY_2)")
    backup_llm_base_url: Optional[str] = Field(None, description="Backup LLM base URL (CIRIS_OPENAI_API_BASE_2)")
    backup_llm_model: Optional[str] = Field(None, description="Backup LLM model name (CIRIS_OPENAI_MODEL_NAME_2)")

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

    # Primary LLM Configuration
    llm_provider: Optional[str] = Field(None, description="Current LLM provider")
    llm_base_url: Optional[str] = Field(None, description="Current LLM base URL")
    llm_model: Optional[str] = Field(None, description="Current LLM model")
    llm_api_key_set: bool = Field(False, description="Whether API key is configured")

    # Backup/Secondary LLM Configuration
    backup_llm_base_url: Optional[str] = Field(None, description="Backup LLM base URL")
    backup_llm_model: Optional[str] = Field(None, description="Backup LLM model")
    backup_llm_api_key_set: bool = Field(False, description="Whether backup API key is configured")

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
    """Get list of available agent templates from ciris_templates directory.

    Returns template metadata for GUI display including:
    - 4 default DSAR SOPs for GDPR compliance
    - Book VI Stewardship information with creator signature
    """
    import yaml

    from ciris_engine.logic.utils.path_resolution import get_template_directory
    from ciris_engine.schemas.config.agent import AgentTemplate as ConfigAgentTemplate

    templates: List[AgentTemplate] = []
    template_dir = get_template_directory()

    # Skip test.yaml and backup files
    skip_templates = {"test.yaml", "CIRIS_TEMPLATE_GUIDE.md"}

    for template_file in template_dir.glob("*.yaml"):
        if template_file.name in skip_templates or template_file.name.endswith(".backup"):
            continue

        try:
            with open(template_file, "r") as f:
                template_data = yaml.safe_load(f)

            # Load and validate template
            config_template = ConfigAgentTemplate(**template_data)

            # Extract SOP names from tickets config
            supported_sops: List[str] = []
            if config_template.tickets and config_template.tickets.sops:
                supported_sops = [sop.sop for sop in config_template.tickets.sops]

            # Extract stewardship info
            stewardship_tier = 3  # Default medium risk
            creator_id = "Unknown"
            signature = "unsigned"

            if config_template.stewardship:
                stewardship_tier = config_template.stewardship.stewardship_tier
                creator_id = config_template.stewardship.creator_ledger_entry.creator_id
                signature = config_template.stewardship.creator_ledger_entry.signature

            # Create API response template
            template = AgentTemplate(
                id=template_file.stem,  # Use filename without .yaml as ID
                name=config_template.name,
                description=config_template.description,
                identity=config_template.role_description,
                example_use_cases=[],  # Can be added to template schema later
                supported_sops=supported_sops,
                stewardship_tier=stewardship_tier,
                creator_id=creator_id,
                signature=signature,
            )

            templates.append(template)

        except Exception as e:
            # Log but don't fail - skip invalid templates
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to load template {template_file}: {e}")
            continue

    return templates


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


def _validate_api_key_for_provider(config: LLMValidationRequest) -> Optional[LLMValidationResponse]:
    """Validate API key based on provider type.

    Returns:
        LLMValidationResponse if validation fails, None if valid
    """
    if config.provider == "openai":
        if not config.api_key or config.api_key == "your_openai_api_key_here":
            return LLMValidationResponse(
                valid=False,
                message="Invalid API key",
                error="OpenAI requires a valid API key starting with 'sk-'",
            )
    elif config.provider != "local" and not config.api_key:
        # Other non-local providers need API key
        return LLMValidationResponse(valid=False, message="API key required", error="This provider requires an API key")
    return None


def _classify_llm_connection_error(error: Exception, base_url: Optional[str]) -> LLMValidationResponse:
    """Classify and format LLM connection errors.

    Args:
        error: The exception that occurred
        base_url: The base URL being connected to

    Returns:
        Formatted error response
    """
    error_str = str(error)

    if "401" in error_str or "Unauthorized" in error_str:
        return LLMValidationResponse(
            valid=False,
            message="Authentication failed",
            error="Invalid API key. Please check your credentials.",
        )
    if "404" in error_str or "Not Found" in error_str:
        return LLMValidationResponse(
            valid=False,
            message="Endpoint not found",
            error=f"Could not reach {base_url}. Please check the URL.",
        )
    if "timeout" in error_str.lower():
        return LLMValidationResponse(
            valid=False,
            message="Connection timeout",
            error="Could not connect to LLM server. Please check if it's running.",
        )
    return LLMValidationResponse(valid=False, message="Connection failed", error=f"Error: {error_str}")


async def _validate_llm_connection(config: LLMValidationRequest) -> LLMValidationResponse:
    """Validate LLM configuration by attempting a connection.

    Args:
        config: LLM configuration to validate

    Returns:
        Validation response with success/failure status
    """
    try:
        # Validate API key for provider type
        api_key_error = _validate_api_key_for_provider(config)
        if api_key_error:
            return api_key_error

        # Import OpenAI client
        from openai import AsyncOpenAI

        # Build client configuration
        client_kwargs: Dict[str, Any] = {"api_key": config.api_key or "local"}  # Local LLMs can use placeholder
        if config.base_url:
            client_kwargs["base_url"] = config.base_url

        # Create client and test connection
        client = AsyncOpenAI(**client_kwargs)

        try:
            models = await client.models.list()
            model_count = len(models.data) if hasattr(models, "data") else 0

            return LLMValidationResponse(
                valid=True,
                message=f"Connection successful! Found {model_count} available models.",
                error=None,
            )
        except Exception as e:
            return _classify_llm_connection_error(e, config.base_url)

    except Exception as e:
        return LLMValidationResponse(valid=False, message="Validation error", error=str(e))


async def _create_setup_users(setup: SetupCompleteRequest, auth_db_path: str) -> None:
    """Create users immediately during setup completion.

    This is called during setup completion to create users without waiting for restart.
    Creates users directly in the database using authentication store functions.

    Args:
        setup: Setup configuration with user details
        auth_db_path: Path to the audit database (from running application)
    """
    from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService
    from ciris_engine.logic.services.lifecycle.time.service import TimeService
    from ciris_engine.schemas.services.authority_core import WARole

    logger.info("Creating setup users immediately...")
    logger.info(f"📁 [SETUP DEBUG] Using auth database path: {auth_db_path}")

    # Create temporary authentication service for user creation
    time_service = TimeService()
    await time_service.start()

    auth_service = AuthenticationService(
        db_path=auth_db_path, time_service=time_service, key_dir=None  # Use default ~/.ciris/
    )
    await auth_service.start()

    try:
        # Create new user with AUTHORITY role (setup wizard always creates admin)
        wa_role = WARole.AUTHORITY

        logger.info(f"Creating user: {setup.admin_username} with role: {wa_role}")

        # Create WA certificate
        wa_cert = await auth_service.create_wa(
            name=setup.admin_username,
            email=f"{setup.admin_username}@local",
            scopes=["read:any", "write:any"] if wa_role == WARole.AUTHORITY else ["read:any"],
            role=wa_role,
        )

        # Hash password and update WA
        password_hash = auth_service.hash_password(setup.admin_password)
        await auth_service.update_wa(wa_id=wa_cert.wa_id, password_hash=password_hash)

        logger.info(f"✅ Created user: {setup.admin_username} (WA: {wa_cert.wa_id})")

        # Update default admin password if specified
        if setup.system_admin_password:
            logger.info("Updating default admin password...")
            all_was = await auth_service.list_was(active_only=True)
            admin_wa = next((wa for wa in all_was if wa.name == "admin" and wa.wa_id != wa_cert.wa_id), None)

            if admin_wa:
                admin_password_hash = auth_service.hash_password(setup.system_admin_password)
                await auth_service.update_wa(wa_id=admin_wa.wa_id, password_hash=admin_password_hash)
                logger.info("✅ Updated admin password")
            else:
                logger.warning("⚠️  Default admin WA not found")

    finally:
        await auth_service.stop()
        await time_service.stop()


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
        f.write("\n# Agent Template\n")
        f.write(f"CIRIS_TEMPLATE={setup.template_id}\n")

        # Adapter configuration
        f.write("\n# Enabled Adapters\n")
        adapters_str = ",".join(setup.enabled_adapters)
        f.write(f"CIRIS_ADAPTER={adapters_str}\n")

        # Adapter-specific environment variables
        if setup.adapter_config:
            f.write("\n# Adapter-Specific Configuration\n")
            for key, value in setup.adapter_config.items():
                f.write(f"{key}={value}\n")

        # Backup/Secondary LLM Configuration (Optional)
        if setup.backup_llm_api_key:
            f.write("\n# Backup/Secondary LLM Configuration\n")
            f.write(f'CIRIS_OPENAI_API_KEY_2="{setup.backup_llm_api_key}"\n')
            if setup.backup_llm_base_url:
                f.write(f'CIRIS_OPENAI_API_BASE_2="{setup.backup_llm_base_url}"\n')
            if setup.backup_llm_model:
                f.write(f'CIRIS_OPENAI_MODEL_NAME_2="{setup.backup_llm_model}"\n')


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
async def complete_setup(setup: SetupCompleteRequest, request: Request) -> SuccessResponse[Dict[str, str]]:
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

        # Reload environment variables from the new .env file
        from dotenv import load_dotenv

        load_dotenv(config_path, override=True)
        logger.info(f"Reloaded environment variables from {config_path}")

        # Get runtime and database path from the running application
        runtime = getattr(request.app.state, "runtime", None)
        if not runtime:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Runtime not available - cannot complete setup",
            )

        # Get audit database path from runtime's essential config
        auth_db_path = str(runtime.essential_config.database.audit_db)
        logger.info(f"Using runtime audit database: {auth_db_path}")

        # Create users immediately (don't wait for restart)
        await _create_setup_users(setup, auth_db_path)

        # Reload user cache in APIAuthService to pick up newly created users
        auth_service = getattr(request.app.state, "auth_service", None)
        if auth_service:
            logger.info("Reloading user cache after setup user creation...")
            await auth_service.reload_users_from_db()
            logger.info("✅ User cache reloaded - new users now visible to authentication")

        # Build next steps message
        next_steps = "Configuration completed. The agent is now starting. You can log in immediately."
        if setup.system_admin_password:
            next_steps += " Both user passwords have been configured."

        # Resume initialization from first-run mode to start agent processor
        logger.info("Setup complete - resuming initialization to start agent processor")
        # Schedule resume in background to allow response to be sent first
        import asyncio

        async def _resume_runtime() -> None:
            await asyncio.sleep(0.5)  # Brief delay to ensure response is sent
            try:
                await runtime.resume_from_first_run()
                logger.info("✅ Successfully resumed from first-run mode - agent processor running")
            except Exception as e:
                logger.error(f"Failed to resume from first-run: {e}", exc_info=True)
                # If resume fails, fall back to restart
                runtime.request_shutdown("Resume failed - restarting to apply configuration")

        # Store task to prevent garbage collection and log task creation
        resume_task = asyncio.create_task(_resume_runtime())
        logger.info(f"Scheduled background resume task: {resume_task.get_name()}")

        return SuccessResponse(
            data={
                "status": "completed",
                "message": "Setup completed successfully. Starting agent processor...",
                "config_path": str(config_path),
                "username": setup.admin_username,
                "next_steps": next_steps,
            }
        )

    except Exception as e:
        logger.error(f"Setup completion failed: {e}", exc_info=True)
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
        backup_llm_base_url=os.getenv("CIRIS_OPENAI_API_BASE_2"),
        backup_llm_model=os.getenv("CIRIS_OPENAI_MODEL_NAME_2"),
        backup_llm_api_key_set=bool(os.getenv("CIRIS_OPENAI_API_KEY_2")),
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
