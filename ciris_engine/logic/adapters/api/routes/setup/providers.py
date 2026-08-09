"""Provider, template, and adapter listing endpoints for CIRIS setup.

This module provides endpoints to list available LLM providers,
agent templates, and adapters during setup.
"""

import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from ciris_engine.schemas.adapters.tools import ToolDisclosureReport
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.consent.disclosure import ConsentDisclosure

from .dependencies import SetupOnlyDep
from .helpers import _get_agent_templates, _get_available_adapters
from .llm_validation import _get_llm_providers
from .models import AdapterConfig, AgentTemplate, LLMProvider

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/providers", dependencies=[SetupOnlyDep])
async def list_providers() -> SuccessResponse[List[LLMProvider]]:
    """List available LLM providers.

    Returns configuration templates for supported LLM providers.
    This endpoint is always accessible without authentication.
    """
    providers = _get_llm_providers()
    return SuccessResponse(data=providers)


@router.get("/templates", dependencies=[SetupOnlyDep])
async def list_templates() -> SuccessResponse[List[AgentTemplate]]:
    """List available agent templates.

    Returns pre-configured agent identity templates.
    This endpoint is always accessible without authentication.
    """
    templates = _get_agent_templates()
    return SuccessResponse(data=templates)


@router.get("/adapters", dependencies=[SetupOnlyDep])
async def list_adapters() -> SuccessResponse[List[AdapterConfig]]:
    """List available adapters with platform requirements.

    Returns ALL adapters with their requirements metadata.
    KMP clients filter locally based on platform capabilities (iOS, Android, desktop).
    This endpoint is always accessible without authentication.
    """
    adapters = _get_available_adapters()
    return SuccessResponse(data=adapters)


@router.get("/tool-disclosure", dependencies=[SetupOnlyDep])
async def list_tool_disclosure(include_discovered: bool = True) -> SuccessResponse[ToolDisclosureReport]:
    """Disclose every tool each setup choice grants, generated from the live tool services.

    The wizard's optional-features step defaults to enabled and discloses at
    adapter granularity. Informed consent needs the rest: what each adapter
    actually grants the agent, including the tools that no choice controls and
    that therefore cannot be declined.

    Nothing here restricts anything -- wide tool access is intended. This is
    disclosure only. The list is read from each tool service's own
    ``get_all_tool_info()`` so it cannot drift from the implementation.
    This endpoint is always accessible without authentication during setup.
    """
    from ciris_engine.logic.services.tool.tool_disclosure import build_tool_disclosure

    try:
        report = await build_tool_disclosure(include_discovered=include_discovered)
        return SuccessResponse(data=report)
    except Exception as e:
        logger.error(f"Error building tool disclosure: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/consent-disclosure", dependencies=[SetupOnlyDep])
async def get_consent_disclosure() -> SuccessResponse[ConsentDisclosure]:
    """The substrate's OWN consent copy, for the wizard to render verbatim.

    ``ciris_server.consent_disclosure()`` exists so the wizard does not compose
    this paragraph itself: a wizard that writes its own version drifts from the
    substrate the moment either changes. Every string arrives with a stable id
    into the 29-locale catalogue, so the client renders the localized text and
    falls back to the substrate's wording.

    This carries no owner data and gates nothing — it is the disclosure that
    makes the consent informed, so it is available without authentication during
    setup, like the other disclosure endpoints here.
    """
    import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

    try:
        raw = ciris_server.consent_disclosure()
        payload = json.loads(raw) if isinstance(raw, str) else raw
        return SuccessResponse(data=ConsentDisclosure.model_validate(payload))
    except Exception as e:
        # Fail LOUD. Rendering a hand-written substitute is precisely the drift
        # the export exists to prevent, so the screen must show an error rather
        # than invent the words.
        logger.error(f"Error reading substrate consent disclosure: {e}")
        raise HTTPException(status_code=503, detail=f"consent disclosure unavailable: {e}")


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
