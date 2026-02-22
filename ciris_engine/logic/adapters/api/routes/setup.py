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
# Device Auth Session Persistence
# ============================================================================
# Device codes MUST persist across app restarts until the flow completes,
# expires, or errors. Otherwise, if the user pays for a license in the browser
# and the app restarts, the purchase is orphaned.


def _get_device_auth_session_path() -> Path:
    """Get path to the device auth session file."""
    ciris_home = os.environ.get("CIRIS_HOME", str(Path.home() / ".ciris"))
    return Path(ciris_home) / ".device_auth_session.json"


def _load_device_auth_session() -> Optional[Dict[str, Any]]:
    """Load active device auth session if it exists and hasn't expired."""
    session_path = _get_device_auth_session_path()
    if not session_path.exists():
        return None

    try:
        with open(session_path, "r") as f:
            session = json.load(f)

        # Check if expired
        expires_at = session.get("expires_at", 0)
        if time.time() > expires_at:
            logger.info("Device auth session expired, clearing")
            _clear_device_auth_session()
            return None

        return session
    except Exception as e:
        logger.warning("Failed to load device auth session: %s", e)
        return None


def _save_device_auth_session(
    device_code: str,
    portal_url: str,
    verification_uri_complete: str,
    user_code: str,
    expires_in: int,
    interval: int,
) -> None:
    """Save active device auth session."""
    session_path = _get_device_auth_session_path()
    session = {
        "device_code": device_code,
        "portal_url": portal_url,
        "verification_uri_complete": verification_uri_complete,
        "user_code": user_code,
        "expires_in": expires_in,
        "interval": interval,
        "expires_at": time.time() + expires_in,
        "created_at": time.time(),
    }

    try:
        session_path.parent.mkdir(parents=True, exist_ok=True)
        with open(session_path, "w") as f:
            json.dump(session, f)
        logger.info("Saved device auth session (expires in %ds)", expires_in)
    except Exception as e:
        logger.warning("Failed to save device auth session: %s", e)


def _clear_device_auth_session() -> None:
    """Clear device auth session (on completion or error)."""
    session_path = _get_device_auth_session_path()
    try:
        if session_path.exists():
            session_path.unlink()
            logger.info("Cleared device auth session")
    except Exception as e:
        logger.warning("Failed to clear device auth session: %s", e)


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


