"""Setup module for CIRIS first-run and reconfiguration.

This module provides the setup wizard endpoints for initial configuration.

MIGRATION STATUS (Phase 3 Complete - Full Modularization):
The monolithic setup.py (4987 lines) has been fully refactored into modules.

Modules:
- status.py: /status endpoint (~35 lines)
- providers.py: /providers, /templates, /adapters endpoints (~70 lines)
- llm_routes.py: /models, /validate-llm, /list-models endpoints (~130 lines)
- device_auth_routes.py: /connect-node, /download-package endpoints (~350 lines)
- config.py: /config GET/PUT endpoints (~90 lines)
- complete.py: /complete endpoint and user creation helpers (~450 lines)
- attestation.py: Verification endpoints delegating to auth service (~560 lines)
- models.py: Pydantic schemas for all setup endpoints (~430 lines)
- helpers.py: Adapter/template/password helpers (~260 lines)
- llm_validation.py: LLM provider/model validation (~620 lines)
- device_auth.py: Node connection session helpers (~420 lines)
- dependencies.py: Shared FastAPI dependencies (~25 lines)
- constants.py: Shared constants (~20 lines)

The legacy _setup_legacy.py file has been deleted.
"""

from fastapi import APIRouter

# Import sub-routers
from . import attestation, complete, config, device_auth_routes, llm_routes, providers, status

# Complete helpers - imported from complete.py module
from .complete import _create_founding_partnership, _create_setup_users, _save_setup_config

# Device auth helpers - imported from device_auth.py module
from .device_auth import (
    _activate_key_inline,
    _clear_device_auth_session,
    _get_device_auth_session_path,
    _load_device_auth_session,
    _save_device_auth_session,
    _submit_attestation_inline,
)

# Helpers - imported from helpers.py module
from .helpers import (
    _create_adapter_from_manifest,
    _get_agent_templates,
    _get_available_adapters,
    _is_setup_allowed_without_auth,
    _log_oauth_linking_skip,
    _should_skip_manifest,
    _validate_setup_passwords,
)

# LLM validation - imported from llm_validation.py module
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

# Models - imported from models.py module
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

# Create the main router and include all sub-routers
router = APIRouter(prefix="/setup", tags=["setup"])

# Include all sub-routers
router.include_router(status.router)
router.include_router(providers.router)
router.include_router(llm_routes.router)
router.include_router(device_auth_routes.router)
router.include_router(config.router)
router.include_router(complete.router)
router.include_router(attestation.router, tags=["attestation"])

__all__ = [
    "router",
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
    # Complete helpers (for test compatibility)
    "_save_setup_config",
    "_create_setup_users",
    "_create_founding_partnership",
]
