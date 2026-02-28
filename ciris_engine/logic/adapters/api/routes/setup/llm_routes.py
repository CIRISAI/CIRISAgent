"""LLM model listing and validation endpoints for CIRIS setup.

This module provides endpoints for listing available models and
validating LLM configurations during setup.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status

from ciris_engine.schemas.api.responses import SuccessResponse

from .._common import RESPONSES_404_500, RESPONSES_500
from .dependencies import SetupOnlyDep
from .llm_validation import _list_models_for_provider, _validate_llm_connection
from .models import ListModelsResponse, LLMValidationRequest, LLMValidationResponse

logger = logging.getLogger(__name__)

router = APIRouter()


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


@router.post("/validate-llm", dependencies=[SetupOnlyDep])
async def validate_llm(config: LLMValidationRequest) -> SuccessResponse[LLMValidationResponse]:
    """Validate LLM configuration.

    Tests the provided LLM configuration by attempting a connection.
    This endpoint is always accessible without authentication during first-run.
    """
    validation_result = await _validate_llm_connection(config)
    return SuccessResponse(data=validation_result)


@router.post("/list-models", dependencies=[SetupOnlyDep])
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
