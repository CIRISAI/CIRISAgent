"""
Setup wizard endpoints for CIRIS first-run and reconfiguration.

Provides GUI-based setup wizard accessible at /v1/setup/*.
Replaces the CLI wizard for pip-installed CIRIS agents.
"""

import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ciris_engine.logic.config.db_paths import get_audit_db_full_path
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
    platform_requirements: List[str] = Field(
        default_factory=list, description="Platform requirements (e.g., 'android_play_integrity')"
    )
    platform_available: bool = Field(True, description="Whether available on current platform")


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
    admin_password: Optional[str] = Field(
        None,
        description="New user's password (min 8 characters). Optional for OAuth users - if not provided, a random password is generated and password auth is disabled for this user.",
    )
    system_admin_password: Optional[str] = Field(
        None, description="System admin password to replace default (min 8 characters, optional)"
    )
    # OAuth indicator - frontend sets this when user authenticated via OAuth (Google, etc.)
    oauth_provider: Optional[str] = Field(
        None, description="OAuth provider used for authentication (e.g., 'google'). If set, local password is optional."
    )
    oauth_external_id: Optional[str] = Field(
        None, description="OAuth external ID (e.g., Google user ID). Required if oauth_provider is set."
    )
    oauth_email: Optional[str] = Field(None, description="OAuth email address from the provider.")

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
            description="Official OpenAI API (GPT-4, GPT-5.2, etc.)",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url=None,
            default_model="gpt-5.2",
            examples=[
                "Standard OpenAI API",
                "Azure OpenAI Service",
            ],
        ),
        LLMProvider(
            id="anthropic",
            name="Anthropic",
            description="Claude models (Claude 3.5 Sonnet, Opus, Haiku)",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url=None,
            default_model="claude-3-5-sonnet-20241022",
            examples=[
                "Claude 3.5 Sonnet",
                "Claude 3 Opus",
            ],
        ),
        LLMProvider(
            id="openrouter",
            name="OpenRouter",
            description="Access 100+ models via OpenRouter",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url="https://openrouter.ai/api/v1",
            default_model="meta-llama/llama-4-maverick",
            examples=[
                "Llama 4 Maverick",
                "GPT-4o via OpenRouter",
            ],
        ),
        LLMProvider(
            id="groq",
            name="Groq",
            description="Ultra-fast LPU inference (Llama 3.3, Mixtral)",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url="https://api.groq.com/openai/v1",
            default_model="llama-3.3-70b-versatile",
            examples=[
                "Llama 3.3 70B Versatile",
                "Llama 3.2 90B Vision",
            ],
        ),
        LLMProvider(
            id="together",
            name="Together AI",
            description="High-performance open models",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url="https://api.together.xyz/v1",
            default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
            examples=[
                "Llama 3.3 70B Turbo",
                "Llama Vision Free",
            ],
        ),
        LLMProvider(
            id="google",
            name="Google AI",
            description="Gemini models (Gemini 2.0, 1.5 Pro)",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url="https://generativelanguage.googleapis.com/v1beta",
            default_model="gemini-2.0-flash-exp",
            examples=[
                "Gemini 2.0 Flash",
                "Gemini 1.5 Pro",
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
            name="Other",
            description="Any OpenAI-compatible API endpoint",
            requires_api_key=True,
            requires_base_url=True,
            requires_model=True,
            default_base_url=None,
            default_model=None,
            examples=[
                "Custom endpoints",
                "Private deployments",
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

    logger.info(f"[SETUP TEMPLATES] Loading templates from: {template_dir}")
    logger.info(f"[SETUP TEMPLATES] Directory exists: {template_dir.exists()}")

    # Skip test.yaml and backup files
    skip_templates = {"test.yaml", "CIRIS_TEMPLATE_GUIDE.md"}

    yaml_files = list(template_dir.glob("*.yaml"))
    logger.info(f"[SETUP TEMPLATES] Found {len(yaml_files)} .yaml files: {[f.name for f in yaml_files]}")

    for template_file in yaml_files:
        if template_file.name in skip_templates or template_file.name.endswith(".backup"):
            logger.info(f"[SETUP TEMPLATES] Skipping: {template_file.name}")
            continue

        try:
            logger.info(f"[SETUP TEMPLATES] Loading: {template_file.name}")
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
            logger.info(f"[SETUP TEMPLATES] Loaded: id={template.id}, name={template.name}")

        except Exception as e:
            logger.warning(f"[SETUP TEMPLATES] Failed to load template {template_file}: {e}")
            continue

    logger.info(f"[SETUP TEMPLATES] Total templates loaded: {len(templates)}")
    logger.info(f"[SETUP TEMPLATES] Template IDs: {[t.id for t in templates]}")
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
    logger.info("[VALIDATE_LLM] " + "=" * 50)
    logger.info(f"[VALIDATE_LLM] Starting validation for provider: {config.provider}")
    logger.info(
        f"[VALIDATE_LLM] API key provided: {bool(config.api_key)} (length: {len(config.api_key) if config.api_key else 0})"
    )
    logger.info(
        f"[VALIDATE_LLM] API key prefix: {config.api_key[:20] + '...' if config.api_key and len(config.api_key) > 20 else config.api_key}"
    )
    logger.info(f"[VALIDATE_LLM] Base URL: {config.base_url}")
    logger.info(f"[VALIDATE_LLM] Model: {config.model}")

    try:
        # Validate API key for provider type
        api_key_error = _validate_api_key_for_provider(config)
        if api_key_error:
            logger.warning(f"[VALIDATE_LLM] API key validation FAILED: {api_key_error.error}")
            return api_key_error

        logger.info("[VALIDATE_LLM] API key format validation passed")

        # Import OpenAI client
        from openai import AsyncOpenAI

        # Build client configuration
        client_kwargs: Dict[str, Any] = {"api_key": config.api_key or "local"}  # Local LLMs can use placeholder
        if config.base_url:
            client_kwargs["base_url"] = config.base_url

        logger.info(f"[VALIDATE_LLM] Creating OpenAI client with base_url: {client_kwargs.get('base_url', 'default')}")

        # Create client and test connection
        client = AsyncOpenAI(**client_kwargs)

        try:
            logger.info("[VALIDATE_LLM] Attempting to list models from API...")
            models = await client.models.list()
            model_count = len(models.data) if hasattr(models, "data") else 0

            logger.info(f"[VALIDATE_LLM] SUCCESS! Found {model_count} models")
            return LLMValidationResponse(
                valid=True,
                message=f"Connection successful! Found {model_count} available models.",
                error=None,
            )
        except Exception as e:
            logger.error(f"[VALIDATE_LLM] API call FAILED: {type(e).__name__}: {e}")
            result = _classify_llm_connection_error(e, config.base_url)
            logger.error(f"[VALIDATE_LLM] Classified error - valid: {result.valid}, error: {result.error}")
            return result

    except Exception as e:
        logger.error(f"[VALIDATE_LLM] Unexpected error: {type(e).__name__}: {e}")
        return LLMValidationResponse(valid=False, message="Validation error", error=str(e))


# =============================================================================
# SETUP USER HELPER FUNCTIONS (extracted for cognitive complexity reduction)
# =============================================================================


async def _link_oauth_identity_to_wa(auth_service: Any, setup: "SetupCompleteRequest", wa_cert: Any) -> Any:
    """Link OAuth identity to WA, handling existing links gracefully.

    Returns the WA cert to use (may be updated if existing link found).
    """
    from ciris_engine.schemas.services.authority_core import WARole

    logger.debug("CIRIS_SETUP_DEBUG *** ENTERING OAuth linking block ***")
    logger.debug(  # NOSONAR - provider:external_id is not a secret, it's a provider-assigned ID
        f"CIRIS_SETUP_DEBUG Linking OAuth identity: {setup.oauth_provider}:{setup.oauth_external_id} to WA {wa_cert.wa_id}"
    )

    try:
        # First check if OAuth identity is already linked to another WA
        existing_wa = await auth_service.get_wa_by_oauth(setup.oauth_provider, setup.oauth_external_id)
        if existing_wa and existing_wa.wa_id != wa_cert.wa_id:
            logger.info(f"CIRIS_SETUP_DEBUG OAuth identity already linked to WA {existing_wa.wa_id}")
            logger.info(
                "CIRIS_SETUP_DEBUG During first-run setup, we'll update the existing WA to be ROOT instead of creating new"
            )
            # Update the existing WA to have ROOT role and update its name
            await auth_service.update_wa(
                wa_id=existing_wa.wa_id,
                name=setup.admin_username,
                role=WARole.ROOT,
            )
            logger.info(f"CIRIS_SETUP_DEBUG ✅ Updated existing WA {existing_wa.wa_id} to ROOT role")
            return existing_wa

        # No existing link or same WA - safe to link
        await auth_service.link_oauth_identity(
            wa_id=wa_cert.wa_id,
            provider=setup.oauth_provider,
            external_id=setup.oauth_external_id,
            account_name=setup.admin_username,
            metadata={"email": setup.oauth_email} if setup.oauth_email else None,
            primary=True,
        )
        logger.debug(  # NOSONAR - provider:external_id is not a secret
            f"CIRIS_SETUP_DEBUG ✅ SUCCESS: Linked OAuth {setup.oauth_provider}:{setup.oauth_external_id} to WA {wa_cert.wa_id}"
        )
    except Exception as e:
        logger.error(f"CIRIS_SETUP_DEBUG ❌ FAILED to link OAuth identity: {e}", exc_info=True)
        # Don't fail setup if OAuth linking fails - user can still use password

    return wa_cert


def _log_oauth_linking_skip(setup: "SetupCompleteRequest") -> None:
    """Log debug information when OAuth linking is skipped."""
    logger.info("CIRIS_SETUP_DEBUG *** SKIPPING OAuth linking block - condition not met ***")
    if not setup.oauth_provider:
        logger.info("CIRIS_SETUP_DEBUG   Reason: oauth_provider is falsy/empty")
    if not setup.oauth_external_id:
        logger.info("CIRIS_SETUP_DEBUG   Reason: oauth_external_id is falsy/empty")


async def _update_system_admin_password(auth_service: Any, setup: "SetupCompleteRequest", exclude_wa_id: str) -> None:
    """Update the default admin password if specified."""
    if not setup.system_admin_password:
        return

    logger.info("Updating default admin password...")
    all_was = await auth_service.list_was(active_only=True)
    admin_wa = next((wa for wa in all_was if wa.name == "admin" and wa.wa_id != exclude_wa_id), None)

    if admin_wa:
        admin_password_hash = auth_service.hash_password(setup.system_admin_password)
        await auth_service.update_wa(wa_id=admin_wa.wa_id, password_hash=admin_password_hash)
        logger.info("✅ Updated admin password")
    else:
        logger.warning("⚠️  Default admin WA not found")


async def _check_existing_oauth_wa(auth_service: Any, setup: "SetupCompleteRequest") -> tuple[Optional[Any], bool]:
    """Check if OAuth user already exists and update to ROOT if found.

    Returns:
        Tuple of (wa_cert, was_found) where wa_cert is the WA certificate and
        was_found indicates if an existing WA was found and updated.
    """
    from ciris_engine.schemas.services.authority_core import WARole

    if not (setup.oauth_provider and setup.oauth_external_id):
        return None, False

    logger.debug(  # NOSONAR - provider:external_id is not a secret
        f"CIRIS_USER_CREATE: Checking for existing OAuth user: {setup.oauth_provider}:{setup.oauth_external_id}"
    )
    existing_wa = await auth_service.get_wa_by_oauth(setup.oauth_provider, setup.oauth_external_id)

    if not existing_wa:
        logger.info("CIRIS_USER_CREATE: No existing WA found for OAuth user - will create new")
        return None, False

    logger.info(f"CIRIS_USER_CREATE: ✓ Found existing WA for OAuth user: {existing_wa.wa_id}")
    logger.info(f"CIRIS_USER_CREATE:   Current role: {existing_wa.role}")
    logger.info(f"CIRIS_USER_CREATE:   Current name: {existing_wa.name}")

    # Update existing WA to ROOT role instead of creating new one
    logger.info(
        f"CIRIS_USER_CREATE: Updating existing WA {existing_wa.wa_id} to ROOT role (keeping name: {existing_wa.name})"
    )
    await auth_service.update_wa(wa_id=existing_wa.wa_id, role=WARole.ROOT)
    logger.info(f"CIRIS_USER_CREATE: ✅ Updated existing OAuth WA to ROOT: {existing_wa.wa_id}")

    return existing_wa, True


async def _create_new_wa(auth_service: Any, setup: "SetupCompleteRequest") -> Any:
    """Create a new WA certificate for the setup user.

    Returns:
        WA certificate for the newly created user
    """
    from ciris_engine.schemas.services.authority_core import WARole

    logger.info(f"CIRIS_USER_CREATE: Creating NEW user: {setup.admin_username} with role: {WARole.ROOT}")

    # Use OAuth email if available, otherwise generate local email
    user_email = setup.oauth_email or f"{setup.admin_username}@local"
    masked_email = (user_email[:3] + "***@" + user_email.split("@")[-1]) if "@" in user_email else user_email
    logger.debug(f"CIRIS_USER_CREATE: User email: {masked_email}")  # NOSONAR - email masked

    # List existing WAs before creation for debugging
    existing_was = await auth_service.list_was(active_only=False)
    logger.info(f"CIRIS_USER_CREATE: Existing WAs before creation: {len(existing_was)}")
    for wa in existing_was:
        logger.info(f"CIRIS_USER_CREATE:   - {wa.wa_id}: name={wa.name}, role={wa.role}")

    # Create WA certificate
    wa_cert = await auth_service.create_wa(
        name=setup.admin_username,
        email=user_email,
        scopes=["read:any", "write:any"],  # ROOT gets full scopes
        role=WARole.ROOT,
    )
    logger.info(f"CIRIS_USER_CREATE: ✅ Created NEW WA: {wa_cert.wa_id}")

    return wa_cert


async def _set_password_for_wa(auth_service: Any, setup: "SetupCompleteRequest", wa_cert: Any) -> None:
    """Set password hash for non-OAuth users."""
    is_oauth_setup = bool(setup.oauth_provider and setup.oauth_external_id)

    if is_oauth_setup:
        logger.info(f"CIRIS_USER_CREATE: Skipping password hash for OAuth user: {wa_cert.wa_id}")
        return

    # Hash password and update WA (admin_password is guaranteed set by validation above)
    assert setup.admin_password is not None, "admin_password should be set by validation"
    password_hash = auth_service.hash_password(setup.admin_password)
    await auth_service.update_wa(wa_id=wa_cert.wa_id, password_hash=password_hash)
    logger.info(f"CIRIS_USER_CREATE: Password hash set for WA: {wa_cert.wa_id}")


async def _ensure_system_wa(auth_service: Any) -> None:
    """Ensure system WA exists for signing system tasks."""
    system_wa_id = await auth_service.ensure_system_wa_exists()
    if system_wa_id:
        logger.info(f"✅ System WA ready: {system_wa_id}")
    else:
        logger.warning("⚠️ Could not create system WA - deferral handling may not work")


async def _log_wa_list(auth_service: Any, phase: str) -> None:
    """Log list of WAs for debugging purposes."""
    was = await auth_service.list_was(active_only=False)
    logger.info(f"CIRIS_USER_CREATE: WAs {phase}: {len(was)}")
    for wa in was:
        logger.info(f"CIRIS_USER_CREATE:   - {wa.wa_id}: name={wa.name}, role={wa.role}")


async def _create_setup_users(setup: SetupCompleteRequest, auth_db_path: str) -> None:
    """Create users immediately during setup completion.

    This is called during setup completion to create users without waiting for restart.
    Creates users directly in the database using authentication store functions.

    IMPORTANT: For OAuth users, we check if they already exist and update to ROOT instead
    of creating a duplicate WA. This prevents multiple ROOT users from being created.

    Args:
        setup: Setup configuration with user details
        auth_db_path: Path to the audit database (from running application)
    """
    from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService
    from ciris_engine.logic.services.lifecycle.time.service import TimeService

    logger.info("=" * 70)
    logger.info("CIRIS_USER_CREATE: _create_setup_users() called")
    logger.info("=" * 70)
    logger.info(f"CIRIS_USER_CREATE: auth_db_path = {auth_db_path}")
    logger.info(f"CIRIS_USER_CREATE: admin_username = {setup.admin_username}")
    logger.info(f"CIRIS_USER_CREATE: oauth_provider = {repr(setup.oauth_provider)}")
    logger.info(f"CIRIS_USER_CREATE: oauth_external_id = {repr(setup.oauth_external_id)}")
    logger.info(f"CIRIS_USER_CREATE: oauth_email = {repr(setup.oauth_email)}")

    # Create temporary authentication service for user creation
    time_service = TimeService()
    await time_service.start()

    auth_service = AuthenticationService(
        db_path=auth_db_path, time_service=time_service, key_dir=None  # Use default ~/.ciris/
    )
    await auth_service.start()

    try:
        # Check if OAuth user already exists and update to ROOT if found
        wa_cert, _ = await _check_existing_oauth_wa(auth_service, setup)

        # Create new WA if we didn't find an existing OAuth user
        if wa_cert is None:
            wa_cert = await _create_new_wa(auth_service, setup)

        # Set password for non-OAuth users
        await _set_password_for_wa(auth_service, setup, wa_cert)

        # Log WAs after creation for debugging
        await _log_wa_list(auth_service, "after setup")

        # Ensure system WA exists
        await _ensure_system_wa(auth_service)

        # CIRIS_SETUP_DEBUG: Log OAuth linking decision
        logger.debug("CIRIS_SETUP_DEBUG _create_setup_users() OAuth linking check:")
        logger.debug(f"CIRIS_SETUP_DEBUG   setup.oauth_provider = {repr(setup.oauth_provider)}")
        logger.debug(f"CIRIS_SETUP_DEBUG   setup.oauth_external_id = {repr(setup.oauth_external_id)}")
        logger.debug(f"CIRIS_SETUP_DEBUG   bool(setup.oauth_provider) = {bool(setup.oauth_provider)}")
        logger.debug(f"CIRIS_SETUP_DEBUG   bool(setup.oauth_external_id) = {bool(setup.oauth_external_id)}")
        oauth_link_condition = bool(setup.oauth_provider) and bool(setup.oauth_external_id)
        logger.debug(f"CIRIS_SETUP_DEBUG   Condition (provider AND external_id) = {oauth_link_condition}")

        # Link OAuth identity if provided - THIS IS CRITICAL for OAuth login to work
        if setup.oauth_provider and setup.oauth_external_id:
            wa_cert = await _link_oauth_identity_to_wa(auth_service, setup, wa_cert)
        else:
            _log_oauth_linking_skip(setup)

        # Update default admin password if specified
        assert wa_cert is not None, "wa_cert should be set by create_wa or existing WA lookup"
        await _update_system_admin_password(auth_service, setup, wa_cert.wa_id)

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


def _validate_setup_passwords(setup: SetupCompleteRequest, is_oauth_user: bool) -> str:
    """Validate and potentially generate admin password for setup.

    For OAuth users without a password, generates a secure random password.
    For non-OAuth users, validates password requirements.

    Args:
        setup: Setup configuration request
        is_oauth_user: Whether user is authenticating via OAuth

    Returns:
        Validated or generated admin password

    Raises:
        HTTPException: If password validation fails
    """
    admin_password = setup.admin_password

    if not admin_password or len(admin_password) == 0:
        if is_oauth_user:
            # Generate a secure random password for OAuth users
            # They won't use this password - they'll authenticate via OAuth
            admin_password = secrets.token_urlsafe(32)
            logger.info("[Setup Complete] Generated random password for OAuth user (password auth disabled)")
        else:
            # Non-OAuth users MUST provide a password
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="New user password must be at least 8 characters"
            )
    elif len(admin_password) < 8:
        # If a password was provided, it must meet minimum requirements
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="New user password must be at least 8 characters"
        )

    # Validate system admin password strength if provided
    if setup.system_admin_password and len(setup.system_admin_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="System admin password must be at least 8 characters"
        )

    return admin_password


def _save_and_reload_config(setup: SetupCompleteRequest) -> Path:
    """Save setup configuration to .env and reload environment variables.

    Args:
        setup: Setup configuration request

    Returns:
        Path to the saved configuration file
    """
    from dotenv import load_dotenv

    from ciris_engine.logic.utils.path_resolution import get_ciris_home, is_android, is_development_mode

    logger.info("[Setup Complete] Path resolution:")
    logger.info(f"[Setup Complete]   is_android(): {is_android()}")
    logger.info(f"[Setup Complete]   is_development_mode(): {is_development_mode()}")
    logger.info(f"[Setup Complete]   get_ciris_home(): {get_ciris_home()}")

    config_path = get_default_config_path()
    config_dir = config_path.parent
    logger.info(f"[Setup Complete]   config_path: {config_path}")
    logger.info(f"[Setup Complete]   config_dir: {config_dir}")

    # Ensure directory exists
    config_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"[Setup Complete] Directory ensured: {config_dir}")

    # Save configuration
    logger.info(f"[Setup Complete] Saving configuration to: {config_path}")
    _save_setup_config(setup, config_path)
    logger.info("[Setup Complete] Configuration saved successfully!")

    # Verify the file was written
    if config_path.exists():
        file_size = config_path.stat().st_size
        logger.info(f"[Setup Complete] Verified: .env exists ({file_size} bytes)")
    else:
        logger.error(f"[Setup Complete] ERROR: .env file NOT found at {config_path} after save!")

    # Reload environment variables from the new .env file
    load_dotenv(config_path, override=True)
    logger.info(f"[Setup Complete] Reloaded environment variables from {config_path}")

    # Verify key env vars were loaded
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_base = os.getenv("OPENAI_API_BASE")
    logger.info(f"[Setup Complete] After reload - OPENAI_API_KEY: {openai_key[:20] if openai_key else '(not set)'}...")
    logger.info(f"[Setup Complete] After reload - OPENAI_API_BASE: {openai_base}")

    return config_path


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


