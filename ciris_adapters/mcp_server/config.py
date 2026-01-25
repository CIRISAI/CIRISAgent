"""
MCP Server Configuration.

Simple configuration for the MCP server adapter.
"""

import logging
import os
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class MCPTransportType(str, Enum):
    """MCP transport types."""

    STDIO = "stdio"  # Standard input/output (for Claude Desktop)
    SSE = "sse"  # Server-sent events (HTTP)
    HTTP = "http"  # Standard HTTP


class MCPServerConfig(BaseModel):
    """Configuration for MCP server."""

    # Server identification
    server_id: str = Field("ciris_mcp", description="Unique server identifier")
    server_name: str = Field("CIRIS Agent", description="Human-readable server name")

    # Transport settings
    transport: MCPTransportType = Field(
        MCPTransportType.STDIO,
        description="Transport type (stdio for Claude Desktop, sse/http for web)",
    )
    host: str = Field("127.0.0.1", description="Host for HTTP/SSE transport")
    port: int = Field(8765, description="Port for HTTP/SSE transport")

    # Authentication
    require_auth: bool = Field(True, description="Require authentication for message/history tools")
    api_key: Optional[str] = Field(None, description="API key for authentication (if set)")

    # Enable/disable
    enabled: bool = Field(True, description="Whether server is enabled")

    model_config = ConfigDict(extra="forbid")

    def load_env_vars(self) -> None:
        """Load configuration from environment variables."""
        if os.environ.get("MCP_SERVER_ID"):
            self.server_id = os.environ["MCP_SERVER_ID"]

        if os.environ.get("MCP_SERVER_NAME"):
            self.server_name = os.environ["MCP_SERVER_NAME"]

        if os.environ.get("MCP_TRANSPORT"):
            try:
                self.transport = MCPTransportType(os.environ["MCP_TRANSPORT"])
            except ValueError:
                logger.warning(f"Invalid MCP_TRANSPORT value: {os.environ['MCP_TRANSPORT']}")

        if os.environ.get("MCP_HOST"):
            self.host = os.environ["MCP_HOST"]

        if os.environ.get("MCP_PORT"):
            try:
                self.port = int(os.environ["MCP_PORT"])
            except ValueError:
                logger.warning(f"Invalid MCP_PORT value: {os.environ['MCP_PORT']}")

        if os.environ.get("MCP_API_KEY"):
            self.api_key = os.environ["MCP_API_KEY"]

        if os.environ.get("MCP_REQUIRE_AUTH"):
            self.require_auth = os.environ["MCP_REQUIRE_AUTH"].lower() == "true"


__all__ = [
    "MCPTransportType",
    "MCPServerConfig",
]