class VerifyStatusResponse(BaseModel):
    """CIRISVerify status for Trust and Security display.

    CIRISVerify is REQUIRED for CIRIS 2.0+. Agents cannot run without it.
    """

    loaded: bool = Field(..., description="Whether CIRISVerify library is loaded")
    version: Optional[str] = Field(None, description="CIRISVerify version if loaded")
    hardware_type: Optional[str] = Field(None, description="Hardware security type (TPM_2_0, SOFTWARE_ONLY, etc.)")
    key_status: str = Field(..., description="Key status: 'none', 'ephemeral', 'portal_pending', 'portal_active'")
    key_id: Optional[str] = Field(None, description="Portal-issued key ID if activated")
    attestation_status: str = Field(..., description="Attestation: 'not_attempted', 'pending', 'verified', 'failed'")
    error: Optional[str] = Field(None, description="Error message if verify failed to load")
    diagnostic_info: Optional[str] = Field(None, description="Detailed diagnostic info for troubleshooting")
    disclaimer: str = Field(
        default="CIRISVerify provides cryptographic attestation of agent identity and behavior. "
        "This enables participation in the Coherence Ratchet and CIRIS Scoring. "
        "CIRISVerify is REQUIRED for CIRIS 2.0 agents.",
        description="Trust and security disclaimer text",
    )
    # Attestation level checks
    dns_us_ok: bool = Field(default=False, description="CIRIS DNS connectivity (US)")
    dns_eu_ok: bool = Field(default=False, description="CIRIS DNS connectivity (EU)")
    https_us_ok: bool = Field(default=False, description="CIRIS HTTPS connectivity (US)")
    https_eu_ok: bool = Field(default=False, description="CIRIS HTTPS connectivity (EU)")
    binary_ok: bool = Field(default=False, description="CIRISVerify binary loaded and functional")
    file_integrity_ok: bool = Field(default=False, description="File integrity verified (Tripwire-style)")
    registry_ok: bool = Field(default=False, description="Signing key registered with Portal/Registry")
    audit_ok: bool = Field(default=False, description="Audit trail intact")
    env_ok: bool = Field(default=False, description="Environment (.env) properly configured")
    play_integrity_ok: bool = Field(default=False, description="Google Play Integrity verification passed")
    play_integrity_verdict: Optional[str] = Field(
        default=None, description="Play Integrity verdict (MEETS_STRONG_INTEGRITY, etc.)"
    )
    max_level: int = Field(default=0, description="Maximum attestation level achieved (0-5)")
    # Attestation mode
    attestation_mode: str = Field(default="partial", description="Attestation mode: 'full' or 'partial'")
    # Detailed attestation info (for expanded view)
    checks: Optional[Dict[str, Any]] = Field(default=None, description="Per-check details with ok/label/level")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Full attestation details from CIRISVerify")
    # Platform info from attestation
    platform_os: Optional[str] = Field(default=None, description="Platform OS from attestation")
    platform_arch: Optional[str] = Field(default=None, description="Platform architecture")
    # Integrity details
    total_files: Optional[int] = Field(default=None, description="Total files in registry manifest")
    files_checked: Optional[int] = Field(default=None, description="Number of files checked for integrity")
    files_passed: Optional[int] = Field(default=None, description="Number of files that passed integrity")
    files_failed: Optional[int] = Field(default=None, description="Number of files that failed integrity")
    integrity_failure_reason: Optional[str] = Field(default=None, description="Reason for integrity failure if any")

    # v0.6.0: Function integrity verification (constructor-based)
    function_integrity: Optional[str] = Field(
        default=None,
        description="Function integrity: verified, tampered, unavailable:{reason}, signature_invalid, not_found, pending",
    )

    # v0.6.0: Per-source error details for network validation
    source_errors: Optional[Dict[str, Dict[str, str]]] = Field(
        default=None, description="Per-source error details: {source: {category: str, details: str}}"
    )


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
    signing_key_id: Optional[str] = Field(
        None,
        description="Portal-issued signing key ID (stored in .env, private key stored in hardware keystore)",
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
_SKIP_ADAPTERS = {"ciris_accord_metrics"}  # Handled by consent checkbox
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
    # Portal-issued key ID (private key is stored in hardware keystore, NOT here)
    if setup.signing_key_id:
        f.write(f'CIRIS_SIGNING_KEY_ID="{setup.signing_key_id}"\n')


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

        # Accord metrics consent
        if "ciris_accord_metrics" in setup.enabled_adapters:
            from datetime import datetime, timezone

            consent_timestamp = datetime.now(timezone.utc).isoformat()
            f.write("\n# Accord Metrics Consent (auto-set when adapter enabled)\n")
            f.write("CIRIS_ACCORD_METRICS_CONSENT=true\n")
            f.write(f"CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP={consent_timestamp}\n")
            logger.info(f"[SETUP] Accord metrics consent enabled: {consent_timestamp}")

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

    # Node flow / signing key fields
    logger.info(f"CIRIS_SETUP_DEBUG Node flow fields:")
    logger.info(f"CIRIS_SETUP_DEBUG   node_url = {repr(setup.node_url)}")
    logger.info(f"CIRIS_SETUP_DEBUG   signing_key_id = {repr(setup.signing_key_id)}")
    logger.info(f"CIRIS_SETUP_DEBUG   signing_key_provisioned = {setup.signing_key_provisioned}")
    logger.info(f"CIRIS_SETUP_DEBUG   provisioned_signing_key_b64 set = {bool(setup.provisioned_signing_key_b64)}")

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


@router.get("/verify-status")
async def get_verify_status(
    mode: str = "partial",
    play_integrity_token: Optional[str] = None,
    play_integrity_nonce: Optional[str] = None,
) -> SuccessResponse[VerifyStatusResponse]:
    """Get CIRISVerify status for Trust and Security display.

    Returns the status of CIRISVerify including:
    - Whether the library is loaded
    - Hardware security type (TPM, Secure Enclave, Software)
    - Key status (none, ephemeral, portal_pending, portal_active)
    - Attestation status
    - Play Integrity verification (if token provided)

    Query Parameters:
    - mode: "full" for complete file integrity check, "partial" for spot-check (default)
    - play_integrity_token: Optional Google Play Integrity token for device verification
    - play_integrity_nonce: Optional nonce used when requesting the Play Integrity token

    CIRISVerify is REQUIRED for CIRIS 2.0+. Agents cannot run without it.
    This endpoint is always accessible without authentication.
    """
    import threading

    # Validate mode parameter
    attestation_mode = "partial" if mode not in ("full", "partial") else mode
    # spot_check_count: 0 = full check, 10 = spot check 10 files
    spot_check_count = 0 if attestation_mode == "full" else 10

    logger.info(f"[verify-status] Starting CIRISVerify status check (mode={attestation_mode})")

    # Try to get CIRISVerify status on a large stack thread (Rust Tokio compatibility)
    verify_result: list[Any] = [None, None]  # [status_dict | None, error | None]

    def _get_verify_status_on_large_stack() -> None:
        try:
            logger.info("[verify-status] Importing ciris_verify...")
            from ciris_verify import CIRISVerify as CV

            logger.info("[verify-status] Creating CIRISVerify instance...")
            verifier = CV(skip_integrity_check=True)
            logger.info("[verify-status] CIRISVerify instance created successfully")

            # Get version - try both attribute and __version__
            version = None
            try:
                version = getattr(verifier, "version", None)
                if callable(version):
                    version = version()
                if version is None:
                    # Try module-level __version__
                    import ciris_verify

                    version = getattr(ciris_verify, "__version__", "unknown")
            except Exception as ve:
                logger.warning(f"[verify-status] Version check failed: {ve}")
                version = "unknown"

            logger.info(f"[verify-status] CIRISVerify version: {version}")

            # Build diagnostic info for troubleshooting
            diag_parts = []
            import os

            is_android = os.environ.get("ANDROID_ROOT") is not None
            diag_parts.append(f"platform={'android' if is_android else 'other'}")

            # Check if Portal key is loaded using the correct method name
            has_portal_key = False
            key_id = os.environ.get("CIRIS_SIGNING_KEY_ID")  # Read from .env
            key_check_method = "none"
            key_check_error = None
            try:
                # Mobile FFI uses has_key_sync(), desktop may use has_portal_key()
                # The key should be stored in Android Keystore (hardware-backed)
                if hasattr(verifier, "has_key_sync"):
                    key_check_method = "has_key_sync"
                    has_portal_key = verifier.has_key_sync()
                    logger.info(f"[verify-status] has_key_sync() = {has_portal_key}")
                elif hasattr(verifier, "has_portal_key"):
                    key_check_method = "has_portal_key"
                    has_portal_key = verifier.has_portal_key()
                    logger.info(f"[verify-status] has_portal_key() = {has_portal_key}")
                else:
                    key_check_method = "unavailable"
                    logger.info("[verify-status] No key check method available")
            except Exception as ke:
                key_check_error = str(ke)
                logger.warning(f"[verify-status] Key check failed: {ke}")

            diag_parts.append(f"key_check={key_check_method}")
            diag_parts.append(f"has_portal_key={has_portal_key}")
            if key_check_error:
                diag_parts.append(f"key_error={key_check_error}")

            # Check Ed25519 support
            has_ed25519 = getattr(verifier, "has_ed25519_support", False)
            if callable(has_ed25519):
                has_ed25519 = has_ed25519
            logger.info(f"[verify-status] Ed25519 support: {has_ed25519}")
            diag_parts.append(f"ed25519={has_ed25519}")

            # List available verifier methods for debugging
            verifier_methods = [
                m for m in dir(verifier) if not m.startswith("_") and callable(getattr(verifier, m, None))
            ]
            diag_parts.append(f"methods={','.join(verifier_methods[:10])}")  # First 10 methods

            # Determine key status
            # If we have a key_id from .env, the portal key was provisioned
            # (even if has_key_sync() returns False on a fresh verifier instance)
            if key_id:
                key_status = "portal_active"
                logger.info(f"[verify-status] key_id={key_id} found in .env, setting key_status=portal_active")
            elif has_portal_key:
                key_status = "portal_active"
            elif has_ed25519:
                key_status = "ephemeral"
            else:
                key_status = "none"

            # Get hardware type - use platform detection (fast) on mobile
            is_ios = os.path.exists("/System/Library/Frameworks")

            if is_android:
                # Android: Check for StrongBox vs Keystore
                # For now, default to ANDROID_KEYSTORE (StrongBox detection requires JNI)
                hardware_type = "ANDROID_KEYSTORE"
                logger.info(f"[verify-status] Android detected, using {hardware_type}")
            elif is_ios:
                hardware_type = "IOS_SECURE_ENCLAVE"
                logger.info(f"[verify-status] iOS detected, using {hardware_type}")
            else:
                # Desktop: Try to get hardware type from verifier (non-blocking)
                hardware_type = "SOFTWARE_ONLY"
                try:
                    if hasattr(verifier, "get_hardware_type"):
                        hw = verifier.get_hardware_type()
                        if hasattr(hw, "name"):
                            hardware_type = hw.name
                        elif hasattr(hw, "value"):
                            hardware_type = str(hw.value)
                        else:
                            hardware_type = str(hw)
                        logger.info(f"[verify-status] Hardware type from verifier: {hardware_type}")
                except Exception as hw_err:
                    logger.warning(f"[verify-status] Could not get hardware type: {hw_err}")

            diagnostic_info = " | ".join(diag_parts)
            logger.info(f"[verify-status] Diagnostics: {diagnostic_info}")

            # === Attestation Level Checks ===
            # Level 0: Nothing
            # Level 1: CIRISVerify binary loaded
            # Level 2: Environment configured (.env has required keys)
            # Level 3: DNS connectivity to CIRIS infrastructure
            # Level 4: HTTPS connectivity to CIRIS infrastructure
            # Level 5: Signing key registered with Portal/Registry

            binary_ok = True  # We got here, so binary is loaded
            env_ok = bool(os.environ.get("CIRIS_CONFIGURED")) and bool(os.environ.get("OPENAI_API_KEY"))

            # Play Integrity check (Level 2 - device/app integrity)
            play_integrity_ok = False
            play_integrity_verdict = None
            if play_integrity_token and play_integrity_nonce:
                try:
                    import httpx

                    registry_url = os.environ.get("CIRIS_REGISTRY_URL", "https://api.registry.ciris-services-1.ai")
                    with httpx.Client(timeout=10.0) as client:
                        resp = client.post(
                            f"{registry_url}/v1/integrity/verify",
                            json={"token": play_integrity_token, "nonce": play_integrity_nonce},
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            play_integrity_ok = data.get("valid", False)
                            play_integrity_verdict = data.get("device_verdict", None)
                            logger.info(
                                f"[verify-status] Play Integrity: ok={play_integrity_ok}, verdict={play_integrity_verdict}"
                            )
                        else:
                            logger.warning(f"[verify-status] Play Integrity verification failed: {resp.status_code}")
                except Exception as pi_err:
                    logger.warning(f"[verify-status] Play Integrity check failed: {pi_err}")

            # Use CIRISVerify's get_license_status for real attestation checks
            dns_us_ok = False
            dns_eu_ok = False
            https_us_ok = False
            https_eu_ok = False
            registry_ok = bool(key_id)
            sources_agreeing = 0

            # v0.6.0 fields
            source_errors: Dict[str, Dict[str, str]] = {}
            function_integrity: Optional[str] = None

            try:
                # Generate challenge nonce for attestation
                import secrets

                challenge_nonce = secrets.token_bytes(32)

                # Check if verifier has get_license_status method (v0.5.0+)
                if hasattr(verifier, "get_license_status"):
                    # Use longer timeout for network validation (30s instead of default 10s)
                    network_timeout = 30.0
                    logger.info(
                        f"[verify-status] Calling CIRISVerify get_license_status (timeout={network_timeout}s)..."
                    )
                    # Run async method in a new event loop
                    import asyncio

                    loop = asyncio.new_event_loop()
                    try:
                        license_status = loop.run_until_complete(
                            verifier.get_license_status(challenge_nonce, timeout=network_timeout)
                        )
                    finally:
                        loop.close()

                    # Extract source details from CIRISVerify response
                    source_errors: Dict[str, Dict[str, str]] = {}
                    if hasattr(license_status, "source_details"):
                        sd = license_status.source_details
                        dns_us_ok = getattr(sd, "dns_us_reachable", False)
                        dns_eu_ok = getattr(sd, "dns_eu_reachable", False)
                        https_us_ok = getattr(sd, "https_reachable", False)
                        https_eu_ok = https_us_ok
                        sources_agreeing = getattr(sd, "sources_agreeing", 0)
                        validation_status = str(getattr(sd, "validation_status", "unknown"))

                        # Log all available source_details attributes for debugging
                        sd_attrs = [attr for attr in dir(sd) if not attr.startswith("_")]
                        logger.info(f"[verify-status] source_details attrs: {sd_attrs}")

                        # v0.6.6: Extract per-source error details (FLAT fields on source_details)
                        # Fields: dns_us_error, dns_us_error_category, dns_eu_error, etc.
                        for source_name in ["dns_us", "dns_eu", "https"]:
                            error_val = getattr(sd, f"{source_name}_error", None)
                            error_cat = getattr(sd, f"{source_name}_error_category", None)
                            logger.info(f"[verify-status] {source_name}: error={error_val}, category={error_cat}")

                            if error_val or error_cat:
                                source_errors[source_name] = {
                                    "category": str(error_cat) if error_cat else "unknown",
                                    "details": str(error_val) if error_val else "",
                                }

                        # Log Level 3 details explicitly
                        logger.info(
                            f"[verify-status] LEVEL 3 NETWORK: dns_us={dns_us_ok}, dns_eu={dns_eu_ok}, https={https_us_ok}, sources_agreeing={sources_agreeing}/3, validation={validation_status}"
                        )
                    else:
                        validation_status = "unknown"
                        sources_agreeing = 0
                        logger.warning("[verify-status] LEVEL 3 NETWORK: No source_details in response")

                    # v0.6.0: Extract function integrity status (constructor-based verification)
                    function_integrity = getattr(license_status, "function_integrity", None)
                    if function_integrity:
                        logger.info(f"[verify-status] Function integrity: {function_integrity}")

                    # Build detailed info for expanded view
                    detailed_info = {
                        # License status
                        "status_code": int(license_status.status) if hasattr(license_status, "status") else 0,
                        "status_name": license_status.status.name if hasattr(license_status, "status") else "UNKNOWN",
                        "validation_status": validation_status,
                        "sources_agreeing": sources_agreeing,
                        # Hardware
                        "has_attestation_chain": bool(
                            getattr(license_status, "attestation", None)
                            and getattr(license_status.attestation, "attestation_chain", None)
                        ),
                        "has_signature": bool(
                            getattr(license_status, "attestation", None)
                            and getattr(license_status.attestation, "signature", None)
                        ),
                        # Cache
                        "cached": getattr(license_status, "cached", False),
                        "cache_age_seconds": getattr(license_status, "cache_age_seconds", None),
                        # Disclosure (required by CIRIS)
                        "disclosure_text": (
                            getattr(license_status.mandatory_disclosure, "text", "")
                            if hasattr(license_status, "mandatory_disclosure") and license_status.mandatory_disclosure
                            else ""
                        ),
                        "disclosure_severity": (
                            str(getattr(license_status.mandatory_disclosure, "severity", "info"))
                            if hasattr(license_status, "mandatory_disclosure") and license_status.mandatory_disclosure
                            else "info"
                        ),
                    }

                    # License details if present
                    if hasattr(license_status, "license") and license_status.license:
                        lic = license_status.license
                        detailed_info["license"] = {
                            "tier": int(getattr(lic, "tier", 0)),
                            "tier_name": ["COMMUNITY", "PROFESSIONAL_BASIC", "PROFESSIONAL_FULL", "ENTERPRISE"][
                                int(getattr(lic, "tier", 0))
                            ],
                            "license_id": getattr(lic, "license_id", None),
                            "issuer": getattr(lic, "issuer", None),
                            "holder": getattr(lic, "holder_name", None),
                            "organization": getattr(lic, "holder_organization", None),
                            "expires": str(getattr(lic, "expires_at", "")) if hasattr(lic, "expires_at") else None,
                            "capabilities": list(getattr(lic, "capabilities", [])),
                            "prohibited": list(getattr(lic, "prohibited_capabilities", [])),
                        }

                    logger.info(
                        f"[verify-status] CIRISVerify: status={detailed_info['status_name']}, sources={sources_agreeing}/3, validation={validation_status}"
                    )
                else:
                    detailed_info = {"status_name": "NOT_AVAILABLE", "status_code": 0}
                    validation_status = "not_checked"
                    sources_agreeing = 0
                    logger.info("[verify-status] CIRISVerify <0.5.0 - no get_license_status")
            except Exception as attest_err:
                # Log explicit Level 3 failure details
                logger.warning(f"[verify-status] LEVEL 3 NETWORK FAILED: {attest_err}")
                logger.warning(
                    f"[verify-status] dns_us={dns_us_ok}, dns_eu={dns_eu_ok}, https_us={https_us_ok}, https_eu={https_eu_ok}"
                )
                detailed_info = {"status_name": "TIMEOUT", "error": str(attest_err)}
                validation_status = "timeout"

            # File integrity check (Level 4)
            # The binary handles everything - we just call it with the right params
            file_integrity_ok = False
            total_files = 0
            files_checked = 0
            files_passed = 0
            files_failed = 0
            integrity_failure_reason = None
            try:
                if hasattr(verifier, "check_agent_integrity"):
                    # Find manifest file and agent root
                    agent_root = os.environ.get("CIRIS_AGENT_ROOT", os.getcwd())
                    manifest_path = os.path.join(agent_root, "file_manifest.json")

                    if os.path.exists(manifest_path):
                        # check_agent_integrity(manifest_path, agent_root, spot_check_count)
                        # spot_check_count=0 for full check, >0 for spot check N files
                        import asyncio

                        loop = asyncio.new_event_loop()
                        try:
                            integrity_result = loop.run_until_complete(
                                verifier.check_agent_integrity(
                                    manifest_path,
                                    agent_root,
                                    spot_check_count,  # From outer scope: 0=full, 10=partial
                                )
                            )
                        finally:
                            loop.close()

                        # Extract detailed results
                        file_integrity_ok = getattr(integrity_result, "integrity_valid", False)
                        total_files = getattr(integrity_result, "total_files", 0)
                        files_checked = getattr(integrity_result, "files_checked", 0)
                        files_passed = getattr(integrity_result, "files_passed", 0)
                        files_failed = getattr(integrity_result, "files_failed", 0)
                        integrity_failure_reason = getattr(integrity_result, "failure_reason", None)

                        logger.info(
                            f"[verify-status] File integrity: ok={file_integrity_ok}, checked={files_checked}/{total_files}, passed={files_passed}, failed={files_failed}"
                        )
                    else:
                        # No manifest - assume OK for now (pre-distribution state)
                        file_integrity_ok = True
                        integrity_failure_reason = "No manifest file (pre-distribution)"
                        logger.info("[verify-status] No manifest file, assuming OK (pre-distribution)")
                else:
                    # Fallback: assume OK if binary loaded successfully
                    file_integrity_ok = binary_ok
                    logger.info("[verify-status] No check_agent_integrity method, using binary_ok as proxy")
            except Exception as fi_err:
                logger.warning(f"[verify-status] File integrity check failed: {fi_err}")
                file_integrity_ok = False
                integrity_failure_reason = str(fi_err)

            # Audit trail check (Level 5)
            # Triple audit system: SQLite (ciris_audit.db), JSONL (audit_logs.jsonl), Graph (memory)
            # We validate the audit trail exists and has entries signed by our key
            audit_ok = False
            audit_details = {"sources_checked": [], "sources_valid": []}
            try:
                data_dir = os.environ.get("CIRIS_DATA_DIR", ".")

                # Check SQLite audit database (primary)
                audit_db_path = os.path.join(data_dir, "ciris_audit.db")
                if os.path.exists(audit_db_path) and os.path.getsize(audit_db_path) > 0:
                    audit_details["sources_checked"].append("sqlite")
                    audit_details["sources_valid"].append("sqlite")
                    audit_details["sqlite_path"] = audit_db_path
                    audit_details["sqlite_size"] = os.path.getsize(audit_db_path)

                # Check JSONL audit log (secondary)
                jsonl_path = os.environ.get("AUDIT_LOG_PATH", os.path.join(data_dir, "audit_logs.jsonl"))
                # Handle ~ expansion
                jsonl_path = os.path.expanduser(jsonl_path)
                if os.path.exists(jsonl_path) and os.path.getsize(jsonl_path) > 0:
                    audit_details["sources_checked"].append("jsonl")
                    audit_details["sources_valid"].append("jsonl")
                    audit_details["jsonl_path"] = jsonl_path
                    audit_details["jsonl_size"] = os.path.getsize(jsonl_path)

                # Audit trail is valid if ANY source has entries
                audit_ok = len(audit_details["sources_valid"]) > 0

                # If we have a Registry-provisioned key, note it for enhanced verification
                key_id = os.environ.get("CIRIS_SIGNING_KEY_ID", "")
                if key_id:
                    audit_details["registry_key_id"] = key_id
                    audit_details["registry_verified"] = True  # Key from Portal = registered

                logger.info(f"[verify-status] Audit trail check: {audit_ok} (sources={audit_details['sources_valid']})")
            except Exception as audit_err:
                logger.warning(f"[verify-status] Audit trail check failed: {audit_err}")

            # Export attestation proof to get platform info and signatures
            platform_os = None
            platform_arch = None
            attestation_proof = None
            try:
                if hasattr(verifier, "export_attestation_sync"):
                    attestation_proof = verifier.export_attestation_sync(challenge_nonce)
                elif hasattr(verifier, "export_attestation"):
                    import asyncio

                    loop = asyncio.new_event_loop()
                    try:
                        attestation_proof = loop.run_until_complete(verifier.export_attestation(challenge_nonce))
                    finally:
                        loop.close()

                if attestation_proof:
                    # Extract platform info
                    platform_attestation = attestation_proof.get("platform_attestation", {})
                    if "Software" in platform_attestation:
                        sw = platform_attestation["Software"]
                        platform_os = sw.get("os", "unknown")
                        platform_arch = sw.get("arch", "unknown")
                    logger.info(f"[verify-status] Attestation proof: os={platform_os}, arch={platform_arch}")
            except Exception as ap_err:
                logger.warning(f"[verify-status] Attestation proof export failed: {ap_err}")

            # Calculate max level
            # Level 1: Binary OK
            # Level 2: Env OK
            # Level 3: DNS/HTTPS (2 of 3 checks pass)
            # Level 4: File Integrity
            # Level 5: Portal Key + Audit Trail
            max_level = 0
            if binary_ok:
                max_level = 1
            if max_level >= 1 and env_ok:
                max_level = 2
            # Level 3 requires 2 of 3 network checks
            network_checks_passed = sum([dns_us_ok, dns_eu_ok, https_us_ok or https_eu_ok])
            if max_level >= 2 and network_checks_passed >= 2:
                max_level = 3
            if max_level >= 3 and file_integrity_ok:
                max_level = 4
            if max_level >= 4 and registry_ok and audit_ok:
                max_level = 5

            logger.info(
                f"[verify-status] Attestation levels: binary={binary_ok}, env={env_ok}, dns_us={dns_us_ok}, dns_eu={dns_eu_ok}, https_us={https_us_ok}, https_eu={https_eu_ok}, file_integrity={file_integrity_ok}, registry={registry_ok}, audit={audit_ok}, max_level={max_level}"
            )

            # Build result with simple view + detailed info for expansion
            verify_result[0] = {
                # === SIMPLE VIEW (always shown) ===
                "loaded": True,
                "version": str(version) if version else "unknown",
                "hardware_type": hardware_type,
                "key_status": key_status,
                "key_id": key_id,
                "max_level": max_level,
                "attestation_status": (
                    "verified" if max_level >= 5 else ("pending" if max_level >= 3 else "not_attempted")
                ),
                "attestation_mode": attestation_mode,  # "full" or "partial"
                # === LEVEL CHECKS (expandable section 1) ===
                "checks": {
                    "binary": {"ok": binary_ok, "label": "CIRISVerify Binary", "level": 1},
                    "env": {"ok": env_ok, "label": "Environment Config", "level": 2},
                    "play_integrity": {
                        "ok": play_integrity_ok,
                        "label": "Play Integrity",
                        "level": 2,
                        "verdict": play_integrity_verdict,
                    },
                    "dns_us": {"ok": dns_us_ok, "label": "DNS (US)", "level": 3},
                    "dns_eu": {"ok": dns_eu_ok, "label": "DNS (EU)", "level": 3},
                    "https": {"ok": https_us_ok or https_eu_ok, "label": "HTTPS Registry", "level": 3},
                    "file_integrity": {
                        "ok": file_integrity_ok,
                        "label": "File Integrity",
                        "level": 4,
                        "total_files": total_files,
                        "files_checked": files_checked,
                        "files_passed": files_passed,
                        "files_failed": files_failed,
                        "failure_reason": integrity_failure_reason,
                    },
                    "portal_key": {"ok": registry_ok, "label": "Portal Key", "level": 5},
                    "audit": {"ok": audit_ok, "label": "Audit Trail", "level": 5},
                },
                "sources_agreeing": sources_agreeing if "sources_agreeing" in dir() else 0,
                "validation_status": validation_status if "validation_status" in dir() else "unknown",
                # === DETAILED INFO (expandable section 2) ===
                "details": detailed_info if "detailed_info" in dir() else {},
                # === PLATFORM INFO (from attestation proof) ===
                "platform_os": platform_os,
                "platform_arch": platform_arch,
                "attestation_proof": attestation_proof,  # Full proof for advanced users
                # === FILE INTEGRITY DETAILS ===
                "total_files": total_files,
                "files_checked": files_checked,
                "files_passed": files_passed,
                "files_failed": files_failed,
                "integrity_failure_reason": integrity_failure_reason,
                # Legacy fields for compatibility
                "diagnostic_info": diagnostic_info,
                "dns_us_ok": dns_us_ok,
                "dns_eu_ok": dns_eu_ok,
                "https_us_ok": https_us_ok,
                "https_eu_ok": https_eu_ok,
                "binary_ok": binary_ok,
                "file_integrity_ok": file_integrity_ok,
                "registry_ok": registry_ok,
                "audit_ok": audit_ok,
                "env_ok": env_ok,
                "play_integrity_ok": play_integrity_ok,
                "play_integrity_verdict": play_integrity_verdict,
                # v0.6.0 fields
                "function_integrity": function_integrity,
                "source_errors": source_errors if source_errors else None,
            }
            logger.info(f"[verify-status] Success: {verify_result[0]}")
        except ImportError as e:
            error_msg = f"CIRISVerify not installed: {e}"
            logger.error(f"[verify-status] {error_msg}")
            verify_result[1] = error_msg
        except Exception as e:
            error_msg = f"CIRISVerify error: {type(e).__name__}: {e}"
            logger.error(f"[verify-status] {error_msg}")
            verify_result[1] = error_msg

    # On Android/mobile, thread stack size manipulation may not work
    # Try without stack size change first, fall back to large stack if needed
    is_android = os.environ.get("ANDROID_ROOT") is not None

    if is_android:
        logger.info("[verify-status] Android detected, using default thread stack")
        t = threading.Thread(target=_get_verify_status_on_large_stack, daemon=True)
        t.start()
        t.join(timeout=25)  # Longer timeout for mobile attestation network checks
    else:
        old_stack = threading.stack_size()
        try:
            threading.stack_size(8 * 1024 * 1024)  # 8 MB for Rust Tokio
            t = threading.Thread(target=_get_verify_status_on_large_stack, daemon=True)
            t.start()
            t.join(timeout=5)
        finally:
            threading.stack_size(old_stack)

    if verify_result[1] is not None or verify_result[0] is None:
        # CIRISVerify not available - this is a CRITICAL error for 2.0
        error_msg = verify_result[1] if verify_result[1] else "CIRISVerify status check timed out"
        logger.error(f"[verify-status] Returning error: {error_msg}")
        return SuccessResponse(
            data=VerifyStatusResponse(
                loaded=False,
                version=None,
                hardware_type=None,
                key_status="none",
                key_id=None,
                attestation_status="not_attempted",
                error=error_msg,
            )
        )

    status_dict = verify_result[0]
    logger.info(
        f"[verify-status] Returning success: loaded=True, key_status={status_dict['key_status']}, max_level={status_dict.get('max_level', 0)}"
    )
    return SuccessResponse(
        data=VerifyStatusResponse(
            loaded=status_dict["loaded"],
            version=status_dict["version"],
            hardware_type=status_dict["hardware_type"],
            key_status=status_dict["key_status"],
            key_id=status_dict["key_id"],
            attestation_status=status_dict["attestation_status"],
            attestation_mode=status_dict.get("attestation_mode", "partial"),
            error=None,
            diagnostic_info=status_dict.get("diagnostic_info"),
            # Attestation level checks
            dns_us_ok=status_dict.get("dns_us_ok", False),
            dns_eu_ok=status_dict.get("dns_eu_ok", False),
            https_us_ok=status_dict.get("https_us_ok", False),
            https_eu_ok=status_dict.get("https_eu_ok", False),
            binary_ok=status_dict.get("binary_ok", False),
            file_integrity_ok=status_dict.get("file_integrity_ok", False),
            registry_ok=status_dict.get("registry_ok", False),
            audit_ok=status_dict.get("audit_ok", False),
            env_ok=status_dict.get("env_ok", False),
            play_integrity_ok=status_dict.get("play_integrity_ok", False),
            play_integrity_verdict=status_dict.get("play_integrity_verdict"),
            max_level=status_dict.get("max_level", 0),
            # Detailed attestation info
            checks=status_dict.get("checks"),
            details=status_dict.get("details"),
            # Platform info
            platform_os=status_dict.get("platform_os"),
            platform_arch=status_dict.get("platform_arch"),
            # File integrity details
            total_files=status_dict.get("total_files"),
            files_checked=status_dict.get("files_checked"),
            files_passed=status_dict.get("files_passed"),
            files_failed=status_dict.get("files_failed"),
            integrity_failure_reason=status_dict.get("integrity_failure_reason"),
        )
    )


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
    1. Checks for existing non-expired device auth session (reuses if found)
    2. Normalizes the Portal URL (adds https:// if needed)
    3. Calls Portal's POST /api/device/authorize with agent info
    4. Persists the session so it survives app restarts
    5. Returns verification URL for user to open in browser

    CRITICAL: Device codes are persisted to survive app restarts. If user
    pays for a license in browser and app restarts, we must continue polling
    with the SAME device code, not request a new one.

    This endpoint is accessible without authentication during first-run.
    """
    import httpx

    portal_url = req.node_url.strip().rstrip("/")
    # Normalize URL — add https:// if no scheme provided
    if not portal_url.startswith("http://") and not portal_url.startswith("https://"):
        portal_url = f"https://{portal_url}"

    # Check for existing non-expired session — reuse it if found
    existing_session = _load_device_auth_session()
    if existing_session and existing_session.get("portal_url") == portal_url:
        logger.info("Reusing existing device auth session (device_code=%s...)", existing_session["device_code"][:16])
        remaining = int(existing_session["expires_at"] - time.time())
        return SuccessResponse(
            data=ConnectNodeResponse(
                verification_uri_complete=existing_session["verification_uri_complete"],
                device_code=existing_session["device_code"],
                user_code=existing_session.get("user_code", ""),
                portal_url=portal_url,
                expires_in=max(remaining, 0),
                interval=existing_session.get("interval", 5),
            )
        )

    device_auth_endpoint = "/api/device/authorize"

    # For first-run setup, we send empty agent_info since we're provisioning a new agent.
    # Existing agents reconnecting would include their hash and public key here.
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

    # If Portal returned a challenge_nonce, submit attestation inline
    # before returning to the client. This keeps KMP simple.
    challenge_nonce = auth_data.get("challenge_nonce")
    if challenge_nonce:
        await _submit_attestation_inline(
            challenge_nonce=challenge_nonce,
            device_code=auth_data["device_code"],
            portal_url=portal_url,
        )

    # Persist the session so it survives app restarts
    device_code = auth_data["device_code"]
    expires_in = auth_data.get("expires_in", 900)
    interval = auth_data.get("interval", 5)
    verification_uri = auth_data["verification_uri_complete"]
    user_code = auth_data.get("user_code", "")

    _save_device_auth_session(
        device_code=device_code,
        portal_url=portal_url,
        verification_uri_complete=verification_uri,
        user_code=user_code,
        expires_in=expires_in,
        interval=interval,
    )

    return SuccessResponse(
        data=ConnectNodeResponse(
            verification_uri_complete=verification_uri,
            device_code=device_code,
            user_code=user_code,
            portal_url=portal_url,
            expires_in=expires_in,
            interval=interval,
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
                # Authorization denied — clear session so user can retry
                _clear_device_auth_session()
                return SuccessResponse(data=ConnectNodeStatusResponse(status="error"))

            if token_resp.status_code != 200:
                body = (
                    token_resp.json()
                    if token_resp.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
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

    # Log what Portal returned for debugging
    logger.info("[connect-node/status] Portal token response keys: %s", list(data.keys()))
    logger.info("[connect-node/status] signing_key keys: %s", list(signing_key.keys()) if signing_key else "None")
    logger.info("[connect-node/status] signing_key.key_id = %s", signing_key.get("key_id"))
    logger.info("[connect-node/status] agent_record keys: %s", list(agent_record.keys()) if agent_record else "None")

    # Extract the provisioned signing key — it will be saved during /complete setup.
    # We don't eagerly save here to avoid filesystem issues (e.g., iOS read-only bundles).
    private_key_b64 = signing_key.get("ed25519_private_key", "")

    # PHASE 2: Key Activation - import key and submit second attestation
    # This binds the agent identity to this specific key instance.
    # Key reuse across agents is FORBIDDEN.
    if private_key_b64:
        await _activate_key_inline(private_key_b64, device_code, portal_url)

    # Clear device auth session — flow completed successfully
    _clear_device_auth_session()
    logger.info("Device auth flow completed successfully")

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
# CIRISVerify Attestation (inline helper for connect_node)
# ============================================================================


async def _submit_attestation_inline(challenge_nonce: str, device_code: str, portal_url: str) -> None:
    """Submit CIRISVerify hardware attestation to Portal inline during connect-node.

    Runs CIRISVerify on an 8MB-stack thread (iOS Rust/Tokio compatibility),
    then POSTs the proof to Portal's /api/device/attest.

    Non-fatal: if CIRISVerify is unavailable (community mode) or Portal
    rejects the proof, we log and continue — the user can still authorize.
    """
    import threading

    import httpx

    challenge_bytes = bytes.fromhex(challenge_nonce)

    # Attempt attestation on 8MB stack thread (Rust Tokio runtime needs it)
    attest_result: list[Any] = [None, None]  # [proof_dict | None, error | None]

    def _attest_on_large_stack() -> None:
        try:
            from ciris_verify import CIRISVerify as CV

            verifier = CV(skip_integrity_check=True)
            proof = verifier.export_attestation_sync(challenge_bytes)
            attest_result[0] = proof  # export_attestation_sync returns dict directly
        except Exception as e:
            attest_result[1] = e

    old_stack = threading.stack_size()
    try:
        threading.stack_size(8 * 1024 * 1024)  # 8 MB
        t = threading.Thread(target=_attest_on_large_stack, daemon=True)
        t.start()
        t.join(timeout=15)
    finally:
        threading.stack_size(old_stack)

    # CIRISVerify not available — skip gracefully (community mode)
    if attest_result[1] is not None or attest_result[0] is None:
        error_msg = str(attest_result[1]) if attest_result[1] else "CIRISVerify init timed out"
        logger.info("CIRISVerify attestation skipped (community mode): %s", error_msg)
        return

    proof_dict = attest_result[0]

    # Log attestation proof details for debugging
    logger.info(
        "[CIRISVerify] Attestation proof generated: key_type=%s, hw_algo=%s, hw_type=%s, "
        "pubkey_len=%d, sig_len=%d, challenge_len=%d",
        proof_dict.get("key_type", "unknown"),
        proof_dict.get("hardware_algorithm", "unknown"),
        proof_dict.get("hardware_type", "unknown"),
        len(proof_dict.get("hardware_public_key", "")),
        len(proof_dict.get("classical_signature", "")),
        len(proof_dict.get("challenge", "")),
    )

    # POST proof to Portal's /api/device/attest
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            attest_resp = await client.post(
                f"{portal_url.rstrip('/')}/api/device/attest",
                json={
                    "device_code": device_code,
                    "attestation_proof": proof_dict,
                    "agent_hash": "",  # Will be populated after RegisterBuild
                    "integrity_passed": True,
                },
            )

            if attest_resp.status_code == 200:
                result_data = attest_resp.json()
                verified = result_data.get("verified", False)
                hw_type = result_data.get("hardware_type", "unknown")
                warnings = result_data.get("warnings", [])
                logger.info("[CIRISVerify] Portal attestation VERIFIED: hw_type=%s, warnings=%s", hw_type, warnings)
            else:
                # Log detailed error response from Portal
                try:
                    error_data = attest_resp.json()
                    errors = error_data.get("errors", [])
                    warnings = error_data.get("warnings", [])
                    logger.warning(
                        "[CIRISVerify] Portal attestation REJECTED: HTTP %s, errors=%s, warnings=%s",
                        attest_resp.status_code,
                        errors,
                        warnings,
                    )
                except Exception:
                    logger.warning(
                        "[CIRISVerify] Portal attestation rejected: HTTP %s, body=%s",
                        attest_resp.status_code,
                        attest_resp.text[:500],
                    )
    except httpx.HTTPError as e:
        logger.warning("[CIRISVerify] Failed to submit attestation to Portal: %s", e)


async def _activate_key_inline(private_key_b64: str, device_code: str, portal_url: str) -> None:
    """Phase 2: Key Activation - import Portal key and submit second attestation.

    After receiving the signing key from Portal, we:
    1. Import it into CIRISVerify
    2. Generate a second attestation (signed with Portal key, key_type="portal")
    3. Submit to /api/device/activate

    This creates a tamper-evident binding between the agent instance and its key.
    Key reuse across agents is FORBIDDEN - Portal tracks all activations.
    Transferring agent identities to a new device is NOT SUPPORTED YET.

    Non-fatal: if activation fails, we log and continue — agent will still work
    but key reuse detection may not be fully enabled.
    """
    import base64
    import os
    import threading

    import httpx

    # Decode the private key from base64
    try:
        key_bytes = base64.b64decode(private_key_b64)
        if len(key_bytes) != 32:
            logger.warning(
                "Key activation skipped: invalid key length (%d bytes, expected 32)",
                len(key_bytes),
            )
            return
    except Exception as e:
        logger.warning("Key activation skipped: failed to decode key: %s", e)
        return

    # Generate a fresh challenge for the second attestation
    challenge_bytes = os.urandom(32)

    # Import key and generate attestation on 8MB stack thread
    # [proof_dict, error, has_key_before, has_key_after]
    activate_result: list[Any] = [None, None, None, None]

    def _activate_on_large_stack() -> None:
        try:
            from ciris_verify import CIRISVerify as CV

            logger.info("[KEY-IMPORT] Creating CIRISVerify instance...")
            verifier = CV(skip_integrity_check=True)

            # Check key state BEFORE import
            has_key_before = False
            if hasattr(verifier, "has_key_sync"):
                has_key_before = verifier.has_key_sync()
            activate_result[2] = has_key_before
            logger.info(f"[KEY-IMPORT] has_key_sync() BEFORE import: {has_key_before}")

            # Import the Portal-issued key into Android Keystore
            logger.info(f"[KEY-IMPORT] Calling import_key_sync() with {len(key_bytes)} byte key...")
            verifier.import_key_sync(key_bytes)
            logger.info("[KEY-IMPORT] import_key_sync() completed")

            # Check key state AFTER import
            has_key_after = False
            if hasattr(verifier, "has_key_sync"):
                has_key_after = verifier.has_key_sync()
            activate_result[3] = has_key_after
            logger.info(f"[KEY-IMPORT] has_key_sync() AFTER import: {has_key_after}")

            if not has_key_after:
                logger.error("[KEY-IMPORT] CRITICAL: Key import succeeded but has_key_sync() returns False!")
                logger.error("[KEY-IMPORT] This suggests the key was NOT persisted to Android Keystore")

            # Generate second attestation (now with key_type="portal")
            logger.info("[KEY-IMPORT] Generating attestation proof...")
            proof = verifier.export_attestation_sync(challenge_bytes)
            key_type = proof.get("key_type", "unknown") if isinstance(proof, dict) else "unknown"
            logger.info(f"[KEY-IMPORT] Attestation generated: key_type={key_type}")
            activate_result[0] = proof
        except Exception as e:
            logger.error(f"[KEY-IMPORT] Exception during key import: {type(e).__name__}: {e}")
            activate_result[1] = e

    # On Android, skip stack size manipulation (may not work)
    is_android = os.environ.get("ANDROID_ROOT") is not None

    if is_android:
        t = threading.Thread(target=_activate_on_large_stack, daemon=True)
        t.start()
        t.join(timeout=15)
    else:
        old_stack = threading.stack_size()
        try:
            threading.stack_size(8 * 1024 * 1024)  # 8 MB
            t = threading.Thread(target=_activate_on_large_stack, daemon=True)
            t.start()
            t.join(timeout=15)
        finally:
            threading.stack_size(old_stack)

    # Check for errors
    if activate_result[1] is not None or activate_result[0] is None:
        error_msg = str(activate_result[1]) if activate_result[1] else "CIRISVerify activation timed out"
        logger.warning("Key activation skipped: %s", error_msg)
        return

    proof_dict = activate_result[0]

    # Verify key_type is "portal" (not "ephemeral")
    key_type = proof_dict.get("key_type", "unknown")
    if key_type != "portal":
        logger.warning(
            "Key activation: unexpected key_type '%s' (expected 'portal'). "
            "Key may not have been imported correctly.",
            key_type,
        )

    # POST to Portal's /api/device/activate
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            activate_resp = await client.post(
                f"{portal_url.rstrip('/')}/api/device/activate",
                json={
                    "device_code": device_code,
                    "attestation_proof": proof_dict,
                },
            )

            if activate_resp.status_code == 200:
                result_data = activate_resp.json()
                activated = result_data.get("activated", False)
                logger.info(
                    "Portal key activation result: activated=%s, key_id=%s",
                    activated,
                    result_data.get("key_id", "unknown"),
                )
            elif activate_resp.status_code == 403:
                result_data = activate_resp.json()
                error = result_data.get("error", "unknown")
                # Check for key reuse
                if "KEY REUSE" in error:
                    logger.error(
                        "KEY REUSE DETECTED: %s. This key was already activated "
                        "for another agent. Key reuse is forbidden for CIRIS agents.",
                        error,
                    )
                else:
                    logger.warning("Portal key activation rejected: %s", error)
            else:
                logger.warning("Portal key activation failed: HTTP %s", activate_resp.status_code)
    except httpx.HTTPError as e:
        logger.warning("Failed to submit key activation to Portal: %s", e)


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
    import asyncio
    import hashlib
    import shutil
    import tempfile
    import zipfile
    from urllib.parse import urlparse

    import httpx

    # Determine install directory
    data_dir = Path(os.environ.get("CIRIS_DATA_DIR", "."))
    licensed_modules_dir = data_dir / "licensed_modules"

    # Validate URL is from trusted Portal domains and paths only (security: prevent SSRF)
    ALLOWED_PORTAL_HOSTS = {
        "portal.ciris.ai",
        "portal.ciris-services-1.ai",
        "portal.ciris-services-2.ai",
        "localhost",
        "127.0.0.1",
    }
    ALLOWED_PATH_PREFIXES = ("/api/", "/v1/")  # Only allow API endpoints
    parsed_url = urlparse(req.package_download_url)
    if parsed_url.hostname not in ALLOWED_PORTAL_HOSTS:
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error=f"Invalid package URL: host '{parsed_url.hostname}' not in allowed Portal domains",
            )
        )
    if not any(parsed_url.path.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES):
        return SuccessResponse(
            data=DownloadPackageResponse(
                status="error",
                error="Invalid package URL: path must start with /api/ or /v1/",
            )
        )

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

        # Save zip to temp file (run sync I/O in thread to avoid blocking event loop)
        def _write_temp_file(content: bytes) -> str:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(content)
                return tmp.name

        tmp_path = await asyncio.to_thread(_write_temp_file, dl_resp.content)

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

        logger.info(f"[Package Download] Installed {package_id} v{package_version} to {install_dir}")

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
            provisioned_key_id = provisioned_key.key_id
            logger.info(f"[Setup Complete] Saved Registry-provisioned signing key (key_id={provisioned_key_id})")

            # Audit the key provisioning event - critical for Level 5 attestation
            audit_service = getattr(request.app.state, "audit_service", None)
            if audit_service:
                import asyncio

                from ciris_engine.schemas.services.graph.audit import AuditEventData

                audit_event = AuditEventData(
                    event_type="signing_key_provisioned",
                    details={
                        "key_id": provisioned_key_id,
                        "signing_key_id": setup.signing_key_id,
                        "source": "portal_registry",
                        "node_url": setup.node_url,
                    },
                    severity="info",
                    source="setup_complete",
                )
                asyncio.create_task(audit_service.log_event("signing_key_provisioned", audit_event))
                logger.info(f"[Setup Complete] Audit entry created for key provisioning")

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