@router.get("/models")
async def get_model_capabilities_endpoint() -> SuccessResponse[Dict[str, Any]]:
    """Get CIRIS-compatible LLM model capabilities.

    Returns the on-device model capabilities database for BYOK model selection.
    Used by the wizard's Advanced settings to show compatible models per provider.
    This endpoint is always accessible without authentication.

    Returns model info including:
    - CIRIS compatibility requirements (128K+ context, tool use, vision)
    - Per-provider model listings with capability flags
    - Tiers (default, fast, fallback, premium)
    - Recommendations and rejection reasons
    """
    from ciris_engine.config import get_model_capabilities

    try:
        config = get_model_capabilities()

        # Convert to dict for JSON response
        return SuccessResponse(
            data={
                "version": config.version,
                "last_updated": config.last_updated.isoformat(),
                "ciris_requirements": config.ciris_requirements.model_dump(),
                "providers": {
                    provider_id: {
                        "display_name": provider.display_name,
                        "api_base": provider.api_base,
                        "models": {model_id: model.model_dump() for model_id, model in provider.models.items()},
                    }
                    for provider_id, provider in config.providers.items()
                },
                "tiers": {tier_id: tier.model_dump() for tier_id, tier in config.tiers.items()},
                "rejected_models": {model_id: model.model_dump() for model_id, model in config.rejected_models.items()},
            }
        )
    except Exception as e:
        logger.error(f"Failed to load model capabilities: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load model capabilities: {str(e)}",
        )


