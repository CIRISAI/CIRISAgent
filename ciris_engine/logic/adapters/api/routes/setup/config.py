"""Configuration endpoints for CIRIS setup.

This module provides endpoints for reading and updating agent configuration.
"""

import logging
import os
from typing import Dict

from fastapi import APIRouter, HTTPException, Request, status

from ciris_engine.schemas.api.responses import SuccessResponse

from .._common import RESPONSES_401_500, RESPONSES_403, RESPONSES_500, AuthAdminDep
from .helpers import _is_setup_allowed_without_auth
from .models import SetupCompleteRequest, SetupConfigResponse

logger = logging.getLogger(__name__)


def _detect_llm_provider(request: Request) -> str:
    """Detect the active LLM provider for display in the UI.

    Checks mock LLM first, then explicit env vars, then auto-detects
    from API keys. Mirrors _detect_provider_from_env() in llm_service.
    """
    # Mock LLM check (runtime flag or env var)
    runtime = getattr(request.app.state, "runtime", None)
    if runtime and hasattr(runtime, "modules_to_load") and "mock_llm" in runtime.modules_to_load:
        return "mockllm"
    if os.getenv("CIRIS_MOCK_LLM", "").lower() in ("true", "1", "yes", "on"):
        return "mockllm"

    # Explicit provider setting (CIRIS_LLM_PROVIDER or LLM_PROVIDER)
    provider_env = (os.getenv("CIRIS_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "").lower()
    if provider_env:
        if provider_env in ("anthropic", "claude"):
            return "anthropic"
        elif provider_env in ("google", "gemini"):
            return "google"
        elif provider_env == "openai":
            return "openai"
        elif provider_env == "openrouter":
            return "openrouter"
        elif provider_env == "groq":
            return "groq"
        elif provider_env == "together":
            return "together"
        elif provider_env in ("openai_compatible",):
            return "other"
        return provider_env  # Pass through unknown providers

    # Auto-detect from API keys
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        return "google"

    # Check base URL for known providers
    base_url = os.getenv("OPENAI_API_BASE", "")
    if base_url:
        if "openrouter.ai" in base_url:
            return "openrouter"
        elif "groq.com" in base_url:
            return "groq"
        elif "together.xyz" in base_url or "together.ai" in base_url:
            return "together"
        elif "mistral.ai" in base_url:
            return "mistral"
        elif "deepseek.com" in base_url:
            return "deepseek"
        elif "cohere" in base_url:
            return "cohere"
        elif "localhost" in base_url or "127.0.0.1" in base_url:
            return "local"
        return "other"

    # CIRIS Proxy detection
    if os.getenv("CIRIS_PROXY_URL") or os.getenv("CIRIS_PROXY_ENABLED", "").lower() in ("true", "1"):
        return "ciris_proxy"

    return "openai"


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

    config = SetupConfigResponse(
        llm_provider=llm_provider,
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
