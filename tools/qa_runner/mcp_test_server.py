#!/usr/bin/env python3
"""
MCP Test Server for QA testing.

Uses the official MCP SDK to provide a proper MCP server with test tools.
Supports stdio transport for reliable subprocess-based testing.

Usage:
    python -m tools.qa_runner.mcp_test_server
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Create the MCP server
server = Server("ciris-qa-test-server")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available test tools."""
    return [
        Tool(
            name="qa_echo",
            description="Echoes back the input message - for testing tool execution",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message to echo back",
                    }
                },
                "required": ["message"],
            },
        ),
        Tool(
            name="qa_add",
            description="Adds two numbers together - for testing numeric tools",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First number"},
                    "b": {"type": "number", "description": "Second number"},
                },
                "required": ["a", "b"],
            },
        ),
        Tool(
            name="qa_get_time",
            description="Returns the current server time in ISO format",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="qa_list_items",
            description="Returns a list of test items",
            inputSchema={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of items to return",
                        "default": 5,
                    }
                },
            },
        ),
        Tool(
            name="qa_fail",
            description="Always fails - for testing error handling",
            inputSchema={
                "type": "object",
                "properties": {
                    "error_message": {
                        "type": "string",
                        "description": "Error message to return",
                        "default": "Intentional test failure",
                    }
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool call: {name} with args: {arguments}")

    if name == "qa_echo":
        message = arguments.get("message", "")
        return [TextContent(type="text", text=f"Echo: {message}")]

    elif name == "qa_add":
        a = float(arguments.get("a", 0))
        b = float(arguments.get("b", 0))
        result = a + b
        return [TextContent(type="text", text=f"Result: {a} + {b} = {result}")]

    elif name == "qa_get_time":
        now = datetime.now(timezone.utc).isoformat()
        return [TextContent(type="text", text=f"Current time: {now}")]

    elif name == "qa_list_items":
        count = int(arguments.get("count", 5))
        items = [f"item_{i}" for i in range(1, count + 1)]
        return [TextContent(type="text", text=f"Items: {', '.join(items)}")]

    elif name == "qa_fail":
        error_msg = arguments.get("error_message", "Intentional test failure")
        raise ValueError(error_msg)

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    """Run the MCP test server."""
    logger.info("Starting MCP test server (stdio transport)...")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
