"""Setup module for CIRIS first-run and reconfiguration.

This module provides the setup wizard endpoints for initial configuration.

MIGRATION STATUS (Phase 2 Complete):
The monolithic setup.py (4987 lines) has been refactored significantly.

Extracted Modules (~2450 lines total):
- attestation.py: All /verify-status, /attestation-status, /app-attest/*,
  /play-integrity/* endpoints - delegates to auth service (~560 lines)
- models.py: Pydantic schemas for all setup endpoints (~430 lines)
- helpers.py: adapter/template/password helpers (~260 lines)
- llm_validation.py: LLM provider/model validation (~620 lines)
- device_auth.py: node connection session helpers (~420 lines)
- constants.py: shared constants (~20 lines)

Legacy file reduced from 4987 to 1612 lines (68% reduction).

Remaining in _setup_legacy.py (~1600 lines):
- Setup completion helpers and endpoint (/complete)
- Config endpoints (/config GET/PUT)
- Provider/template/adapter listing endpoints
- Device auth endpoint wrappers (use device_auth.py helpers)
- LLM model listing endpoint wrappers (use llm_validation.py)
"""

# Re-export the legacy router for backwards compatibility
# The legacy file was renamed from setup.py to _setup_legacy.py
from .._setup_legacy import _create_setup_users, _save_setup_config, router

# Device auth - imported from the new device_auth.py module
from .device_auth import (
    _activate_key_inline,
    _clear_device_auth_session,
    _get_device_auth_session_path,
    _load_device_auth_session,
    _save_device_auth_session,
    _submit_attestation_inline,
)

# Helpers - imported from the new helpers.py module
from .helpers import (
    _create_adapter_from_manifest,
    _get_agent_templates,
    _get_available_adapters,
    _is_setup_allowed_without_auth,
    _log_oauth_linking_skip,
    _should_skip_manifest,
    _validate_setup_passwords,
)

# LLM validation - imported from the new llm_validation.py module
from .llm_validation import (
    _annotate_models_with_capabilities,
    _build_fallback_response,
    _classify_llm_connection_error,
    _detect_ollama,
    _fetch_live_models,
    _get_llm_providers,
    _get_provider_base_url,
    _get_static_fallback_models,
    _list_models_for_provider,
    _sort_models,
    _validate_api_key_for_provider,
    _validate_llm_connection,
)

# Models - imported from the new models.py module
from .models import (
    AdapterConfig,
    AgentTemplate,
    AppAttestVerifyRequest,
    ChangePasswordRequest,
    ConnectNodeRequest,
    ConnectNodeResponse,
    ConnectNodeStatusResponse,
    CreateUserRequest,
    DownloadPackageRequest,
    DownloadPackageResponse,
    ListModelsResponse,
    LiveModelInfo,
    LLMProvider,
    LLMValidationRequest,
    LLMValidationResponse,
    PlayIntegrityVerifyRequest,
    SetupCompleteRequest,
    SetupConfigResponse,
    SetupStatusResponse,
    VerifyStatusResponse,
)

# Note: The attestation module is created but not yet wired in.
# To complete the migration:
# 1. Update _setup_legacy.py to remove attestation endpoints
# 2. Wire in attestation.router here
# 3. Repeat for other modules (llm_validation, device_auth, etc.)
# 4. Delete _setup_legacy.py when all modules are migrated

__all__ = [
    "router",
    # Legacy functions (still in _setup_legacy.py)
    "_save_setup_config",
    "_create_setup_users",
    # Models
    "AdapterConfig",
    "AgentTemplate",
    "AppAttestVerifyRequest",
    "ChangePasswordRequest",
    "ConnectNodeRequest",
    "ConnectNodeResponse",
    "ConnectNodeStatusResponse",
    "CreateUserRequest",
    "DownloadPackageRequest",
    "DownloadPackageResponse",
    "ListModelsResponse",
    "LiveModelInfo",
    "LLMProvider",
    "LLMValidationRequest",
    "LLMValidationResponse",
    "PlayIntegrityVerifyRequest",
    "SetupCompleteRequest",
    "SetupConfigResponse",
    "SetupStatusResponse",
    "VerifyStatusResponse",
    # Helper functions (for test compatibility)
    "_classify_llm_connection_error",
    "_create_adapter_from_manifest",
    "_get_agent_templates",
    "_get_available_adapters",
    "_get_llm_providers",
    "_is_setup_allowed_without_auth",
    "_log_oauth_linking_skip",
    "_should_skip_manifest",
    "_validate_api_key_for_provider",
    "_validate_llm_connection",
    "_validate_setup_passwords",
    "_detect_ollama",
    "_get_provider_base_url",
    "_annotate_models_with_capabilities",
    "_sort_models",
    "_get_static_fallback_models",
    "_build_fallback_response",
    "_list_models_for_provider",
    "_fetch_live_models",
    # Device auth helpers
    "_get_device_auth_session_path",
    "_load_device_auth_session",
    "_save_device_auth_session",
    "_clear_device_auth_session",
    "_submit_attestation_inline",
    "_activate_key_inline",
]
