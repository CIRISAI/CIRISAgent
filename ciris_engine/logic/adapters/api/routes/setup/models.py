"""Pydantic models for CIRIS setup module.

This module contains all request/response schemas used by the setup endpoints.
"""

import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from ciris_engine.config.model_capabilities import ModelCapabilities

# Constants used in model field descriptions
FIELD_DESC_DISPLAY_NAME = "Display name"


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
    missing_binaries: List[str] = Field(default_factory=list, description="Required binaries not found on system")
    binaries_available: bool = Field(True, description="Whether all required binaries are installed")
    supported_platforms: List[str] = Field(
        default_factory=list,
        description="Platforms supported - empty means all, otherwise ['android', 'ios', 'desktop']",
    )
    requires_ciris_services: bool = Field(False, description="Requires CIRIS AI services (Google sign-in)")
    # Interactive configuration (wizard) support
    requires_config: bool = Field(False, description="Whether this adapter needs interactive configuration (wizard)")
    config_fields: List[str] = Field(default_factory=list, description="Fields that can be configured via wizard")


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
    max_level: int = Field(default=0, description="Current attestation level achieved (0-5)")
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

    # v0.7.0: Enhanced verification details
    ed25519_fingerprint: Optional[str] = Field(default=None, description="Ed25519 public key fingerprint (SHA-256 hex)")
    key_storage_mode: Optional[str] = Field(
        default=None, description="Key storage mode: SOFTWARE, HARDWARE_BACKED, or specific provider"
    )
    hardware_backed: bool = Field(default=False, description="Whether the key is hardware-backed")
    target_triple: Optional[str] = Field(
        default=None, description="Target triple being checked against registry (e.g., aarch64-linux-android)"
    )
    binary_self_check: Optional[str] = Field(
        default=None, description="Binary self-check status: verified, mismatch, not_found, unavailable:{reason}"
    )
    binary_hash: Optional[str] = Field(default=None, description="Binary hash computed locally")
    expected_binary_hash: Optional[str] = Field(default=None, description="Expected binary hash from registry")
    function_self_check: Optional[str] = Field(
        default=None, description="Function self-check status: verified, mismatch, not_found, unavailable:{reason}"
    )
    functions_checked: Optional[int] = Field(default=None, description="Number of functions verified")
    functions_passed: Optional[int] = Field(default=None, description="Number of functions that passed verification")
    registry_key_status: Optional[str] = Field(default=None, description="Registry key verification status")

    # v0.8.1: Python integrity for mobile
    python_integrity_ok: bool = Field(default=False, description="Python module integrity verified")
    python_modules_checked: Optional[int] = Field(default=None, description="Number of Python modules checked")
    python_modules_passed: Optional[int] = Field(default=None, description="Number of Python modules that passed")
    python_total_hash: Optional[str] = Field(default=None, description="Total hash of all Python modules")
    python_hash_valid: bool = Field(default=False, description="Whether Python total hash matches expected")

    # v0.8.4: Enhanced detail lists for UI
    files_missing_count: Optional[int] = Field(default=None, description="Number of manifest files not on device")
    files_missing_list: Optional[List[str]] = Field(default=None, description="List of missing files (max 50)")
    files_failed_list: Optional[List[str]] = Field(
        default=None, description="List of files that failed hash check (max 50)"
    )
    files_unexpected_list: Optional[List[str]] = Field(default=None, description="List of unexpected files (max 50)")
    functions_failed_list: Optional[List[str]] = Field(
        default=None, description="List of functions that failed verification (max 50)"
    )
    # v0.8.6: Mobile exclusion tracking for correct denominator
    mobile_excluded_count: Optional[int] = Field(
        default=None, description="Files excluded from mobile (discord, reddit, cli, etc.)"
    )
    mobile_excluded_list: Optional[List[str]] = Field(
        default=None, description="List of mobile-excluded files (max 50)"
    )

    # v0.8.5: Registry sources agreement and attestation proof
    sources_agreeing: int = Field(default=0, description="Number of registry sources that agree (0-3)")
    attestation_proof: Optional[Dict[str, Any]] = Field(
        default=None, description="Full attestation proof from CIRISVerify"
    )

    # v0.8.6: Per-file results for deconflicted integrity display
    per_file_results: Optional[Dict[str, str]] = Field(
        default=None, description="Per-file status map (path → passed/failed/missing/unreadable)"
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


class DiscoveredLLMServer(BaseModel):
    """A discovered local LLM inference server."""

    id: str = Field(..., description="Unique server ID (ip_port format)")
    label: str = Field(..., description="Display label (e.g., 'jetson.local:8080 (Gemma 4)')")
    url: str = Field(..., description="Server URL (http://ip:port)")
    server_type: str = Field(..., description="Server type: ollama, llama_cpp, vllm, lmstudio, localai, openai_compatible")
    model_count: int = Field(default=0, description="Number of models available")
    models: List[str] = Field(default_factory=list, description="Model names available on server")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata (hostname, ip, port, source)")


class DiscoverLocalLLMRequest(BaseModel):
    """Request to discover local LLM servers."""

    timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0, description="Discovery timeout")
    include_localhost: bool = Field(default=True, description="Include localhost port scanning")


