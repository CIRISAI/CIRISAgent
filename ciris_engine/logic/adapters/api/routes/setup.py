"""
Setup wizard endpoints for CIRIS first-run and reconfiguration.

Provides GUI-based setup wizard accessible at /v1/setup/*.
Replaces the CLI wizard for pip-installed CIRIS agents.
"""

import asyncio
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ciris_engine.config.model_capabilities import ModelCapabilities, get_model_capabilities
from ciris_engine.logic.config.db_paths import get_audit_db_full_path
from ciris_engine.logic.setup.first_run import get_default_config_path, is_first_run
from ciris_engine.logic.setup.wizard import create_env_file
from ciris_engine.schemas.api.responses import SuccessResponse

from ._common import (
    RESPONSES_400_403_500,
    RESPONSES_401_500,
    RESPONSES_403,
    RESPONSES_404_500,
    RESPONSES_500,
    AuthAdminDep,
)

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
    """Adapter configuration with platform requirements for KMP filtering.

    The server returns all adapters with their requirements.
    KMP clients filter locally based on platform capabilities.
    """

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
    # Fields for KMP-side filtering
    requires_binaries: bool = Field(False, description="Requires external CLI tools (not available on mobile)")
    required_binaries: List[str] = Field(default_factory=list, description="Specific binary names needed")
    supported_platforms: List[str] = Field(
        default_factory=list,
        description="Platforms supported - empty means all, otherwise ['android', 'ios', 'desktop']",
    )
    requires_ciris_services: bool = Field(False, description="Requires CIRIS AI services (Google sign-in)")


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


class LiveModelInfo(BaseModel):
    """A model returned from a provider's live API, annotated with CIRIS compatibility."""

    id: str = Field(..., description="Model ID as returned by the provider")
    display_name: str = Field(..., description="Human-readable name (from capabilities DB or derived)")
    ciris_compatible: Optional[bool] = Field(
        None, description="True if CIRIS-compatible, False if incompatible, None if unknown"
    )
    ciris_recommended: bool = Field(default=False, description="Whether CIRIS recommends this model")
    tier: Optional[str] = Field(None, description="Performance tier (default, fast, fallback, premium, legacy)")
    capabilities: Optional[ModelCapabilities] = Field(
        None, description="Model capabilities if known from capabilities DB"
    )
    context_window: Optional[int] = Field(None, description="Context window size if known")
    notes: Optional[str] = Field(None, description="Additional notes (e.g., rejection reason)")
    source: str = Field(default="live", description="Data source: 'live', 'static', or 'both'")


class ListModelsResponse(BaseModel):
    """Response from the list-models endpoint."""

    provider: str = Field(..., description="Provider ID that was queried")
    models: List[LiveModelInfo] = Field(default_factory=list, description="Models sorted by CIRIS compatibility")
    total_count: int = Field(default=0, description="Total number of models returned")
    source: str = Field(default="live", description="Data source: 'live' (API queried) or 'static' (fallback)")
    error: Optional[str] = Field(
        None, description="If live query failed, the error message (data is from static fallback)"
    )


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
    template_id: str = Field(default="default", description="Agent template ID")

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

    # Node Connection (set by "Connect to Node" device auth flow)
    node_url: Optional[str] = Field(None, description="CIRISNode URL (e.g., https://node.ciris.ai)")
    identity_template: Optional[str] = Field(None, description="Registry-provisioned identity template ID")
    stewardship_tier: Optional[int] = Field(None, ge=1, le=5, description="Stewardship tier from provisioned template")
    approved_adapters: Optional[List[str]] = Field(None, description="Registry-approved adapter list")
    org_id: Optional[str] = Field(None, description="Organization ID from Portal ABAC resolution")
    signing_key_provisioned: bool = Field(
        default=False,
        description="If true, signing key was provisioned by Registry (skip local key generation)",
    )
    provisioned_signing_key_b64: Optional[str] = Field(
        None,
        description="Base64-encoded Ed25519 private key from Registry (consumed and cleared after save)",
    )

    # Licensed module package (set by download-package flow)
    licensed_package_path: Optional[str] = Field(None, description="Path to installed licensed module package")
    licensed_modules_path: Optional[str] = Field(None, description="Path to licensed modules directory within package")

    # CIRISVerify (optional, set by node flow)
    verify_binary_path: Optional[str] = Field(None, description="Path to CIRISVerify binary")
    verify_require_hardware: bool = Field(default=False, description="Require hardware attestation for CIRISVerify")


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
# Constants for live model listing
# ============================================================================

_PROVIDER_BASE_URLS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
}

