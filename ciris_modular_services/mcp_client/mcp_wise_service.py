"""
MCP Wise Authority Service.

Provides guidance and wisdom capabilities through MCP server prompts.
Integrates with the WiseBus for the CIRIS agent.

MCP prompts can be used as wisdom sources for:
- Ethical guidance
- Decision making
- Deferral handling
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.authority_core import (
    DeferralRequest,
    GuidanceRequest,
    GuidanceResponse,
    WisdomAdvice,
)
from ciris_engine.schemas.services.context import DeferralContext, GuidanceContext
from ciris_engine.schemas.types import JSONDict

from .config import MCPServerConfig
from .security import MCPSecurityManager

logger = logging.getLogger(__name__)


class MCPWiseService:
    """
    Wise Authority service that uses MCP prompts for guidance.

    This service:
    - Discovers prompts from MCP servers
    - Uses prompts for guidance responses
    - Handles deferral forwarding
    - Provides telemetry and metrics
    """

    def __init__(
        self,
        security_manager: MCPSecurityManager,
        time_service: Optional[TimeServiceProtocol] = None,
    ) -> None:
        """Initialize MCP wise authority service.

        Args:
            security_manager: Security manager for validation
            time_service: Time service for timestamps
        """
        self._security_manager = security_manager
        self._time_service = time_service
        self._running = False
        self._start_time: Optional[datetime] = None

        # MCP clients per server
        self._mcp_clients: Dict[str, Any] = {}

        # Cached prompt information
        self._prompts_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}  # server_id -> {prompt_name -> prompt_info}

        # Metrics
        self._guidance_requests = 0
        self._deferrals_sent = 0
        self._errors = 0

    def register_mcp_client(self, server_id: str, client: Any) -> None:
        """Register an MCP client for a server.

        Args:
            server_id: Server identifier
            client: MCP client instance
        """
        self._mcp_clients[server_id] = client
        logger.info(f"Registered MCP wise client for server '{server_id}'")

    def unregister_mcp_client(self, server_id: str) -> None:
        """Unregister an MCP client.

        Args:
            server_id: Server to unregister
        """
        if server_id in self._mcp_clients:
            del self._mcp_clients[server_id]
            logger.info(f"Unregistered MCP wise client for server '{server_id}'")
        if server_id in self._prompts_cache:
            del self._prompts_cache[server_id]

    async def start(self) -> None:
        """Start the wise authority service."""
        self._running = True
        self._start_time = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        logger.info("MCPWiseService started")

    async def stop(self) -> None:
        """Stop the wise authority service."""
        self._running = False
        self._prompts_cache.clear()
        logger.info("MCPWiseService stopped")

    async def is_healthy(self) -> bool:
        """Check if the wise service is healthy."""
        return self._running

    def get_capabilities(self) -> Any:
        """Get service capabilities for registration."""
        from ciris_engine.schemas.services.capabilities import ServiceCapabilities

        return ServiceCapabilities(
            service_type=ServiceType.WISE_AUTHORITY,
            actions=[
                "fetch_guidance",
                "send_deferral",
                "get_guidance",
            ],
        )

    async def _refresh_prompts_cache(self, server_id: str) -> None:
        """Refresh the prompts cache for a server.

        Args:
            server_id: Server to refresh prompts for
        """
        client = self._mcp_clients.get(server_id)
        if not client:
            return

        try:
            # Call MCP list_prompts
            if hasattr(client, "list_prompts"):
                response = await client.list_prompts()
                prompts = response.prompts if hasattr(response, "prompts") else []

                self._prompts_cache[server_id] = {}

                for prompt in prompts:
                    name = prompt.name if hasattr(prompt, "name") else str(prompt.get("name", ""))
                    description = (
                        prompt.description if hasattr(prompt, "description") else str(prompt.get("description", ""))
                    )
                    arguments = prompt.arguments if hasattr(prompt, "arguments") else prompt.get("arguments", [])

                    # Security check for poisoning in description
                    allowed, violation = await self._security_manager.check_tool_access(server_id, name, description)

                    if not allowed:
                        logger.warning(f"Prompt '{name}' from server '{server_id}' blocked by security")
                        continue

                    self._prompts_cache[server_id][name] = {
                        "name": name,
                        "description": description,
                        "arguments": arguments,
                    }

                logger.debug(
                    f"Refreshed prompts cache for '{server_id}': "
                    f"{len(self._prompts_cache[server_id])} prompts available"
                )

        except Exception as e:
            logger.error(f"Failed to refresh prompts for server '{server_id}': {e}")

    async def fetch_guidance(self, context: GuidanceContext) -> Optional[str]:
        """Fetch guidance from MCP prompts.

        Args:
            context: Guidance context with question and considerations

        Returns:
            Guidance string or None
        """
        self._guidance_requests += 1

        # Try each MCP server that has prompts
        for server_id in self._mcp_clients:
            if server_id not in self._prompts_cache:
                await self._refresh_prompts_cache(server_id)

            prompts = self._prompts_cache.get(server_id, {})
            if not prompts:
                continue

            # Find a suitable prompt for guidance
            # Look for prompts related to guidance, ethics, or decision making
            guidance_prompts = [
                p
                for p in prompts.values()
                if any(kw in p["description"].lower() for kw in ["guidance", "ethic", "decision", "wisdom", "advice"])
            ]

            if not guidance_prompts:
                # Use any available prompt as fallback
                guidance_prompts = list(prompts.values())[:1]

            if not guidance_prompts:
                continue

            # Use the first matching prompt
            prompt = guidance_prompts[0]

            try:
                client = self._mcp_clients[server_id]

                # Build prompt arguments
                arguments = {}
                for arg in prompt.get("arguments", []):
                    arg_name = arg.get("name", "") if isinstance(arg, dict) else getattr(arg, "name", "")
                    if arg_name == "question":
                        arguments["question"] = context.question
                    elif arg_name == "context":
                        arguments["context"] = str(context.domain_context)
                    elif arg_name == "considerations":
                        arguments["considerations"] = str(context.ethical_considerations)

                # Get prompt response
                if hasattr(client, "get_prompt"):
                    response = await client.get_prompt(prompt["name"], arguments)

                    # Extract text from response
                    if hasattr(response, "messages"):
                        messages = response.messages
                        if messages and len(messages) > 0:
                            msg = messages[0]
                            if hasattr(msg, "content"):
                                content = msg.content
                                if hasattr(content, "text"):
                                    return content.text
                                return str(content)
                            return str(msg)
                    elif hasattr(response, "text"):
                        return response.text

                    return str(response)

            except Exception as e:
                self._errors += 1
                logger.error(f"Failed to get guidance from MCP server '{server_id}': {e}")
                continue

        return None

    async def get_guidance(self, request: GuidanceRequest) -> GuidanceResponse:
        """Get guidance for a request.

        Args:
            request: Guidance request with context and options

        Returns:
            GuidanceResponse with advice
        """
        # Convert to context
        context = GuidanceContext(
            thought_id=f"guidance_{id(request)}",
            task_id=f"task_{id(request)}",
            question=request.context,
            ethical_considerations=[],
            domain_context={"urgency": request.urgency} if request.urgency else {},
        )

        guidance_text = await self.fetch_guidance(context)

        if guidance_text:
            # Build advice list
            advice = [
                WisdomAdvice(
                    source=f"mcp_prompt",
                    advice=guidance_text,
                    confidence=0.7,  # Medium confidence for MCP prompts
                    reasoning="Guidance from MCP server prompt",
                )
            ]

            # Select best option if options provided
            selected_option = None
            if request.options:
                # Simple heuristic: check if guidance mentions any option
                for option in request.options:
                    if option.lower() in guidance_text.lower():
                        selected_option = option
                        break
                if not selected_option:
                    selected_option = request.options[0]

            return GuidanceResponse(
                selected_option=selected_option,
                custom_guidance=guidance_text,
                reasoning="Guidance retrieved from MCP server",
                wa_id="mcp_wise_service",
                signature="mcp",
                advice=advice,
            )

        # No guidance available
        return GuidanceResponse(
            selected_option=request.options[0] if request.options else None,
            custom_guidance="No MCP guidance available",
            reasoning="No MCP prompts could provide guidance",
            wa_id="mcp_wise_service",
            signature="none",
        )

    async def send_deferral(self, deferral: DeferralRequest) -> str:
        """Send a deferral to MCP servers.

        MCP servers typically don't handle deferrals directly,
        but we can notify them through resources or prompts.

        Args:
            deferral: Deferral request

        Returns:
            Deferral ID string
        """
        self._deferrals_sent += 1

        # For now, just log the deferral - MCP doesn't have a native deferral concept
        logger.info(
            f"MCP Deferral received: task={deferral.task_id}, "
            f"thought={deferral.thought_id}, reason={deferral.reason}"
        )

        # Return a deferral ID
        return f"mcp_deferral_{deferral.task_id}"

    async def check_authorization(self, wa_id: str, action: str, resource: Optional[str] = None) -> bool:
        """Check if a wise authority is authorized for an action.

        Args:
            wa_id: Wise authority ID
            action: Action to authorize
            resource: Optional resource

        Returns:
            True if authorized (MCP-based WA is always authorized for basic actions)
        """
        # MCP servers are trusted once connected
        return True

    async def request_approval(self, action: str, context: Any) -> bool:
        """Request approval for an action.

        Args:
            action: Action requiring approval
            context: Approval context

        Returns:
            True if approved
        """
        # MCP doesn't have an approval mechanism - approve by default
        return True

    async def get_pending_deferrals(self, wa_id: Optional[str] = None) -> List[Any]:
        """Get pending deferrals.

        MCP doesn't store deferrals, so returns empty list.
        """
        return []

    async def resolve_deferral(self, deferral_id: str, response: Any) -> bool:
        """Resolve a deferred decision.

        MCP doesn't handle deferral resolution.
        """
        return False

    async def get_telemetry(self) -> JSONDict:
        """Get telemetry data for the wise service."""
        uptime_seconds = 0.0
        if self._start_time:
            now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
            uptime_seconds = (now - self._start_time).total_seconds()

        prompts_count = sum(len(prompts) for prompts in self._prompts_cache.values())

        return {
            "service_name": "mcp_wise_service",
            "healthy": self._running,
            "guidance_requests": self._guidance_requests,
            "deferrals_sent": self._deferrals_sent,
            "error_count": self._errors,
            "prompts_available": prompts_count,
            "servers_connected": len(self._mcp_clients),
            "uptime_seconds": uptime_seconds,
        }


__all__ = ["MCPWiseService"]
