"""LLM model listing and validation endpoints for CIRIS setup.

This module provides endpoints for listing available models and
validating LLM configurations during setup AND post-setup settings.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ciris_engine.schemas.api.responses import SuccessResponse

from .._common import RESPONSES_404_500, RESPONSES_500
from .dependencies import SetupOnlyDep
from .helpers import _is_setup_allowed_without_auth
from .llm_validation import _list_models_for_provider, _validate_llm_connection
from .models import (
    DiscoveredLLMServer,
    DiscoverLocalLLMRequest,
    DiscoverLocalLLMResponse,
    ListModelsResponse,
    LLMValidationRequest,
    LLMValidationResponse,
    StartLocalServerRequest,
    StartLocalServerResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _require_setup_or_auth(request: Request) -> None:
    """Allow access during first-run OR with valid authentication.

    This enables the LLM validation/listing endpoints to work both:
    1. During setup (no auth required)
    2. From Settings screen (auth required)
    """
    if _is_setup_allowed_without_auth():
        # First-run - no auth needed
        return

    # Post-setup - require authentication
    from ...dependencies.auth import get_auth_context, get_auth_service

    authorization = request.headers.get("Authorization")
    auth_service = get_auth_service(request)
    auth = await get_auth_context(request, authorization, auth_service)
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for LLM configuration after setup",
        )


async def _require_setup_or_admin(request: Request) -> None:
    """Allow access during first-run OR with admin authentication post-setup.

    Used for endpoints that perform privileged side effects (e.g. spawning
    a local inference server subprocess). During setup the wizard runs
    without auth, but once setup is complete we require ADMIN role — regular
    observers must not be able to trigger background process launches.
    """
    if _is_setup_allowed_without_auth():
        # First-run - no auth needed (wizard operates pre-account)
        return

    from ciris_engine.schemas.api.auth import UserRole

    from ...dependencies.auth import get_auth_context, get_auth_service

    authorization = request.headers.get("Authorization")
    auth_service = get_auth_service(request)
    auth = await get_auth_context(request, authorization, auth_service)
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to start local LLM server",
        )
    if not auth.role.has_permission(UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to start local LLM server",
        )


SetupOrAuthDep = Depends(_require_setup_or_auth)
SetupOrAdminDep = Depends(_require_setup_or_admin)


@router.get("/models", responses=RESPONSES_500, dependencies=[SetupOnlyDep])
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


@router.get("/models/{provider_id}", responses=RESPONSES_404_500, dependencies=[SetupOnlyDep])
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


@router.post("/validate-llm", dependencies=[SetupOrAuthDep])
async def validate_llm(config: LLMValidationRequest) -> SuccessResponse[LLMValidationResponse]:
    """Validate LLM configuration.

    Tests the provided LLM configuration by attempting a connection.
    Accessible without auth during first-run, or with auth after setup.
    """
    validation_result = await _validate_llm_connection(config)
    return SuccessResponse(data=validation_result)


@router.post("/list-models", dependencies=[SetupOrAuthDep])
async def list_models(config: LLMValidationRequest) -> SuccessResponse[ListModelsResponse]:
    """List available models from a provider's live API.

    Queries the provider's models API using the provided credentials,
    then cross-references with the on-device MODEL_CAPABILITIES.json
    for CIRIS compatibility annotations.

    Falls back to static capabilities data if the live query fails.
    Accessible without auth during first-run, or with auth after setup.
    """
    result = await _list_models_for_provider(config)
    return SuccessResponse(data=result)


@router.post("/discover-local-llm", dependencies=[SetupOrAuthDep])
async def discover_local_llm(
    request: DiscoverLocalLLMRequest = DiscoverLocalLLMRequest(),
) -> SuccessResponse[DiscoverLocalLLMResponse]:
    """Discover local LLM inference servers on the network.

    Uses hostname probing and localhost port scanning to find running
    LLM servers (Ollama, llama.cpp, vLLM, LM Studio, LocalAI).

    Probes common hostnames:
    - jetson.local (NVIDIA Jetson with Ollama/llama.cpp)
    - ollama.local, llm.local, inference.local, lmstudio.local, vllm.local

    Probes localhost ports:
    - 11434 (Ollama), 1234 (LM Studio), 8000 (vLLM), 8080 (llama.cpp/LocalAI)

    Returns discovered servers with model counts and names.
    Accessible without auth during first-run, or with auth after setup.
    """
    from .llm_discovery import discover_local_llm_servers

    try:
        servers_data, methods = await discover_local_llm_servers(
            timeout_seconds=request.timeout_seconds,
            include_localhost=request.include_localhost,
        )

        # Convert to Pydantic models
        servers = [DiscoveredLLMServer(**s) for s in servers_data]

        return SuccessResponse(
            data=DiscoverLocalLLMResponse(
                servers=servers,
                total_count=len(servers),
                discovery_methods=methods,
            )
        )
    except Exception as e:
        logger.error(f"[DISCOVER_LOCAL_LLM] Discovery failed: {e}")
        return SuccessResponse(
            data=DiscoverLocalLLMResponse(
                servers=[],
                total_count=0,
                discovery_methods=[],
                error=str(e),
            )
        )


@router.post("/start-local-server", dependencies=[SetupOrAdminDep])
async def start_local_server(
    request: StartLocalServerRequest = StartLocalServerRequest(),
) -> SuccessResponse[StartLocalServerResponse]:
    """Start a local LLM inference server.

    Used when the device is capable of running local inference but no server
    is currently detected. Starts llama.cpp or Ollama in the background.

    This operation may take 30-90 seconds as the model loads into memory.
    The server runs with a keepalive and will stay running until shutdown.

    After starting, call /discover-local-llm to find the running server.

    Accessible without auth during first-run, or with ADMIN role after
    setup — spawning a background subprocess is privileged and must not be
    exposed to plain observer accounts.
    """
    from .llm_discovery import start_local_llm_server

    try:
        result = await start_local_llm_server(
            server_type=request.server_type,
            model=request.model,
            port=request.port,
            confirm_download=request.confirm_download,
        )

        return SuccessResponse(
            data=StartLocalServerResponse(
                success=result.get("success", False),
                server_url=result.get("server_url"),
                server_type=request.server_type,
                model=request.model,
                pid=result.get("pid"),
                message=result.get("message", "Unknown status"),
                estimated_ready_seconds=result.get("estimated_ready_seconds") or 60,
                requires_download=result.get("requires_download", False),
                download_size=result.get("download_size"),
            )
        )
    except Exception as e:
        logger.error(f"[START_LOCAL_SERVER] Failed to start server: {e}")
        return SuccessResponse(
            data=StartLocalServerResponse(
                success=False,
                server_url=None,
                server_type=request.server_type,
                model=request.model,
                pid=None,
                message=f"Failed to start server: {str(e)}",
                estimated_ready_seconds=0,
                requires_download=False,
                download_size=None,
            )
        )
