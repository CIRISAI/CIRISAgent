"""
Tools endpoint.

Provides information about available tools from all tool providers.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

from ...dependencies.auth import AuthContext, require_observer
from .schemas import ToolInfoResponse

logger = logging.getLogger(__name__)

router = APIRouter()


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
        all_tools = []
        tool_providers = set()  # Use set to avoid counting duplicates

        # Get all tool providers from the service registry
        service_registry = getattr(request.app.state, "service_registry", None)
        if service_registry:
            # Get provider info for TOOL services
            provider_info = service_registry.get_provider_info(service_type=ServiceType.TOOL.value)
            provider_info.get("services", {}).get(ServiceType.TOOL.value, [])

            # Get the actual provider instances from the registry
            if hasattr(service_registry, "_services") and ServiceType.TOOL in service_registry._services:
                for provider_data in service_registry._services[ServiceType.TOOL]:
                    try:
                        provider = provider_data.instance
                        provider_name = provider.__class__.__name__
                        tool_providers.add(provider_name)  # Use add to avoid duplicates

                        if hasattr(provider, "get_all_tool_info"):
                            # Modern interface with ToolInfo objects
                            tool_infos = await provider.get_all_tool_info()
                            for info in tool_infos:
                                all_tools.append(
                                    ToolInfoResponse(
                                        name=info.name,
                                        description=info.description,
                                        provider=provider_name,
                                        parameters=info.parameters if hasattr(info, "parameters") else None,
                                        category=getattr(info, "category", "general"),
                                        cost=getattr(info, "cost", 0.0),
                                        when_to_use=getattr(info, "when_to_use", None),
                                    )
                                )
                        elif hasattr(provider, "list_tools"):
                            # Legacy interface
                            tool_names = await provider.list_tools()
                            for name in tool_names:
                                all_tools.append(
                                    ToolInfoResponse(
                                        name=name,
                                        description=f"{name} tool",
                                        provider=provider_name,
                                        parameters=None,
                                        category="general",
                                        cost=0.0,
                                        when_to_use=None,
                                    )
                                )
                    except Exception as e:
                        logger.warning(f"Failed to get tools from provider {provider_name}: {e}", exc_info=True)

        # Deduplicate tools by name (in case multiple providers offer the same tool)
        seen_tools = {}
        unique_tools = []
        for tool in all_tools:
            if tool.name not in seen_tools:
                seen_tools[tool.name] = tool
                unique_tools.append(tool)
            else:
                # If we see the same tool from multiple providers, add provider info
                existing = seen_tools[tool.name]
                if existing.provider != tool.provider:
                    existing.provider = f"{existing.provider}, {tool.provider}"

        # Log provider information for debugging
        logger.info(f"Tool providers found: {len(tool_providers)} unique providers: {tool_providers}")
        logger.info(f"Total tools collected: {len(all_tools)}, Unique tools: {len(unique_tools)}")
        logger.info(f"Tool provider summary: {list(tool_providers)}")

        # Create response with additional metadata for tool providers
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

    except Exception as e:
        logger.error(f"Error getting available tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))
