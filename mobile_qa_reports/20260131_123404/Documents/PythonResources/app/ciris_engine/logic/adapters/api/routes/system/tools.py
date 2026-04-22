"""
Tools endpoint.

Provides information about available tools from all tool providers.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request

from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

from ...dependencies.auth import AuthContext, require_observer
from .schemas import ToolInfoResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _tool_info_to_response(info: Any, provider_name: str) -> ToolInfoResponse:
    """Convert a ToolInfo object to ToolInfoResponse."""
    return ToolInfoResponse(
        name=info.name,
        description=info.description,
        provider=provider_name,
        parameters=getattr(info, "parameters", None),
        category=getattr(info, "category", "general"),
        cost=getattr(info, "cost", 0.0),
        when_to_use=getattr(info, "when_to_use", None),
    )


def _legacy_tool_to_response(name: str, provider_name: str) -> ToolInfoResponse:
    """Convert a legacy tool name to ToolInfoResponse."""
    return ToolInfoResponse(
        name=name,
        description=f"{name} tool",
        provider=provider_name,
        parameters=None,
        category="general",
        cost=0.0,
        when_to_use=None,
    )


async def _collect_tools_from_provider(provider: Any, provider_name: str) -> List[ToolInfoResponse]:
    """Collect tools from a single provider using modern or legacy interface."""
    tools: List[ToolInfoResponse] = []
    if hasattr(provider, "get_all_tool_info"):
        tool_infos = await provider.get_all_tool_info()
        tools = [_tool_info_to_response(info, provider_name) for info in tool_infos]
    elif hasattr(provider, "list_tools"):
        tool_names = await provider.list_tools()
        tools = [_legacy_tool_to_response(name, provider_name) for name in tool_names]
    return tools


async def _collect_all_tools(service_registry: Any) -> Tuple[List[ToolInfoResponse], Set[str]]:
    """Collect tools from all providers in the service registry."""
    all_tools: List[ToolInfoResponse] = []
    tool_providers: Set[str] = set()

    if not hasattr(service_registry, "_services"):
        return all_tools, tool_providers
    if ServiceType.TOOL not in service_registry._services:
        return all_tools, tool_providers

    for provider_data in service_registry._services[ServiceType.TOOL]:
        provider = provider_data.instance
        provider_name = provider.__class__.__name__
        tool_providers.add(provider_name)
        try:
            tools = await _collect_tools_from_provider(provider, provider_name)
            all_tools.extend(tools)
        except Exception as e:
            logger.warning(f"Failed to get tools from provider {provider_name}: {e}", exc_info=True)

    return all_tools, tool_providers


def _deduplicate_tools(all_tools: List[ToolInfoResponse]) -> List[ToolInfoResponse]:
    """Deduplicate tools by name, merging provider info for duplicates."""
    seen_tools: Dict[str, ToolInfoResponse] = {}
    unique_tools: List[ToolInfoResponse] = []

    for tool in all_tools:
        if tool.name not in seen_tools:
            seen_tools[tool.name] = tool
            unique_tools.append(tool)
        elif seen_tools[tool.name].provider != tool.provider:
            seen_tools[tool.name].provider = f"{seen_tools[tool.name].provider}, {tool.provider}"

    return unique_tools


def _build_tools_response(unique_tools: List[ToolInfoResponse], tool_providers: Set[str]) -> JSONDict:
    """Build the final response with tools and metadata."""
    return {
        "data": [tool.model_dump() for tool in unique_tools],
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": None,
            "duration_ms": None,
            "providers": list(tool_providers),
            "provider_count": len(tool_providers),
            "total_tools": len(unique_tools),
        },
    }


@router.get("/tools")
async def get_available_tools(request: Request, auth: AuthContext = Depends(require_observer)) -> JSONDict:
    """
    Get list of all available tools from all tool providers.

    Returns tools from:
    - Core tool services (secrets, self_help)
    - Adapter tool services (API, Discord, etc.)

    Requires OBSERVER role.
    """
    try:
        service_registry = getattr(request.app.state, "service_registry", None)
        if not service_registry:
            return _build_tools_response([], set())

        all_tools, tool_providers = await _collect_all_tools(service_registry)
        unique_tools = _deduplicate_tools(all_tools)

        logger.info(f"Tool providers found: {len(tool_providers)} unique providers: {tool_providers}")
        logger.info(f"Total tools collected: {len(all_tools)}, Unique tools: {len(unique_tools)}")

        return _build_tools_response(unique_tools, tool_providers)

    except Exception as e:
        logger.error(f"Error getting available tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))