_LIST_MODELS_TIMEOUT = 10.0  # seconds


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
                "GPT-5.2 Thinking",
                "GPT-4o",
            ],
        ),
        LLMProvider(
            id="anthropic",
            name="Anthropic",
            description="Claude models (Claude Sonnet 4.5, Opus 4.5, Haiku 4.5)",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url=None,
            default_model="claude-sonnet-4-5-20250929",
            examples=[
                "Claude Sonnet 4.5",
                "Claude Opus 4.5",
                "Claude Haiku 4.5",
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


# Constants for adapter filtering
_SKIP_ADAPTERS = {"ciris_covenant_metrics"}  # Handled by consent checkbox
_CIRIS_SERVICES_ADAPTERS = {"ciris_hosted_tools"}  # Require Google sign-in


def _should_skip_manifest(manifest: Any, module_id: str, seen_ids: set[str]) -> bool:
    """Check if a manifest should be skipped during adapter discovery."""
    if module_id in seen_ids:
        return True
    if module_id in _SKIP_ADAPTERS:
        logger.debug(f"[SETUP ADAPTERS] Skipping {module_id} (handled separately)")
        return True
    if manifest.module.is_mock:
        return True
    if manifest.module.reference or manifest.module.for_qa:
        return True
    if not manifest.services:
        return True
    if manifest.metadata and manifest.metadata.get("type") == "library":
        return True
    if module_id.endswith("_common") or "_common_" in module_id:
        return True
    return False


def _create_adapter_from_manifest(manifest: Any, module_id: str) -> AdapterConfig:
    """Create an AdapterConfig from a service manifest."""
    capabilities = manifest.capabilities or []
    requires_binaries = "requires:binaries" in capabilities

    supported_platforms: List[str] = []
    if manifest.metadata:
        platforms = manifest.metadata.get("supported_platforms")
        if platforms and isinstance(platforms, list):
            supported_platforms = platforms

    requires_ciris_services = module_id in _CIRIS_SERVICES_ADAPTERS

    return AdapterConfig(
        id=module_id,
        name=manifest.module.name.replace("_", " ").title(),
        description=manifest.module.description or f"{module_id} adapter",
        enabled_by_default=requires_ciris_services,
        required_env_vars=[],
        optional_env_vars=[],
        platform_requirements=manifest.platform_requirements or [],
        platform_available=True,
        requires_binaries=requires_binaries,
        required_binaries=[],
        supported_platforms=supported_platforms,
        requires_ciris_services=requires_ciris_services,
    )


def _get_available_adapters() -> List[AdapterConfig]:
    """Get all adapters with platform requirements for KMP-side filtering."""
    from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService

    adapters: List[AdapterConfig] = []
    seen_ids: set[str] = set()

    # Always include API adapter first (required, cannot be disabled)
    adapters.append(
        AdapterConfig(
            id="api",
            name="Web API",
            description="RESTful API server with built-in web interface",
            enabled_by_default=True,
            required_env_vars=[],
            optional_env_vars=["CIRIS_API_PORT", "NEXT_PUBLIC_API_BASE_URL"],
            platform_available=True,
            requires_binaries=False,
            required_binaries=[],
            supported_platforms=[],
            requires_ciris_services=False,
        )
    )
    seen_ids.add("api")

    try:
        discovery = AdapterDiscoveryService()
        for manifest in discovery.discover_adapters():
            module_id = manifest.module.name
            if _should_skip_manifest(manifest, module_id, seen_ids):
                continue

            adapter_config = _create_adapter_from_manifest(manifest, module_id)
            adapters.append(adapter_config)
            seen_ids.add(module_id)
            logger.debug(
                f"[SETUP ADAPTERS] Discovered adapter: {module_id} "
                f"(requires_binaries={adapter_config.requires_binaries}, "
                f"supported_platforms={adapter_config.supported_platforms})"
            )
    except Exception as e:
        logger.warning(f"[SETUP ADAPTERS] Failed to discover adapters: {e}")

    logger.info(f"[SETUP ADAPTERS] Total adapters available: {len(adapters)}")
    return adapters


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
        base_url: The base URL being connected to (None for providers with fixed endpoints)

    Returns:
        Formatted error response
    """
    error_str = str(error)

    if "401" in error_str or "Unauthorized" in error_str or "authentication_error" in error_str.lower():
        return LLMValidationResponse(
            valid=False,
            message="Authentication failed",
            error="Invalid API key. Please check your credentials.",
        )
    if "invalid_api_key" in error_str.lower() or "invalid x-api-key" in error_str.lower():
        return LLMValidationResponse(
            valid=False,
            message="Authentication failed",
            error="Invalid API key. Please check your credentials.",
        )
    if "404" in error_str or "Not Found" in error_str:
        # Check if it's a model not found error (common with Anthropic)
        if "model:" in error_str.lower() or "not_found_error" in error_str.lower():
            return LLMValidationResponse(
                valid=False,
                message="Model not found",
                error="Model not found. Please check the model name (e.g., claude-3-5-sonnet-20241022).",
            )
        if base_url:
            return LLMValidationResponse(
                valid=False,
                message="Endpoint not found",
                error=f"Could not reach {base_url}. Please check the URL.",
            )
        return LLMValidationResponse(
            valid=False,
            message="Endpoint not found",
            error="Could not reach the API endpoint. Please check your configuration.",
        )
    if "timeout" in error_str.lower():
        return LLMValidationResponse(
            valid=False,
            message="Connection timeout",
            error="Could not connect to LLM server. Please check if it's running.",
        )
    if "connection" in error_str.lower() and "refused" in error_str.lower():
        return LLMValidationResponse(
            valid=False,
            message="Connection refused",
            error="Could not connect to the LLM server. Please check if it's running.",
        )
    return LLMValidationResponse(valid=False, message="Connection failed", error=f"Error: {error_str}")


async def _validate_openai_compatible(config: LLMValidationRequest) -> LLMValidationResponse:
    """Validate OpenAI-compatible API connection."""
    from openai import AsyncOpenAI

    # Build client configuration
    client_kwargs: Dict[str, Any] = {"api_key": config.api_key or "local"}

    # Resolve base URL using provider defaults
    resolved_base_url = _get_provider_base_url(config.provider, config.base_url)
    if resolved_base_url:
        client_kwargs["base_url"] = resolved_base_url

    logger.info(f"[VALIDATE_LLM] Creating OpenAI client with base_url: {client_kwargs.get('base_url', 'default')}")

    client = AsyncOpenAI(**client_kwargs)
    model_to_test = config.model or "gpt-3.5-turbo"

    # Try max_tokens first, fall back to max_completion_tokens for reasoning models
    try:
        await client.chat.completions.create(
            model=model_to_test,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=1,
        )
    except Exception as token_err:
        error_str = str(token_err).lower()
        if "max_tokens" in error_str and "max_completion_tokens" in error_str:
            logger.info("[VALIDATE_LLM] Model requires max_completion_tokens, retrying...")
            await client.chat.completions.create(
                model=model_to_test,
                messages=[{"role": "user", "content": "Hi"}],
                max_completion_tokens=1,
            )
        else:
            raise

    logger.info(f"[VALIDATE_LLM] SUCCESS! Test completion worked with model: {model_to_test}")
    return LLMValidationResponse(
        valid=True,
        message=f"Connection successful! Model '{model_to_test}' is available.",
        error=None,
    )


def _log_validation_start(config: LLMValidationRequest) -> None:
    """Log validation start details."""
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


async def _validate_llm_connection(config: LLMValidationRequest) -> LLMValidationResponse:
    """Validate LLM configuration by attempting a connection."""
    _log_validation_start(config)

    try:
        # Validate API key for provider type
        api_key_error = _validate_api_key_for_provider(config)
        if api_key_error:
            logger.warning(f"[VALIDATE_LLM] API key validation FAILED: {api_key_error.error}")
            return api_key_error

        logger.info("[VALIDATE_LLM] API key format validation passed")

        # Route to provider-specific validators
        if config.provider == "anthropic":
            return await _validate_anthropic_connection(config)
        if config.provider == "google":
            return await _validate_google_connection(config)

        # OpenAI-compatible providers
        return await _validate_openai_compatible(config)

    except Exception as e:
        logger.error(f"[VALIDATE_LLM] API call FAILED: {type(e).__name__}: {e}")
        result = _classify_llm_connection_error(e, config.base_url)
        logger.error(f"[VALIDATE_LLM] Classified error - valid: {result.valid}, error: {result.error}")
        return result


async def _validate_anthropic_connection(config: LLMValidationRequest) -> LLMValidationResponse:
    """Validate Anthropic API connection using native SDK."""
    try:
        import anthropic

        logger.info("[VALIDATE_LLM] Using Anthropic SDK for validation")
        client = anthropic.AsyncAnthropic(api_key=config.api_key)

        # Try a minimal completion
        model_to_test = config.model or "claude-haiku-4-5-20251001"
        await client.messages.create(
            model=model_to_test,
            max_tokens=1,
            messages=[{"role": "user", "content": "Hi"}],
        )  # Validation only - response not needed
        logger.info(f"[VALIDATE_LLM] SUCCESS! Anthropic test completion worked with model: {model_to_test}")
        return LLMValidationResponse(
            valid=True,
            message=f"Connection successful! Model '{model_to_test}' is available.",
            error=None,
        )
    except ImportError:
        logger.error("[VALIDATE_LLM] Anthropic SDK not installed")
        return LLMValidationResponse(
            valid=False,
            message="SDK not installed",
            error="Anthropic SDK not installed. Run: pip install anthropic",
        )
    except Exception as e:
        logger.error(f"[VALIDATE_LLM] Anthropic API call FAILED: {type(e).__name__}: {e}")
        return _classify_llm_connection_error(e, "api.anthropic.com")


async def _validate_google_connection(config: LLMValidationRequest) -> LLMValidationResponse:
    """Validate Google AI (Gemini) connection using OpenAI-compatible endpoint."""
    try:
        from openai import AsyncOpenAI

        # Google's OpenAI-compatible endpoint
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        logger.info(f"[VALIDATE_LLM] Using Google OpenAI-compatible endpoint: {base_url}")

        client = AsyncOpenAI(api_key=config.api_key, base_url=base_url)

        # Try a minimal completion
        model_to_test = config.model or "gemini-2.0-flash"
        await client.chat.completions.create(
            model=model_to_test,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=1,
        )  # Validation only - response not needed
        logger.info(f"[VALIDATE_LLM] SUCCESS! Google test completion worked with model: {model_to_test}")
        return LLMValidationResponse(
            valid=True,
            message=f"Connection successful! Model '{model_to_test}' is available.",
            error=None,
        )
    except Exception as e:
        logger.error(f"[VALIDATE_LLM] Google API call FAILED: {type(e).__name__}: {e}")
        return _classify_llm_connection_error(e, "https://generativelanguage.googleapis.com")


# =============================================================================
# LIVE MODEL LISTING HELPER FUNCTIONS
# =============================================================================


def _detect_ollama(base_url: Optional[str]) -> bool:
    """Check if a base URL points to an Ollama instance."""
    if not base_url:
        return False
    return ":11434" in base_url


def _get_provider_base_url(provider: str, base_url: Optional[str]) -> Optional[str]:
    """Resolve the base URL for a provider, using known defaults if not provided."""
    if base_url:
        return base_url
    return _PROVIDER_BASE_URLS.get(provider)


async def _list_models_openai_compatible(api_key: str, base_url: Optional[str]) -> List[LiveModelInfo]:
    """Query models from an OpenAI-compatible API endpoint."""
    from openai import AsyncOpenAI

    client_kwargs: Dict[str, Any] = {"api_key": api_key or "local", "timeout": _LIST_MODELS_TIMEOUT}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = AsyncOpenAI(**client_kwargs)
    models_page = await asyncio.wait_for(client.models.list(), timeout=_LIST_MODELS_TIMEOUT)

    result: List[LiveModelInfo] = []
    for model in models_page.data:
        result.append(LiveModelInfo(id=model.id, display_name=model.id, source="live"))
    return result


async def _list_models_anthropic(api_key: str) -> List[LiveModelInfo]:
    """Query models from the Anthropic API using the native SDK."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)
    result: List[LiveModelInfo] = []

    page = await asyncio.wait_for(client.models.list(limit=100), timeout=_LIST_MODELS_TIMEOUT)
    for model in page.data:
        display = getattr(model, "display_name", model.id)
        result.append(LiveModelInfo(id=model.id, display_name=display, source="live"))

    while page.has_next_page():
        page = await asyncio.wait_for(page.get_next_page(), timeout=_LIST_MODELS_TIMEOUT)
        for model in page.data:
            display = getattr(model, "display_name", model.id)
            result.append(LiveModelInfo(id=model.id, display_name=display, source="live"))

    return result


async def _list_models_google(api_key: str) -> List[LiveModelInfo]:
    """Query models from Google AI using the google-genai SDK."""
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        raw_models = await asyncio.wait_for(_google_models_to_list(client), timeout=_LIST_MODELS_TIMEOUT)

        result: List[LiveModelInfo] = []
        for model in raw_models:
            model_name = model.name or ""
            # Strip "models/" prefix that Google returns
            model_id = model_name.replace("models/", "") if model_name.startswith("models/") else model_name
            display = getattr(model, "display_name", None) or model_id
            result.append(LiveModelInfo(id=model_id, display_name=display, source="live"))
        return result
    except ImportError:
        # Fall back to OpenAI-compatible endpoint
        return await _list_models_openai_compatible(api_key, "https://generativelanguage.googleapis.com/v1beta/openai/")


async def _google_models_to_list(client: Any) -> List[Any]:
    """Collect Google models into a list (helper to work with asyncio.wait_for)."""
    result = []
    async for model in client.aio.models.list(config={"query_base": True}):
        result.append(model)
    return result


async def _list_models_ollama(base_url: str) -> List[LiveModelInfo]:
    """Query models from an Ollama instance via /api/tags."""
    from urllib.parse import urlparse

    import httpx

    # Validate and sanitize the URL to prevent injection
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Ollama URL must use http or https scheme")

    # Reconstruct a safe URL from parsed components
    safe_base = f"{parsed.scheme}://{parsed.netloc}"

    async with httpx.AsyncClient(timeout=_LIST_MODELS_TIMEOUT) as client:
        response = await client.get(f"{safe_base}/api/tags")
        response.raise_for_status()
        data = response.json()

    result: List[LiveModelInfo] = []
    for model in data.get("models", []):
        model_name = model.get("name", "")
        result.append(LiveModelInfo(id=model_name, display_name=model_name, source="live"))
    return result


def _annotate_models_with_capabilities(models: List[LiveModelInfo], provider_id: str) -> List[LiveModelInfo]:
    """Cross-reference live models with MODEL_CAPABILITIES.json for CIRIS compatibility.

    Returns a new list of annotated models. Models found in the capabilities DB
    are enriched with compatibility info; unknown models are passed through unchanged.
    """
    try:
        config = get_model_capabilities()
    except Exception:
        return list(models)

    provider_models = config.get_provider_models(provider_id)
    if provider_models is None:
        return list(models)

    annotated: List[LiveModelInfo] = []
    for model in models:
        known_info = provider_models.get(model.id)
        if known_info is not None:
            annotated.append(
                LiveModelInfo(
                    id=model.id,
                    display_name=known_info.display_name,
                    ciris_compatible=known_info.ciris_compatible,
                    ciris_recommended=known_info.ciris_recommended,
                    tier=known_info.tier,
                    capabilities=known_info.capabilities,
                    context_window=known_info.context_window,
                    notes=known_info.notes or known_info.rejection_reason,
                    source="both",
                )
            )
        else:
            annotated.append(model)

    return annotated


def _sort_models(models: List[LiveModelInfo]) -> List[LiveModelInfo]:
    """Sort models: recommended first, then compatible, unknown, incompatible."""

    def sort_key(m: LiveModelInfo) -> tuple[int, str]:
        if m.ciris_recommended:
            priority = 0
        elif m.ciris_compatible is True:
            priority = 1
        elif m.ciris_compatible is None:
            priority = 2
        else:
            priority = 3
        return (priority, m.display_name.lower())

    return sorted(models, key=sort_key)


def _get_static_fallback_models(provider_id: str) -> List[LiveModelInfo]:
    """Load models from MODEL_CAPABILITIES.json as a static fallback."""
    try:
        config = get_model_capabilities()
    except Exception:
        return []

    provider_models = config.get_provider_models(provider_id)
    if provider_models is None:
        return []

    result: List[LiveModelInfo] = []
    for model_id, info in provider_models.items():
        result.append(
            LiveModelInfo(
                id=model_id,
                display_name=info.display_name,
                ciris_compatible=info.ciris_compatible,
                ciris_recommended=info.ciris_recommended,
                tier=info.tier,
                capabilities=info.capabilities,
                context_window=info.context_window,
                notes=info.notes or info.rejection_reason,
                source="static",
            )
        )
    return result


def _build_fallback_response(provider_id: str, error_msg: str) -> ListModelsResponse:
    """Build a response from static capabilities data when live query fails."""
    fallback_models = _get_static_fallback_models(provider_id)
    sorted_models = _sort_models(fallback_models)
    return ListModelsResponse(
        provider=provider_id,
        models=sorted_models,
        total_count=len(sorted_models),
        source="static",
        error=f"Live query failed: {error_msg}. Showing cached model data.",
    )


async def _fetch_live_models(config: LLMValidationRequest) -> List[LiveModelInfo]:
    """Dispatch to provider-specific model listing function."""
    if config.provider == "anthropic":
        return await _list_models_anthropic(config.api_key)
    if config.provider == "google":
        return await _list_models_google(config.api_key)
    if config.provider == "local" and _detect_ollama(config.base_url):
        return await _list_models_ollama(config.base_url or "http://localhost:11434")

    resolved_url = _get_provider_base_url(config.provider, config.base_url)
    return await _list_models_openai_compatible(config.api_key, resolved_url)


async def _list_models_for_provider(config: LLMValidationRequest) -> ListModelsResponse:
    """Query provider for models and annotate with CIRIS compatibility."""
    # Validate API key first (reuse existing helper)
    api_key_error = _validate_api_key_for_provider(config)
    if api_key_error and config.provider != "local":
        return _build_fallback_response(config.provider, api_key_error.error or "Invalid API key")

    try:
        live_models = await _fetch_live_models(config)
    except Exception as e:
        logger.warning("[LIST_MODELS] Live query failed, falling back to static data")
        return _build_fallback_response(config.provider, str(e))

    annotated = _annotate_models_with_capabilities(live_models, config.provider)
    sorted_models = _sort_models(annotated)

    return ListModelsResponse(
        provider=config.provider,
        models=sorted_models,
        total_count=len(sorted_models),
        source="live",
    )


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

    # Save configuration (path determined internally by get_default_config_path)
    logger.info("[Setup Complete] Saving configuration...")
    config_path = _save_setup_config(setup)
    logger.info(f"[Setup Complete] Configuration saved to: {config_path}")

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


def _write_section_header(f: Any, title: str) -> None:
    """Write a section header with separators to the config file."""
    f.write("\n# ============================================================================\n")
    f.write(f"# {title}\n")
    f.write("# ============================================================================\n")


def _write_backup_llm_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write backup/secondary LLM configuration if provided."""
    if not setup.backup_llm_api_key:
        return
    f.write("\n# Backup/Secondary LLM Configuration\n")
    f.write(f'CIRIS_OPENAI_API_KEY_2="{setup.backup_llm_api_key}"\n')
    if setup.backup_llm_base_url:
        f.write(f'CIRIS_OPENAI_API_BASE_2="{setup.backup_llm_base_url}"\n')
    if setup.backup_llm_model:
        f.write(f'CIRIS_OPENAI_MODEL_NAME_2="{setup.backup_llm_model}"\n')


def _write_node_connection_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write CIRISNode connection configuration if provided."""
    if not setup.node_url:
        return
    _write_section_header(f, "CIRISNode Connection (provisioned via device auth)")
    f.write(f'CIRISNODE_BASE_URL="{setup.node_url}"\n')
    if setup.identity_template:
        f.write(f'CIRIS_IDENTITY_TEMPLATE="{setup.identity_template}"\n')
    if setup.stewardship_tier is not None:
        f.write(f"CIRIS_STEWARDSHIP_TIER={setup.stewardship_tier}\n")
    if setup.approved_adapters:
        f.write(f'CIRIS_APPROVED_ADAPTERS="{",".join(setup.approved_adapters)}"\n')
    if setup.org_id:
        f.write(f'CIRIS_ORG_ID="{setup.org_id}"\n')


def _write_licensed_package_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write licensed module package configuration if provided."""
    if not setup.licensed_package_path:
        return
    _write_section_header(f, "Licensed Module Package")
    f.write(f'CIRIS_LICENSED_PACKAGE_PATH="{setup.licensed_package_path}"\n')
    if setup.licensed_modules_path:
        f.write(f'CIRIS_MODULE_PATH="{setup.licensed_modules_path}"\n')


def _write_verify_config(f: Any, setup: SetupCompleteRequest) -> None:
    """Write CIRISVerify configuration if provided."""
    if not setup.verify_binary_path:
        return
    _write_section_header(f, "CIRISVerify")
    f.write(f'CIRIS_VERIFY_BINARY_PATH="{setup.verify_binary_path}"\n')
    require_hw = "true" if setup.verify_require_hardware else "false"
    f.write(f"CIRIS_VERIFY_REQUIRE_HARDWARE={require_hw}\n")


def _save_setup_config(setup: SetupCompleteRequest) -> Path:
    """Save setup configuration to .env file.

    Args:
        setup: Setup configuration

    Returns:
        Path where config was saved
    """
    llm_base_url = _get_provider_base_url(setup.llm_provider, setup.llm_base_url) or ""
    config_path = create_env_file(
        llm_provider=setup.llm_provider,
        llm_api_key=setup.llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=setup.llm_model or "",
        agent_port=setup.agent_port,
    )

    with open(config_path, "a") as f:
        # Template and adapter configuration
        f.write("\n# Agent Template\n")
        f.write(f"CIRIS_TEMPLATE={setup.template_id}\n")
        f.write("\n# Enabled Adapters\n")
        f.write(f"CIRIS_ADAPTER={','.join(setup.enabled_adapters)}\n")

        # Covenant metrics consent
        if "ciris_covenant_metrics" in setup.enabled_adapters:
            from datetime import datetime, timezone
            consent_timestamp = datetime.now(timezone.utc).isoformat()
            f.write("\n# Covenant Metrics Consent (auto-set when adapter enabled)\n")
            f.write("CIRIS_COVENANT_METRICS_CONSENT=true\n")
            f.write(f"CIRIS_COVENANT_METRICS_CONSENT_TIMESTAMP={consent_timestamp}\n")
            logger.info(f"[SETUP] Covenant metrics consent enabled: {consent_timestamp}")

        # Adapter-specific environment variables
        if setup.adapter_config:
            f.write("\n# Adapter-Specific Configuration\n")
            for key, value in setup.adapter_config.items():
                f.write(f"{key}={value}\n")

        # Write optional configuration sections
        _write_backup_llm_config(f, setup)
        _write_node_connection_config(f, setup)
        _write_licensed_package_config(f, setup)
        _write_verify_config(f, setup)

    return config_path


def _log_setup_debug_info(setup: SetupCompleteRequest) -> bool:
    """Log comprehensive debug information for OAuth identity linking.

    Args:
        setup: Setup configuration request

    Returns:
        Whether OAuth linking will happen
    """
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

    return will_link_oauth


async def _schedule_runtime_resume(runtime: Any) -> None:
    """Schedule runtime resume in background after setup completion.

    Args:
        runtime: The application runtime object
    """
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
            logger.info("Successfully resumed from first-run mode - agent processor running")
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


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/status")
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


@router.get("/providers")
async def list_providers() -> SuccessResponse[List[LLMProvider]]:
    """List available LLM providers.

    Returns configuration templates for supported LLM providers.
    This endpoint is always accessible without authentication.
    """
    providers = _get_llm_providers()
    return SuccessResponse(data=providers)


@router.get("/templates")
async def list_templates() -> SuccessResponse[List[AgentTemplate]]:
    """List available agent templates.

    Returns pre-configured agent identity templates.
    This endpoint is always accessible without authentication.
    """
    templates = _get_agent_templates()
    return SuccessResponse(data=templates)


@router.get("/adapters")
async def list_adapters() -> SuccessResponse[List[AdapterConfig]]:
    """List available adapters with platform requirements.

    Returns ALL adapters with their requirements metadata.
    KMP clients filter locally based on platform capabilities (iOS, Android, desktop).
    This endpoint is always accessible without authentication.
    """
    adapters = _get_available_adapters()
    return SuccessResponse(data=adapters)


@router.get(
    "/adapters/available",
    responses={500: {"description": "Adapter discovery failed"}},
)
async def list_available_adapters_for_setup() -> SuccessResponse[Dict[str, Any]]:
    """List discovered adapters with eligibility status (no auth required for setup).

    Returns both eligible (ready to use) and ineligible (missing requirements)
    adapters, including installation hints for ineligible adapters.
    This endpoint is accessible without authentication during first-run setup.
    """
    from ciris_engine.logic.services.tool.discovery_service import AdapterDiscoveryService

    try:
        discovery = AdapterDiscoveryService()
        report = await discovery.get_discovery_report()
        return SuccessResponse(data=report.model_dump())
    except Exception as e:
        logger.error(f"Error getting adapter availability for setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models", responses=RESPONSES_500)
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


@router.get("/models/{provider_id}", responses=RESPONSES_404_500)
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


@router.post("/validate-llm")
async def validate_llm(config: LLMValidationRequest) -> SuccessResponse[LLMValidationResponse]:
    """Validate LLM configuration.

    Tests the provided LLM configuration by attempting a connection.
    This endpoint is always accessible without authentication during first-run.
    """
    validation_result = await _validate_llm_connection(config)
    return SuccessResponse(data=validation_result)


@router.post("/list-models")
async def list_models(config: LLMValidationRequest) -> SuccessResponse[ListModelsResponse]:
    """List available models from a provider's live API.

    Queries the provider's models API using the provided credentials,
    then cross-references with the on-device MODEL_CAPABILITIES.json
    for CIRIS compatibility annotations.

    Falls back to static capabilities data if the live query fails.
    This endpoint is always accessible without authentication during first-run.
    """
    result = await _list_models_for_provider(config)
    return SuccessResponse(data=result)


# ============================================================================
# Connect to Node (Device Auth Flow)
# ============================================================================


class ConnectNodeRequest(BaseModel):
    """Request to initiate device auth via CIRISPortal."""

    node_url: str = Field(..., description="Portal URL (e.g., https://portal.ciris.ai)")


class ConnectNodeResponse(BaseModel):
    """Response from device auth initiation."""

    verification_uri_complete: str = Field(..., description="URL for user to open in browser")
    device_code: str = Field(..., description="Device code for polling")
    user_code: str = Field(..., description="Human-readable code")
    portal_url: str = Field(..., description="Normalized Portal URL (with https://)")
    expires_in: int = Field(..., description="Seconds until device code expires")
    interval: int = Field(..., description="Polling interval in seconds")


class ConnectNodeStatusResponse(BaseModel):
    """Response from device auth status polling."""

    status: str = Field(..., description="pending, complete, or error")
    # Fields below are only set when status == 'complete'
    template: Optional[str] = Field(None, description="Provisioned identity template ID")
    adapters: Optional[List[str]] = Field(None, description="Approved adapter list")
    org_id: Optional[str] = Field(None, description="Organization ID")
    signing_key_b64: Optional[str] = Field(None, description="Base64-encoded Ed25519 private key (one-time)")
    key_id: Optional[str] = Field(None, description="Key ID from Registry")
    stewardship_tier: Optional[int] = Field(None, description="Stewardship tier from template")
    # Licensed package info — agent downloads this after provisioning
    package_download_url: Optional[str] = Field(None, description="URL to download licensed module package zip")
    package_template_id: Optional[str] = Field(None, description="Template ID within the licensed package")


@router.post("/connect-node", responses=RESPONSES_500)
async def connect_node(req: ConnectNodeRequest) -> SuccessResponse[ConnectNodeResponse]:
    """Initiate device auth via CIRISPortal.

    The user provides a Portal URL directly. This endpoint:
    1. Normalizes the Portal URL (adds https:// if needed)
    2. Calls Portal's POST /api/device/authorize with agent info
    3. Returns verification URL for user to open in browser

    The flow contacts CIRISPortal (for device auth/OAuth) and CIRISRegistry
    (for agent registration + key issuance). CIRISNode is NOT involved
    in the provisioning flow.

    This endpoint is accessible without authentication during first-run.
    """
    import httpx

    portal_url = req.node_url.strip().rstrip("/")
    # Normalize URL — add https:// if no scheme provided
    if not portal_url.startswith("http://") and not portal_url.startswith("https://"):
        portal_url = f"https://{portal_url}"

    device_auth_endpoint = "/api/device/authorize"

    # TODO: Include real agent info (hash, public key) from current agent state.
    # MVP: send empty agent_info since we're provisioning a new agent.
    agent_info: Dict[str, Any] = {}

    # Call Portal's device authorize endpoint directly
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            auth_resp = await client.post(
                f"{portal_url}{device_auth_endpoint}",
                json={
                    "portal_url": portal_url,
                    "agent_info": agent_info,
                },
            )
            auth_resp.raise_for_status()
            auth_data = auth_resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to initiate device auth with Portal at {portal_url}: {e}",
        )

    return SuccessResponse(
        data=ConnectNodeResponse(
            verification_uri_complete=auth_data["verification_uri_complete"],
            device_code=auth_data["device_code"],
            user_code=auth_data.get("user_code", ""),
            portal_url=portal_url,
            expires_in=auth_data.get("expires_in", 900),
            interval=auth_data.get("interval", 5),
        )
    )


@router.get("/connect-node/status", responses=RESPONSES_500)
async def connect_node_status(device_code: str, portal_url: str) -> SuccessResponse[ConnectNodeStatusResponse]:
    """Poll device auth status.

    Called periodically by the setup wizard to check if the user has
    completed the device auth flow in the Portal browser UI.

    Args:
        device_code: Opaque device code from /connect-node
        portal_url: Portal URL to poll (from node manifest)

    Returns:
        Status: pending (keep polling), complete (key ready), or error.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(
                f"{portal_url.rstrip('/')}/api/device/token",
                json={"device_code": device_code},
            )

            # 428 = authorization_pending (RFC 8628)
            if token_resp.status_code == 428:
                return SuccessResponse(data=ConnectNodeStatusResponse(status="pending"))

            if token_resp.status_code == 403:
                return SuccessResponse(data=ConnectNodeStatusResponse(status="error"))

            if token_resp.status_code != 200:
                body = token_resp.json() if token_resp.headers.get("content-type", "").startswith("application/json") else {}
                error_desc = body.get("error_description", body.get("error", f"HTTP {token_resp.status_code}"))
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Portal token endpoint error: {error_desc}",
                )

            data = token_resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to poll Portal token endpoint: {e}",
        )

    # Success — extract provisioned data
    signing_key = data.get("signing_key", {})
    agent_record = data.get("agent_record", {})
    licensed_package = data.get("licensed_package") or {}

    # Save the provisioned signing key immediately
    # TODO: Consider deferring key save to /complete for atomicity.
    # MVP: save key on first successful poll so it's available immediately.
    private_key_b64 = signing_key.get("ed25519_private_key", "")
    if private_key_b64:
        try:
            from ciris_engine.logic.audit.signing_protocol import UnifiedSigningKey
            from ciris_engine.logic.utils.path_resolution import get_data_dir

            save_path = get_data_dir() / "agent_signing.key"
            save_path.parent.mkdir(parents=True, exist_ok=True)
            provisioned_key = UnifiedSigningKey()
            provisioned_key.load_provisioned_key(private_key_b64, save_path=save_path)
            logger.info(f"[Connect Node] Saved Registry-provisioned signing key to {save_path}")
        except Exception as e:
            logger.error(f"[Connect Node] Failed to save provisioned key: {e}")

    return SuccessResponse(
        data=ConnectNodeStatusResponse(
            status="complete",
            template=agent_record.get("identity_template"),
            adapters=agent_record.get("approved_adapters"),
            org_id=signing_key.get("org_id"),
            signing_key_b64=private_key_b64,
            key_id=signing_key.get("key_id"),
            stewardship_tier=agent_record.get("stewardship_tier"),
            package_download_url=licensed_package.get("download_url"),
            package_template_id=licensed_package.get("template_id"),
        )
    )


# ============================================================================
# Licensed Package Download + Configure
# ============================================================================


class DownloadPackageRequest(BaseModel):
    """Request to download and install a licensed module package."""

    package_download_url: str = Field(..., description="Portal URL to download the package zip")
    portal_session_cookie: Optional[str] = Field(None, description="Portal session cookie for auth (from device auth)")


class DownloadPackageResponse(BaseModel):
    """Response from package download + install."""

    status: str = Field(..., description="success or error")
    package_path: str = Field(default="", description="Path where package was installed")
    template_file: Optional[str] = Field(None, description="Path to the identity template YAML")
    modules_path: Optional[str] = Field(None, description="Path to the modules directory")
    config_path: Optional[str] = Field(None, description="Path to the config directory")
    checksum: Optional[str] = Field(None, description="SHA-256 checksum of downloaded zip")
    error: Optional[str] = Field(None, description="Error message if status is error")


@router.post("/download-package", responses=RESPONSES_500)
async def download_package(req: DownloadPackageRequest) -> SuccessResponse[DownloadPackageResponse]:
    """Download and install a licensed module package from Portal.

    1. Downloads the zip from the Portal package endpoint
    2. Verifies checksum from response headers
    3. Unzips to the agent's licensed_modules/ directory
    4. Returns paths for template, modules, and config

    This endpoint is accessible without authentication during first-run.
    """
    import hashlib
    import shutil
    import tempfile
    import zipfile

    import httpx

    # Determine install directory
    data_dir = Path(os.environ.get("CIRIS_DATA_DIR", "."))
    licensed_modules_dir = data_dir / "licensed_modules"

    try:
        # Download the zip from Portal
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            headers: Dict[str, str] = {}
            if req.portal_session_cookie:
                headers["Cookie"] = req.portal_session_cookie

            dl_resp = await client.get(req.package_download_url, headers=headers)
            dl_resp.raise_for_status()

        # Get checksum from response header
        expected_checksum = dl_resp.headers.get("x-package-checksum", "")
        package_id = dl_resp.headers.get("x-package-id", "unknown")
        package_version = dl_resp.headers.get("x-package-version", "0.0.0")

        # Verify checksum
        actual_checksum = hashlib.sha256(dl_resp.content).hexdigest()
        if expected_checksum and actual_checksum != expected_checksum:
            return SuccessResponse(
                data=DownloadPackageResponse(
                    status="error",
                    error=f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}",
                )
            )

        # Save zip to temp file
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(dl_resp.content)
            tmp_path = tmp.name

        # Create install directory
        install_dir = licensed_modules_dir / package_id
        if install_dir.exists():
            # Remove old version
            shutil.rmtree(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)

        # Unzip
        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(install_dir)

        # Cleanup temp file
        os.unlink(tmp_path)

        logger.info(
            f"[Package Download] Installed {package_id} v{package_version} to {install_dir}"
        )

        # Find key paths within the extracted package
        template_file = None
        modules_path = None
        config_path = None

        templates_dir = install_dir / "templates"
        if templates_dir.exists():
            yamls = list(templates_dir.glob("*.yaml"))
            if yamls:
                template_file = str(yamls[0])

        mods_dir = install_dir / "modules"
        if mods_dir.exists():
            modules_path = str(mods_dir)

        cfg_dir = install_dir / "config"
        if cfg_dir.exists():
            config_path = str(cfg_dir)

        return SuccessResponse(
            data=DownloadPackageResponse(
                status="success",
                package_path=str(install_dir),
                template_file=template_file,
                modules_path=modules_path,
                config_path=config_path,
                checksum=actual_checksum,
            )
        )

    except httpx.HTTPError as e:
        logger.error(f"[Package Download] HTTP error: {e}")
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error=f"Failed to download package: {e}",
            )
        )
    except zipfile.BadZipFile:
        logger.error("[Package Download] Invalid zip file received")
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error="Downloaded file is not a valid zip archive",
            )
        )
    except Exception as e:
        logger.error(f"[Package Download] Unexpected error: {e}")
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error=f"Package installation failed: {e}",
            )
        )