class DiscoverLocalLLMResponse(BaseModel):
    """Response from local LLM server discovery."""

    servers: List[DiscoveredLLMServer] = Field(default_factory=list, description="Discovered servers")
    total_count: int = Field(default=0, description="Total servers found")
    discovery_methods: List[str] = Field(default_factory=list, description="Methods used (hostname_probe, localhost_scan)")
    error: Optional[str] = Field(None, description="Error message if discovery partially failed")


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
    admin_username: str = Field(default="owner", description="New user's username")
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

    # User Preferences (language & location at user-selected granularity)
    preferred_language: Optional[str] = Field(
        None, description="ISO 639-1 language code (e.g., 'en', 'am', 'es', 'fr')"
    )
    location_country: Optional[str] = Field(
        None, description="ISO 3166-1 alpha-2 country code (e.g., 'US', 'ET', 'JP')"
    )
    location_region: Optional[str] = Field(
        None, description="Region/state/province name (user-chosen granularity, may be omitted)"
    )
    location_city: Optional[str] = Field(None, description="City name (user-chosen granularity, may be omitted)")
    location_latitude: Optional[float] = Field(
        None, ge=-90.0, le=90.0, description="Latitude in decimal degrees (ISO 6709)"
    )
    location_longitude: Optional[float] = Field(
        None, ge=-180.0, le=180.0, description="Longitude in decimal degrees (ISO 6709)"
    )
    timezone: Optional[str] = Field(None, description="IANA timezone (e.g., 'America/Chicago', 'Africa/Addis_Ababa')")
    share_location_in_traces: bool = Field(
        default=False,
        description="Whether user consents to include location data in anonymized telemetry traces",
    )

    # Node Connection (set by "Connect to Node" device auth flow)
    node_url: Optional[str] = Field(None, description="CIRISNode URL (e.g., https://node.ciris.ai)")
    identity_template: Optional[str] = Field(None, description="Registry-provisioned identity template ID")
    stewardship_tier: Optional[int] = Field(None, ge=1, le=5, description="Stewardship tier from provisioned template")
    approved_adapters: Optional[List[str]] = Field(None, description="Registry-approved adapter list")
    org_id: Optional[str] = Field(None, description="Organization ID from Portal ABAC resolution")

    # DEPRECATED (FSD-002 Self-Custody): These fields are no longer used.
    # Agents now generate their own keys and register the PUBLIC key with Portal.
    # Portal NEVER sends or receives private keys.
    signing_key_provisioned: bool = Field(
        default=False,
        description="DEPRECATED: Always False. Self-custody agents generate their own keys.",
        deprecated=True,
    )
    provisioned_signing_key_b64: Optional[str] = Field(
        None,
        description="DEPRECATED: Always None. Portal never sends private keys (FSD-002 self-custody).",
        deprecated=True,
    )

    # Self-custody key ID from Portal registration
    signing_key_id: Optional[str] = Field(
        None,
        description="Portal key ID (from self-custody registration). Private key stays in agent TPM.",
    )

    # Licensed module package (set by download-package flow)
    licensed_package_path: Optional[str] = Field(None, description="Path to installed licensed module package")
    licensed_modules_path: Optional[str] = Field(None, description="Path to licensed modules directory within package")

    # CIRISVerify (optional, set by node flow)
    verify_binary_path: Optional[str] = Field(None, description="Path to CIRISVerify binary")
    verify_require_hardware: bool = Field(default=False, description="Require hardware attestation for CIRISVerify")

    @field_validator("admin_username")
    @classmethod
    def validate_admin_username(cls, v: str) -> str:
        """Block 'admin' username in production - reserved for testing only."""
        if v.lower() == "admin":
            testing_mode = os.environ.get("CIRIS_TESTING_MODE", "").lower() in ("true", "1", "yes")
            if not testing_mode:
                raise ValueError(
                    "Username 'admin' is reserved for testing. Please choose a different username."
                )
        return v


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

    # User Location (from setup)
    location_country: Optional[str] = Field(None, description="User's country")
    location_region: Optional[str] = Field(None, description="User's region/state")
    location_city: Optional[str] = Field(None, description="User's city")
    location_latitude: Optional[float] = Field(None, description="Latitude in decimal degrees")
    location_longitude: Optional[float] = Field(None, description="Longitude in decimal degrees")
    timezone: Optional[str] = Field(None, description="IANA timezone")
    has_coordinates: bool = Field(False, description="Whether lat/long are available")