@router.get("/models/{provider_id}")
async def get_provider_models(provider_id: str) -> SuccessResponse[Dict[str, Any]]:
    """Get CIRIS-compatible models for a specific provider.

    Returns models for the given provider with compatibility information.
    Used by the wizard to populate model dropdown after provider selection.
    """
    from ciris_engine.config import get_model_capabilities

    try:
        config = get_model_capabilities()

        if provider_id not in config.providers:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Provider '{provider_id}' not found")

        provider = config.providers[provider_id]
        compatible_models = []
        incompatible_models = []

        for model_id, model in provider.models.items():
            model_data = {
                "id": model_id,
                **model.model_dump(),
            }
            if model.ciris_compatible:
                compatible_models.append(model_data)
            else:
                incompatible_models.append(model_data)

        # Sort: recommended first, then by display name
        compatible_models.sort(key=lambda m: (not m.get("ciris_recommended", False), m["display_name"]))

        return SuccessResponse(
            data={
                "provider_id": provider_id,
                "display_name": provider.display_name,
                "api_base": provider.api_base,
                "compatible_models": compatible_models,
                "incompatible_models": incompatible_models,
                "ciris_requirements": config.ciris_requirements.model_dump(),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get provider models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get provider models: {str(e)}",
        )


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
    # CIRIS_SETUP_DEBUG: Comprehensive logging for OAuth identity linking
    logger.info("CIRIS_SETUP_DEBUG " + "=" * 60)
    logger.info("CIRIS_SETUP_DEBUG complete_setup() endpoint called")
    logger.info("CIRIS_SETUP_DEBUG " + "=" * 60)

    # Log ALL OAuth-related fields received from frontend
    logger.info("CIRIS_SETUP_DEBUG OAuth fields received from frontend:")
    logger.info(f"CIRIS_SETUP_DEBUG   oauth_provider = {repr(setup.oauth_provider)}")
    logger.info(f"CIRIS_SETUP_DEBUG   oauth_external_id = {repr(setup.oauth_external_id)}")
    logger.info(f"CIRIS_SETUP_DEBUG   oauth_email = {repr(setup.oauth_email)}")

    # Check truthiness explicitly
    logger.debug("CIRIS_SETUP_DEBUG Truthiness checks:")
    logger.debug(f"CIRIS_SETUP_DEBUG   bool(oauth_provider) = {bool(setup.oauth_provider)}")
    logger.debug(f"CIRIS_SETUP_DEBUG   bool(oauth_external_id) = {bool(setup.oauth_external_id)}")
    logger.debug(f"CIRIS_SETUP_DEBUG   oauth_external_id is None = {setup.oauth_external_id is None}")
    logger.debug(f"CIRIS_SETUP_DEBUG   oauth_external_id == '' = {setup.oauth_external_id == ''}")

    # The critical check that determines OAuth linking
    will_link_oauth = bool(setup.oauth_provider) and bool(setup.oauth_external_id)
    logger.debug(
        f"CIRIS_SETUP_DEBUG CRITICAL: Will OAuth linking happen? = {will_link_oauth}"
    )  # NOSONAR - boolean status only
    if not will_link_oauth:
        if not setup.oauth_provider:
            logger.debug("CIRIS_SETUP_DEBUG   Reason: oauth_provider is falsy")
        if not setup.oauth_external_id:
            logger.debug("CIRIS_SETUP_DEBUG   Reason: oauth_external_id is falsy")

    # Log other setup fields
    logger.debug("CIRIS_SETUP_DEBUG Other setup fields:")
    logger.debug(f"CIRIS_SETUP_DEBUG   admin_username = {setup.admin_username}")
    logger.debug(
        f"CIRIS_SETUP_DEBUG   admin_password set = {bool(setup.admin_password)}"
    )  # NOSONAR - boolean only, not password
    logger.debug(
        f"CIRIS_SETUP_DEBUG   system_admin_password set = {bool(setup.system_admin_password)}"
    )  # NOSONAR - boolean only
    logger.debug(f"CIRIS_SETUP_DEBUG   llm_provider = {setup.llm_provider}")
    logger.debug(f"CIRIS_SETUP_DEBUG   template_id = {setup.template_id}")

    # Only allow during first-run
    if not is_first_run():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup already completed. Use PUT /v1/setup/config to update configuration.",
        )

    # Determine if this is an OAuth user (password is optional for OAuth users)
    is_oauth_user = bool(setup.oauth_provider)
    logger.debug(
        f"CIRIS_SETUP_DEBUG is_oauth_user (for password validation) = {is_oauth_user}"
    )  # NOSONAR - boolean only

    # Validate passwords and potentially generate for OAuth users
    setup.admin_password = _validate_setup_passwords(setup, is_oauth_user)

    try:
        # Save configuration and reload environment variables
        config_path = _save_and_reload_config(setup)

        # Get runtime and database path from the running application
        runtime = getattr(request.app.state, "runtime", None)
        if not runtime:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Runtime not available - cannot complete setup",
            )

        # Get audit database path using same resolution as AuthenticationService
        # This handles both SQLite and PostgreSQL (adds _auth suffix to database name)
        auth_db_path = get_audit_db_full_path(runtime.essential_config)
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

        # Set resume flag AND timestamp BEFORE scheduling task to prevent SmartStartup from killing us
        # This flag blocks local-shutdown requests during the resume sequence
        # The timestamp enables timeout detection for stuck resume scenarios
        runtime._resume_in_progress = True
        runtime._resume_started_at = time.time()
        logger.info(f"[Setup] Set _resume_in_progress=True, _resume_started_at={runtime._resume_started_at:.3f}")

        async def _resume_runtime() -> None:
            await asyncio.sleep(0.5)  # Brief delay to ensure response is sent
            try:
                await runtime.resume_from_first_run()
                logger.info("✅ Successfully resumed from first-run mode - agent processor running")
            except Exception as e:
                logger.error(f"Failed to resume from first-run: {e}", exc_info=True)
                # Clear the flag and timestamp so shutdown can proceed
                runtime._resume_in_progress = False
                runtime._resume_started_at = None
                logger.info("[Setup] Cleared _resume_in_progress due to error")
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