@router.post("/complete", responses=RESPONSES_400_403_500)
async def complete_setup(setup: SetupCompleteRequest, request: Request) -> SuccessResponse[Dict[str, str]]:
    """Complete initial setup.

    Saves configuration and creates initial admin user.
    Only accessible during first-run (no authentication required).
    After setup, authentication is required for reconfiguration.
    """
    # Log debug info and determine if OAuth linking will happen
    _log_setup_debug_info(setup)

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

        # If a Registry-provisioned signing key was provided (Connect to Node flow),
        # save it now so the agent uses the Registry-issued key instead of self-generating.
        if setup.signing_key_provisioned and setup.provisioned_signing_key_b64:
            from ciris_engine.logic.audit.signing_protocol import UnifiedSigningKey

            provisioned_key = UnifiedSigningKey()
            provisioned_key.load_provisioned_key(setup.provisioned_signing_key_b64)
            logger.info("[Setup Complete] Saved Registry-provisioned signing key")
            # Clear the key from the request to avoid logging it
            setup.provisioned_signing_key_b64 = None

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
        await _schedule_runtime_resume(runtime)

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
            from ..dependencies.auth import get_auth_context, get_auth_service

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

    # Read current config from environment
    config = SetupConfigResponse(
        llm_provider="openai" if os.getenv("OPENAI_API_BASE") is None else "other",
        llm_base_url=os.getenv("OPENAI_API_BASE"),
        llm_model=os.getenv("OPENAI_MODEL"),
        llm_api_key_set=bool(os.getenv("OPENAI_API_KEY")),
        backup_llm_base_url=os.getenv("CIRIS_OPENAI_API_BASE_2"),
        backup_llm_model=os.getenv("CIRIS_OPENAI_MODEL_NAME_2"),
        backup_llm_api_key_set=bool(os.getenv("CIRIS_OPENAI_API_KEY_2")),
        template_id=template_id,
        enabled_adapters=os.getenv("CIRIS_ADAPTER", "api").split(","),
        agent_port=int(os.getenv("CIRIS_API_PORT", "8080")),
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