class CreateUserRequest(BaseModel):
    """Request to create initial admin user."""

    username: str = Field(..., description="Admin username")
    password: str = Field(..., description="Admin password (min 8 characters)")


class ChangePasswordRequest(BaseModel):
    """Request to change admin password."""

    old_password: str = Field(..., description="Current password")
    new_password: str = Field(..., description="New password (min 8 characters)")


# App Attest / Play Integrity request models
class AppAttestVerifyRequest(BaseModel):
    """Request body for App Attest verification."""

    attestation: str = Field(..., description="Base64-encoded CBOR attestation from DCAppAttestService")
    key_id: str = Field(..., description="Key ID from DCAppAttestService.generateKey()")
    nonce: str = Field(..., description="Nonce used when requesting the attestation")


class PlayIntegrityVerifyRequest(BaseModel):
    """Request body for Play Integrity verification."""

    token: str = Field(..., description="Play Integrity token from Google Play API")
    nonce: str = Field(..., description="Nonce used when requesting the token")


# Device Auth / Node Connection models
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
    """Response from device auth status polling.

    NOTE (FSD-002 Self-Custody): Portal no longer sends private keys.
    The agent generates its own Ed25519 keypair and registers the PUBLIC key with Portal.
    The `signing_key_b64` field is DEPRECATED and always None.
    """

    status: str = Field(..., description="pending, complete, or error")
    # Fields below are only set when status == 'complete'
    template: Optional[str] = Field(None, description="Provisioned identity template ID")
    adapters: Optional[List[str]] = Field(None, description="Approved adapter list")
    org_id: Optional[str] = Field(None, description="Organization ID")
    signing_key_b64: Optional[str] = Field(
        None,
        description="DEPRECATED: Always None. Portal never sends private keys (FSD-002 self-custody).",
        deprecated=True,
    )
    key_id: Optional[str] = Field(None, description="Key ID from self-custody registration")
    stewardship_tier: Optional[int] = Field(None, description="Stewardship tier from template")
    # Licensed package info — agent downloads this after provisioning
    package_download_url: Optional[str] = Field(None, description="URL to download licensed module package zip")
    package_template_id: Optional[str] = Field(None, description="Template ID within the licensed package")


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
