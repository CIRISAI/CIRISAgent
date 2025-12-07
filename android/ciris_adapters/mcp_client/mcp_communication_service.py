"""
MCP Communication Service.

Provides communication capabilities through MCP server resources.
Integrates with the CommunicationBus for the CIRIS agent.

MCP resources can be used for:
- Fetching context/messages from external systems
- Sending messages through MCP-connected channels
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import FetchedMessage
from ciris_engine.schemas.types import JSONDict

from .config import MCPServerConfig
from .security import MCPSecurityManager

logger = logging.getLogger(__name__)

# Channel prefix for MCP resources
MCP_CHANNEL_PREFIX = "mcp:"


class MCPCommunicationService:
    """
    Communication service that uses MCP resources for messaging.

    This service:
    - Discovers resources from MCP servers
    - Treats resources as message channels
    - Supports resource subscriptions for updates
    - Provides telemetry and metrics
    """

    def __init__(
        self,
        security_manager: MCPSecurityManager,
        time_service: Optional[TimeServiceProtocol] = None,
        home_channel_id: Optional[str] = None,
    ) -> None:
        """Initialize MCP communication service.

        Args:
            security_manager: Security manager for validation
            time_service: Time service for timestamps
            home_channel_id: Default channel for messages
        """
        self._security_manager = security_manager
        self._time_service = time_service
        self._home_channel_id = home_channel_id
        self._running = False
        self._start_time: Optional[datetime] = None

        # MCP clients per server
        self._mcp_clients: Dict[str, Any] = {}

        # Cached resource information
        self._resources_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}  # server_id -> {uri -> resource_info}

        # Message buffers for resources
        self._message_buffers: Dict[str, List[FetchedMessage]] = {}  # channel_id -> messages

        # Metrics
        self._messages_sent = 0
        self._messages_fetched = 0
        self._errors = 0

    def register_mcp_client(self, server_id: str, client: Any) -> None:
        """Register an MCP client for a server.

        Args:
            server_id: Server identifier
            client: MCP client instance
        """
        self._mcp_clients[server_id] = client
        logger.info(f"Registered MCP communication client for server '{server_id}'")

    def unregister_mcp_client(self, server_id: str) -> None:
        """Unregister an MCP client.

        Args:
            server_id: Server to unregister
        """
        if server_id in self._mcp_clients:
            del self._mcp_clients[server_id]
            logger.info(f"Unregistered MCP communication client for server '{server_id}'")
        if server_id in self._resources_cache:
            del self._resources_cache[server_id]

    async def start(self) -> None:
        """Start the communication service."""
        self._running = True
        self._start_time = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        logger.info("MCPCommunicationService started")

    async def stop(self) -> None:
        """Stop the communication service."""
        self._running = False
        self._resources_cache.clear()
        self._message_buffers.clear()
        logger.info("MCPCommunicationService stopped")

    async def is_healthy(self) -> bool:
        """Check if the communication service is healthy."""
        return self._running

    def get_capabilities(self) -> Any:
        """Get service capabilities for registration."""
        from ciris_engine.schemas.services.capabilities import ServiceCapabilities

        return ServiceCapabilities(
            service_type=ServiceType.COMMUNICATION,
            actions=[
                "send_message",
                "fetch_messages",
            ],
        )

    def get_home_channel_id(self) -> Optional[str]:
        """Get the home channel ID for this adapter."""
        return self._home_channel_id

    async def _refresh_resources_cache(self, server_id: str) -> None:
        """Refresh the resources cache for a server.

        Args:
            server_id: Server to refresh resources for
        """
        client = self._mcp_clients.get(server_id)
        if not client:
            return

        try:
            # Call MCP list_resources
            if hasattr(client, "list_resources"):
                response = await client.list_resources()
                resources = response.resources if hasattr(response, "resources") else []

                self._resources_cache[server_id] = {}

                for resource in resources:
                    uri = resource.uri if hasattr(resource, "uri") else str(resource.get("uri", ""))
                    name = resource.name if hasattr(resource, "name") else str(resource.get("name", ""))
                    description = (
                        resource.description
                        if hasattr(resource, "description")
                        else str(resource.get("description", ""))
                    )
                    mime_type = (
                        resource.mimeType if hasattr(resource, "mimeType") else resource.get("mimeType", "text/plain")
                    )

                    self._resources_cache[server_id][uri] = {
                        "uri": uri,
                        "name": name,
                        "description": description,
                        "mime_type": mime_type,
                    }

                    # Set first resource as home channel if not set
                    if not self._home_channel_id and server_id:
                        self._home_channel_id = f"{MCP_CHANNEL_PREFIX}{server_id}/{uri}"

                logger.debug(
                    f"Refreshed resources cache for '{server_id}': "
                    f"{len(self._resources_cache[server_id])} resources available"
                )

        except Exception as e:
            logger.error(f"Failed to refresh resources for server '{server_id}': {e}")

    def _parse_channel_id(self, channel_id: str) -> tuple[Optional[str], Optional[str]]:
        """Parse a channel ID to extract server ID and resource URI.

        Channel format: mcp:server_id/resource_uri

        Args:
            channel_id: Channel ID to parse

        Returns:
            (server_id, resource_uri) tuple
        """
        if not channel_id.startswith(MCP_CHANNEL_PREFIX):
            return None, None

        remaining = channel_id[len(MCP_CHANNEL_PREFIX) :]
        if "/" in remaining:
            parts = remaining.split("/", 1)
            return parts[0], parts[1]
        return remaining, None

    async def send_message(self, channel_id: str, content: str) -> bool:
        """Send a message through MCP.

        MCP resources are typically read-only, so we'll:
        1. If there's a tool that can send messages, use it
        2. Otherwise, store in local buffer

        Args:
            channel_id: Target channel
            content: Message content

        Returns:
            True if message was handled
        """
        self._messages_sent += 1

        server_id, resource_uri = self._parse_channel_id(channel_id)

        if not server_id:
            # Store in local buffer
            if channel_id not in self._message_buffers:
                self._message_buffers[channel_id] = []

            now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
            message = FetchedMessage(
                message_id=f"mcp_{now.timestamp()}",
                content=content,
                author_id="agent",
                author_name="CIRIS Agent",
                channel_id=channel_id,
                timestamp=now,
            )
            self._message_buffers[channel_id].append(message)
            logger.debug(f"Stored message in local buffer for channel '{channel_id}'")
            return True

        client = self._mcp_clients.get(server_id)
        if not client:
            logger.warning(f"No MCP client for server '{server_id}'")
            return False

        # Check if there's a send_message tool available
        try:
            if hasattr(client, "call_tool"):
                # Try to call a message sending tool if available
                tools_response = await client.list_tools()
                tools = tools_response.tools if hasattr(tools_response, "tools") else []

                send_tools = [
                    t
                    for t in tools
                    if any(
                        kw in (t.name if hasattr(t, "name") else "").lower()
                        for kw in ["send", "message", "post", "write"]
                    )
                ]

                if send_tools:
                    tool = send_tools[0]
                    tool_name = tool.name if hasattr(tool, "name") else str(tool.get("name", ""))
                    await client.call_tool(tool_name, {"message": content, "channel": resource_uri})
                    logger.debug(f"Sent message via MCP tool '{tool_name}'")
                    return True

            # No sending capability - store in buffer
            if channel_id not in self._message_buffers:
                self._message_buffers[channel_id] = []

            now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
            message = FetchedMessage(
                message_id=f"mcp_{now.timestamp()}",
                content=content,
                author_id="agent",
                author_name="CIRIS Agent",
                channel_id=channel_id,
                timestamp=now,
            )
            self._message_buffers[channel_id].append(message)
            logger.debug(f"No MCP send capability - stored message in buffer")
            return True

        except Exception as e:
            self._errors += 1
            logger.error(f"Failed to send message via MCP: {e}")
            return False

    async def fetch_messages(self, channel_id: str, limit: int = 100) -> List[FetchedMessage]:
        """Fetch messages from an MCP resource.

        Args:
            channel_id: Channel to fetch from
            limit: Maximum number of messages

        Returns:
            List of FetchedMessage objects
        """
        messages: List[FetchedMessage] = []

        # Check local buffer first
        if channel_id in self._message_buffers:
            messages.extend(self._message_buffers[channel_id][-limit:])

        server_id, resource_uri = self._parse_channel_id(channel_id)

        if not server_id or not resource_uri:
            return messages

        client = self._mcp_clients.get(server_id)
        if not client:
            return messages

        try:
            # Read the MCP resource
            if hasattr(client, "read_resource"):
                response = await client.read_resource(resource_uri)

                # Extract content from response
                contents = response.contents if hasattr(response, "contents") else []

                for content in contents:
                    text = ""
                    if hasattr(content, "text"):
                        text = content.text
                    elif isinstance(content, dict):
                        text = content.get("text", str(content))
                    else:
                        text = str(content)

                    if text:
                        now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
                        message = FetchedMessage(
                            message_id=f"mcp_resource_{now.timestamp()}",
                            content=text,
                            author_id=f"mcp_{server_id}",
                            author_name=f"MCP: {server_id}",
                            channel_id=channel_id,
                            timestamp=now,
                        )
                        messages.append(message)
                        self._messages_fetched += 1

        except Exception as e:
            self._errors += 1
            logger.error(f"Failed to fetch messages from MCP resource: {e}")

        return messages[:limit]

    async def get_active_channels(self) -> List[Dict[str, str]]:
        """Get list of active MCP channels (resources).

        Returns:
            List of channel info dictionaries
        """
        channels = []

        for server_id in self._mcp_clients:
            if server_id not in self._resources_cache:
                await self._refresh_resources_cache(server_id)

            for uri, resource_info in self._resources_cache.get(server_id, {}).items():
                channel_id = f"{MCP_CHANNEL_PREFIX}{server_id}/{uri}"
                channels.append(
                    {
                        "channel_id": channel_id,
                        "name": resource_info["name"],
                        "description": resource_info.get("description", ""),
                        "server_id": server_id,
                    }
                )

        return channels

    async def get_telemetry(self) -> JSONDict:
        """Get telemetry data for the communication service."""
        uptime_seconds = 0.0
        if self._start_time:
            now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
            uptime_seconds = (now - self._start_time).total_seconds()

        resources_count = sum(len(resources) for resources in self._resources_cache.values())

        return {
            "service_name": "mcp_communication_service",
            "healthy": self._running,
            "messages_sent": self._messages_sent,
            "messages_fetched": self._messages_fetched,
            "error_count": self._errors,
            "resources_available": resources_count,
            "servers_connected": len(self._mcp_clients),
            "buffered_channels": len(self._message_buffers),
            "uptime_seconds": uptime_seconds,
        }


__all__ = ["MCPCommunicationService", "MCP_CHANNEL_PREFIX"]
