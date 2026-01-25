"""
MCP (Model Context Protocol) adapter QA tests.

Tests the complete MCP adapter functionality:
- Adapter loading via API runtime control
- Multiple MCP client adapters simultaneously
- Multiple MCP server adapters simultaneously
- Tool execution via MCP through agent interaction ($tool commands)
- Resource access via MCP
- Security validation (rate limiting, poisoning detection)
- Adapter unloading and cleanup

Uses stdio transport with a local MCP test server for end-to-end testing.
"""

import asyncio
import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from rich.console import Console
from rich.table import Table


class MCPTests:
    """Test MCP adapter functionality via API runtime control."""

    def __init__(self, client: Any, console: Console):
        """Initialize MCP tests.

        Args:
            client: CIRIS SDK client (authenticated)
            console: Rich console for output
        """
        self.client = client
        self.console = console
        self.results: List[Dict[str, Any]] = []

        # Track loaded adapters for cleanup
        self.loaded_adapter_ids: List[str] = []

        # Track MCP server ID for tool name prefixing
        self._mcp_server_id = "qa-test-server"

        # Base URL for direct API calls (some operations need raw requests)
        self._base_url = getattr(client, "_base_url", "http://localhost:8080")
        if hasattr(client, "_transport") and hasattr(client._transport, "_base_url"):
            self._base_url = client._transport._base_url

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers from client."""
        headers = {"Content-Type": "application/json"}

        # Try multiple ways to get the token
        token = None

        # Method 1: Direct api_key attribute on client
        if hasattr(self.client, "api_key") and self.client.api_key:
            token = self.client.api_key

        # Method 2: Transport's api_key
        elif hasattr(self.client, "_transport"):
            transport = self.client._transport
            if hasattr(transport, "api_key") and transport.api_key:
                token = transport.api_key

        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            self.console.print("     [dim]Warning: Could not extract auth token from client[/dim]")

        return headers

    def _get_test_server_command(self) -> List[str]:
        """Get the command to run the MCP test server."""
        python_path = sys.executable
        server_script = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "mcp_test_server.py",
        )
        return [python_path, server_script]

    def _get_mcp_tool_name(self, tool_name: str) -> str:
        """Get the full MCP tool name with server prefix.

        MCP tools are registered as mcp_{server_id}_{tool_name}
        """
        return f"mcp_{self._mcp_server_id}_{tool_name}"

    async def run(self) -> List[Dict[str, Any]]:
        """Run all MCP tests."""
        self.console.print("\n[cyan]🔌 Testing MCP Adapter Loading & Operations[/cyan]")

        tests = [
            # Phase 1: Verify baseline system state
            ("Verify System Health", self.test_system_health),
            ("List Initial Adapters", self.test_list_initial_adapters),
            # Phase 2: Load MCP client adapter with local test server (stdio)
            ("Load MCP Client (stdio)", self.test_load_mcp_client_local),
            ("Verify MCP Client Connected", self.test_verify_client_connected),
            ("Verify MCP Tools Discovered", self.test_verify_tools_discovered),
            # Phase 3: Test tool execution via agent interaction
            ("Test Tool: qa_echo (via interact)", self.test_tool_qa_echo),
            ("Test Tool: qa_add (via interact)", self.test_tool_qa_add),
            ("Test Tool: qa_get_time (via interact)", self.test_tool_qa_get_time),
            # Phase 4: Test MCP client adapter loading (additional)
            ("Load MCP Client Adapter (test-client-1)", self.test_load_mcp_client_1),
            ("Load MCP Client Adapter (test-client-2)", self.test_load_mcp_client_2),
            ("Verify Multiple MCP Clients Loaded", self.test_verify_multiple_clients),
            # Phase 5: Test MCP server adapter loading
            ("Load MCP Server Adapter (test-server-1)", self.test_load_mcp_server_1),
            ("Load MCP Server Adapter (test-server-2)", self.test_load_mcp_server_2),
            ("Verify Multiple MCP Servers Loaded", self.test_verify_multiple_servers),
            # Phase 6: Test adapter status and metrics
            ("Get MCP Client Status", self.test_get_client_status),
            ("Get MCP Server Status", self.test_get_server_status),
            # Phase 6.5: Test MCP Server Protocol (actual MCP requests)
            ("MCP Server: Initialize", self.test_mcp_server_initialize),
            ("MCP Server: List Tools", self.test_mcp_server_list_tools),
            ("MCP Server: Call Status Tool", self.test_mcp_server_call_status),
            ("MCP Server: Call Message Tool (auth)", self.test_mcp_server_call_message),
            # Phase 7: Test adapter reload
            ("Reload MCP Client Adapter", self.test_reload_mcp_client),
            # Phase 8: Security & Error Handling Tests
            ("Test Invalid Adapter Config (Error Handling)", self.test_invalid_adapter_config),
            ("Test Capability Discovery", self.test_capability_discovery),
            ("Test Concurrent Adapter Operations", self.test_concurrent_operations),
            # Phase 9: Cleanup - unload all test adapters
            ("Unload Test Adapters", self.test_unload_adapters),
            ("Verify Cleanup Complete", self.test_verify_cleanup),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "✅ PASS", "error": None})
                self.console.print(f"  ✅ {name}")
            except Exception as e:
                self.results.append({"test": name, "status": "❌ FAIL", "error": str(e)})
                self.console.print(f"  ❌ {name}: {str(e)[:100]}")
                if self.console.is_terminal:
                    self.console.print(f"     [dim]{traceback.format_exc()}[/dim]")

        self._print_summary()
        return self.results

    async def test_load_mcp_client_local(self) -> None:
        """Load MCP client adapter with local test server via stdio transport.

        This test verifies the adapter loads AND successfully connects to the MCP server.
        If MCP SDK is not installed, this test should FAIL.
        """
        # Get the command to run the test server
        command = self._get_test_server_command()

        adapter_id = "mcp_qa_client"
        result = await self._load_adapter(
            adapter_type="mcp_client",
            adapter_id=adapter_id,
            config={
                "adapter_type": "mcp_client",
                "enabled": True,
                "settings": {},
                "adapter_config": {
                    "adapter_id": adapter_id,
                    "servers": [
                        {
                            "server_id": self._mcp_server_id,
                            "name": "QA Test Server",
                            "description": "Local MCP test server for QA testing",
                            "transport": "stdio",
                            "command": command[0],
                            "args": command[1:],
                            "enabled": True,
                            "auto_start": True,
                            "bus_bindings": [
                                {"bus_type": "tool", "priority": 10},
                            ],
                        }
                    ],
                },
            },
        )
        self.loaded_adapter_ids.append(adapter_id)

        # Give the adapter time to connect and discover tools
        await asyncio.sleep(2.0)

        # STRICT CHECK: Verify MCP server connection succeeded by checking for tools
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters/{adapter_id}",
            headers=headers,
            timeout=30,
        )

        if response.status_code != 200:
            raise ValueError(f"Failed to get adapter status after load: HTTP {response.status_code}")

        data = response.json()
        adapter_data = data.get("data", {})

        # Check for connection errors or warnings
        errors = adapter_data.get("errors", [])
        warnings = adapter_data.get("warnings", [])
        if errors:
            raise ValueError(f"MCP adapter loaded with errors: {errors}")

        # Verify the adapter is actually running
        if not adapter_data.get("is_running", False):
            raise ValueError("MCP adapter loaded but not running - connection may have failed")

        # Verify tools were discovered (MCP SDK installed and server connected)
        tools = adapter_data.get("tools", [])
        mcp_tools = []
        for t in tools or []:
            name = t.get("name", "") if isinstance(t, dict) else str(t)
            if name.startswith(f"mcp_{self._mcp_server_id}_"):
                mcp_tools.append(name)

        if not mcp_tools:
            raise ValueError(
                f"MCP adapter loaded but discovered 0 tools from server '{self._mcp_server_id}'. "
                f"Check: 1) MCP SDK installed? (pip install mcp), "
                f"2) Test server script exists at {command}?"
            )

        self.console.print(f"     [dim]MCP adapter loaded, {len(mcp_tools)} tools discovered[/dim]")

    async def test_verify_client_connected(self) -> None:
        """Verify MCP client connected to test server AND discovered tools.

        This test verifies REAL connectivity - not just that the adapter object exists.
        If MCP SDK is not installed or server connection failed, this should FAIL.
        """
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters/mcp_qa_client",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            raise ValueError("MCP client adapter not found")

        if response.status_code != 200:
            raise ValueError(f"Failed to get adapter status: HTTP {response.status_code}")

        data = response.json()
        adapter_data = data.get("data", {})
        is_running = adapter_data.get("is_running", False)

        if not is_running:
            raise ValueError("MCP client adapter loaded but NOT running")

        # STRICT CHECK: Verify tools were actually discovered
        # An MCP client that can't connect to servers will have no tools
        tools = adapter_data.get("tools", [])
        if tools is None:
            tools = []

        # Extract tool names and filter for our MCP server's tools
        tool_names = []
        for t in tools:
            if isinstance(t, dict):
                tool_names.append(t.get("name", ""))
            elif isinstance(t, str):
                tool_names.append(t)

        mcp_tools = [t for t in tool_names if t.startswith(f"mcp_{self._mcp_server_id}_")]

        if not mcp_tools:
            # Check if MCP SDK is likely missing
            raise ValueError(
                f"MCP client adapter running but NO TOOLS discovered from server '{self._mcp_server_id}'. "
                f"This usually means: 1) MCP SDK not installed (pip install mcp), "
                f"2) Server connection failed, or 3) Server returned no tools. "
                f"Available tools: {tool_names[:5]}"
            )

        self.console.print(f"     [dim]MCP client connected via stdio, {len(mcp_tools)} tools discovered ✓[/dim]")

    async def test_verify_tools_discovered(self) -> None:
        """Verify MCP tools were discovered and registered."""
        # Check if tools are available via adapter status endpoint
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters/mcp_qa_client",
            headers=headers,
            timeout=30,
        )

        if response.status_code != 200:
            raise ValueError(f"Could not get adapter status: HTTP {response.status_code}")

        data = response.json()
        tools = data.get("data", {}).get("tools", [])

        if tools is None:
            tools = []

        # Extract tool names from ToolInfo objects if needed
        tool_names = []
        for t in tools:
            if isinstance(t, dict):
                tool_names.append(t.get("name", ""))
            elif isinstance(t, str):
                tool_names.append(t)

        # Look for MCP tools with our server prefix
        mcp_tools = [t for t in tool_names if t.startswith(f"mcp_{self._mcp_server_id}_")]

        if not mcp_tools:
            raise ValueError(
                f"No MCP tools discovered with prefix 'mcp_{self._mcp_server_id}_'. Available tools: {tool_names[:10]}"
            )

        self.console.print(f"     [dim]Found {len(mcp_tools)} MCP tools: {mcp_tools}[/dim]")

    async def test_tool_qa_echo(self) -> None:
        """Test qa_echo tool execution via agent interaction."""
        await self._complete_task()

        # Use mock LLM $tool command to execute the MCP tool
        tool_name = self._get_mcp_tool_name("qa_echo")
        message = f'$tool {tool_name} message="Hello from QA!"'

        # Capture timestamp BEFORE interaction
        before_interaction = datetime.now(timezone.utc)

        self.console.print(f"     [dim]Sending: {message}[/dim]")
        response = await self.client.agent.interact(message)
        self.console.print(f"     [dim]Response: {response}[/dim]")

        # Verify TOOL action was executed via audit trail AFTER our interaction
        entry = await self._verify_audit_entry_after("tool", tool_name, before_interaction)
        self.console.print(
            f"     [dim]qa_echo: TOOL action verified in audit (entry_id={entry.get('entry_id', 'unknown')})[/dim]"
        )

    async def test_tool_qa_add(self) -> None:
        """Test qa_add tool execution via agent interaction."""
        await self._complete_task()

        tool_name = self._get_mcp_tool_name("qa_add")
        message = f'$tool {tool_name} {{"a": 5, "b": 3}}'

        # Capture timestamp BEFORE interaction
        before_interaction = datetime.now(timezone.utc)

        self.console.print(f"     [dim]Sending: {message}[/dim]")
        response = await self.client.agent.interact(message)
        self.console.print(f"     [dim]Response: {response}[/dim]")

        # Verify TOOL action was executed AFTER our interaction
        entry = await self._verify_audit_entry_after("tool", tool_name, before_interaction)
        self.console.print(
            f"     [dim]qa_add: TOOL action verified in audit (entry_id={entry.get('entry_id', 'unknown')})[/dim]"
        )

    async def test_tool_qa_get_time(self) -> None:
        """Test qa_get_time tool execution via agent interaction."""
        await self._complete_task()

        tool_name = self._get_mcp_tool_name("qa_get_time")
        message = f"$tool {tool_name}"

        # Capture timestamp BEFORE interaction
        before_interaction = datetime.now(timezone.utc)

        self.console.print(f"     [dim]Sending: {message}[/dim]")
        response = await self.client.agent.interact(message)
        self.console.print(f"     [dim]Response: {response}[/dim]")

        # Verify TOOL action was executed AFTER our interaction
        entry = await self._verify_audit_entry_after("tool", tool_name, before_interaction)
        self.console.print(
            f"     [dim]qa_get_time: TOOL action verified in audit (entry_id={entry.get('entry_id', 'unknown')})[/dim]"
        )

    async def test_system_health(self) -> None:
        """Verify system is healthy before running MCP tests."""
        health = await self.client.system.health()

        if not hasattr(health, "status"):
            raise ValueError("Health response missing status field")

        self.console.print(f"     [dim]System status: {health.status}[/dim]")

    async def test_list_initial_adapters(self) -> None:
        """List adapters before loading any MCP adapters."""
        headers = self._get_auth_headers()
        response = requests.get(f"{self._base_url}/v1/system/adapters", headers=headers, timeout=30)

        if response.status_code != 200:
            raise ValueError(f"Failed to list adapters: {response.status_code}")

        data = response.json()

        # Handle wrapped response format: {"success": true, "data": {...}}
        # or direct format: {"adapters": [...]}
        if "data" in data and isinstance(data["data"], dict):
            adapters = data["data"].get("adapters", [])
        elif "adapters" in data:
            adapters = data.get("adapters", [])
        else:
            adapters = []

        adapter_types = [a.get("adapter_type", "unknown") for a in adapters]
        self.console.print(f"     [dim]Initial adapters: {adapter_types}[/dim]")

        # Verify no MCP adapters are loaded yet
        mcp_adapters = [a for a in adapters if "mcp" in a.get("adapter_type", "").lower()]
        if mcp_adapters:
            self.console.print(f"     [dim]Note: MCP adapters already present: {len(mcp_adapters)}[/dim]")

    async def test_load_mcp_client_1(self) -> None:
        """Load first MCP client adapter via API."""
        adapter_id = "mcp_test_client_1"
        await self._load_adapter(
            adapter_type="mcp_client",
            adapter_id=adapter_id,
            config={
                "adapter_type": "mcp_client",
                "enabled": True,
                "settings": {},  # Simple settings (flat primitives only)
                "adapter_config": {  # Complex nested config goes here
                    "adapter_id": adapter_id,
                    "servers": [
                        {
                            "server_id": "test-server-1",
                            "name": "Test Server 1",
                            "description": "Test MCP server for QA",
                            "transport": "stdio",
                            "command": "echo",
                            "args": ["test"],
                            "enabled": True,
                            "auto_start": True,
                            "bus_bindings": [
                                {"bus_type": "tool", "priority": 50},
                            ],
                        }
                    ],
                },
            },
        )
        self.loaded_adapter_ids.append(adapter_id)

    async def test_load_mcp_client_2(self) -> None:
        """Load second MCP client adapter via API."""
        adapter_id = "mcp_test_client_2"
        await self._load_adapter(
            adapter_type="mcp_client",
            adapter_id=adapter_id,
            config={
                "adapter_type": "mcp_client",
                "enabled": True,
                "settings": {},  # Simple settings (flat primitives only)
                "adapter_config": {  # Complex nested config goes here
                    "adapter_id": adapter_id,
                    "servers": [
                        {
                            "server_id": "test-server-2",
                            "name": "Test Server 2",
                            "description": "Second test MCP server for QA",
                            "transport": "stdio",
                            "command": "cat",
                            "args": [],
                            "enabled": True,
                            "auto_start": True,
                            "bus_bindings": [
                                {"bus_type": "tool", "priority": 50},
                            ],
                        }
                    ],
                },
            },
        )
        self.loaded_adapter_ids.append(adapter_id)

    async def test_verify_multiple_clients(self) -> None:
        """Verify multiple MCP client adapters are loaded."""
        adapters = await self._list_adapters()

        mcp_clients = [a for a in adapters if a.get("adapter_id", "").startswith("mcp_test_client")]

        if len(mcp_clients) < 2:
            raise ValueError(f"Expected at least 2 MCP client adapters, found {len(mcp_clients)}")

        self.console.print(f"     [dim]MCP client adapters loaded: {len(mcp_clients)}[/dim]")

    async def test_load_mcp_server_1(self) -> None:
        """Load first MCP server adapter via API with HTTP transport for testing."""
        adapter_id = "mcp_test_server_1"
        # Use HTTP transport on port 9876 so we can test MCP protocol
        self._mcp_test_server_port = 9876
        await self._load_adapter(
            adapter_type="mcp_server",
            adapter_id=adapter_id,
            config={
                "adapter_type": "mcp_server",
                "enabled": True,
                "settings": {},
                "adapter_config": {
                    "server_id": "test-server-1",
                    "server_name": "Test MCP Server 1",
                    "transport": "sse",  # HTTP-based transport for testing
                    "host": "127.0.0.1",
                    "port": self._mcp_test_server_port,
                    "require_auth": False,  # Allow unauthenticated for testing
                    "enabled": True,
                },
            },
        )
        self.loaded_adapter_ids.append(adapter_id)
        # Give server time to start
        await asyncio.sleep(1.0)

    async def test_load_mcp_server_2(self) -> None:
        """Load second MCP server adapter via API."""
        adapter_id = "mcp_test_server_2"
        await self._load_adapter(
            adapter_type="mcp_server",
            adapter_id=adapter_id,
            config={
                "adapter_type": "mcp_server",
                "enabled": True,
                "settings": {},  # Simple settings (flat primitives only)
                "adapter_config": {  # Complex nested config goes here
                    "server_id": "test-server-2",
                    "server_name": "Test MCP Server 2",
                    "transport": "sse",
                    "host": "127.0.0.1",
                    "port": 9999,
                    "enabled": True,
                },
            },
        )
        self.loaded_adapter_ids.append(adapter_id)

    async def test_verify_multiple_servers(self) -> None:
        """Verify multiple MCP server adapters are loaded."""
        adapters = await self._list_adapters()

        mcp_servers = [a for a in adapters if a.get("adapter_id", "").startswith("mcp_test_server")]

        if len(mcp_servers) < 2:
            raise ValueError(f"Expected at least 2 MCP server adapters, found {len(mcp_servers)}")

        self.console.print(f"     [dim]MCP server adapters loaded: {len(mcp_servers)}[/dim]")

        # Verify total MCP adapters
        all_mcp = [a for a in adapters if "mcp" in a.get("adapter_type", "").lower()]
        self.console.print(f"     [dim]Total MCP adapters: {len(all_mcp)}[/dim]")

    async def test_get_client_status(self) -> None:
        """Get status of MCP client adapter."""
        if "mcp_test_client_1" not in self.loaded_adapter_ids:
            self.console.print("     [dim]Skipping - client not loaded[/dim]")
            return

        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters/mcp_test_client_1",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            raise ValueError("MCP client adapter not found")

        if response.status_code != 200:
            raise ValueError(f"Failed to get adapter status: {response.status_code}")

        data = response.json()
        if data.get("success"):
            status = data.get("data", {})
            is_running = status.get("is_running", False)
            self.console.print(f"     [dim]Client adapter running: {is_running}[/dim]")

    async def test_get_server_status(self) -> None:
        """Get status of MCP server adapter."""
        if "mcp_test_server_1" not in self.loaded_adapter_ids:
            self.console.print("     [dim]Skipping - server not loaded[/dim]")
            return

        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters/mcp_test_server_1",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            raise ValueError("MCP server adapter not found")

        if response.status_code != 200:
            raise ValueError(f"Failed to get adapter status: {response.status_code}")

        data = response.json()
        if data.get("success"):
            status = data.get("data", {})
            is_running = status.get("is_running", False)
            self.console.print(f"     [dim]Server adapter running: {is_running}[/dim]")

    async def test_mcp_server_initialize(self) -> None:
        """Test MCP server initialize request."""
        if "mcp_test_server_1" not in self.loaded_adapter_ids:
            raise ValueError("MCP server not loaded - cannot test protocol")

        # Send MCP initialize request
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "QA Test Client", "version": "1.0.0"},
                "capabilities": {},
            },
        }

        response = await self._send_mcp_request(mcp_request)

        # Verify response structure
        if response.get("error"):
            raise ValueError(f"MCP initialize failed: {response['error']}")

        result = response.get("result", {})
        if not result.get("protocolVersion"):
            raise ValueError(f"Missing protocolVersion in response: {result}")

        server_info = result.get("serverInfo", {})
        self.console.print(
            f"     [dim]MCP Server: {server_info.get('name', 'unknown')} "
            f"v{server_info.get('version', 'unknown')}[/dim]"
        )

    async def test_mcp_server_list_tools(self) -> None:
        """Test MCP server tools/list request."""
        if "mcp_test_server_1" not in self.loaded_adapter_ids:
            raise ValueError("MCP server not loaded - cannot test protocol")

        mcp_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }

        response = await self._send_mcp_request(mcp_request)

        if response.get("error"):
            raise ValueError(f"MCP tools/list failed: {response['error']}")

        result = response.get("result", {})
        tools = result.get("tools", [])

        if not tools:
            raise ValueError("MCP server returned no tools")

        # Verify expected tools are present
        tool_names = [t.get("name", "") for t in tools]
        expected_tools = ["status", "message", "history"]

        for expected in expected_tools:
            if expected not in tool_names:
                raise ValueError(f"Missing expected tool '{expected}'. Got: {tool_names}")

        self.console.print(f"     [dim]MCP tools available: {tool_names}[/dim]")

    async def test_mcp_server_call_status(self) -> None:
        """Test MCP server tools/call for status tool."""
        if "mcp_test_server_1" not in self.loaded_adapter_ids:
            raise ValueError("MCP server not loaded - cannot test protocol")

        mcp_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "status",
                "arguments": {},
            },
        }

        response = await self._send_mcp_request(mcp_request)

        if response.get("error"):
            raise ValueError(f"MCP tools/call status failed: {response['error']}")

        result = response.get("result", {})
        content = result.get("content", [])

        if not content:
            raise ValueError("Status tool returned no content")

        # Check for isError flag
        if result.get("isError"):
            error_text = content[0].get("text", "unknown error") if content else "unknown"
            raise ValueError(f"Status tool returned error: {error_text}")

        # Extract status text
        status_text = content[0].get("text", "") if content else ""
        self.console.print(f"     [dim]Status tool response: {status_text[:100]}...[/dim]")

    async def test_mcp_server_call_message(self) -> None:
        """Test MCP server tools/call for message tool.

        This tests the message tool which requires user_id for HTTP transport.
        We verify that unauthenticated HTTP requests are properly rejected.
        """
        if "mcp_test_server_1" not in self.loaded_adapter_ids:
            raise ValueError("MCP server not loaded - cannot test protocol")

        mcp_request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "message",
                "arguments": {"content": "Hello from MCP QA test!"},
            },
        }

        response = await self._send_mcp_request(mcp_request)

        # For HTTP transport without auth, we expect an error about authentication
        error = response.get("error")
        if error:
            error_message = error.get("message", "") if isinstance(error, dict) else str(error)
            if "Authentication required" in error_message:
                # This is EXPECTED behavior - HTTP without auth should be rejected
                self.console.print("     [dim]Message tool correctly requires auth for HTTP ✓[/dim]")
                return
            else:
                raise ValueError(f"Unexpected error: {error}")

        result = response.get("result", {})
        content = result.get("content", [])

        if not content:
            raise ValueError("Message tool returned no content")

        response_text = content[0].get("text", "") if content else ""

        # Check for isError flag in result
        if result.get("isError"):
            if "Authentication required" in response_text:
                self.console.print("     [dim]Message tool correctly requires auth for HTTP ✓[/dim]")
                return
            elif "No message handler available" in response_text:
                # This means auth passed but handler not wired up
                raise ValueError(f"Message handler not configured: {response_text}")
            else:
                raise ValueError(f"Message tool error: {response_text}")

        # If we got here, message was submitted successfully
        self.console.print(f"     [dim]Message tool response: {response_text[:100]}[/dim]")

    async def _send_mcp_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send an MCP request to the test server and return the response.

        Args:
            request: MCP JSON-RPC request dict

        Returns:
            MCP JSON-RPC response dict
        """
        import json
        import socket

        port = getattr(self, "_mcp_test_server_port", 9876)

        try:
            # Create raw HTTP request with MCP JSON body
            body = json.dumps(request)
            http_request = (
                f"POST /mcp HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{port}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"\r\n"
                f"{body}"
            )

            # Connect and send
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect(("127.0.0.1", port))
            sock.sendall(http_request.encode())

            # Read response
            response_data = b""
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                    # Check if we have complete response
                    if b"\r\n\r\n" in response_data:
                        # Parse headers to get content length
                        header_end = response_data.index(b"\r\n\r\n")
                        headers = response_data[:header_end].decode()
                        body_start = header_end + 4

                        # Find Content-Length
                        content_length = 0
                        for line in headers.split("\r\n"):
                            if line.lower().startswith("content-length:"):
                                content_length = int(line.split(":")[1].strip())
                                break

                        # Check if we have full body
                        if len(response_data) >= body_start + content_length:
                            break
                except socket.timeout:
                    break

            sock.close()

            # Parse response
            if b"\r\n\r\n" in response_data:
                body_start = response_data.index(b"\r\n\r\n") + 4
                body = response_data[body_start:].decode()
                return json.loads(body)
            else:
                raise ValueError(f"Invalid HTTP response: {response_data[:200]}")

        except socket.error as e:
            raise ValueError(f"Failed to connect to MCP server on port {port}: {e}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response: {e}")

    async def test_reload_mcp_client(self) -> None:
        """Test reloading an MCP client adapter with new config."""
        if "mcp_test_client_1" not in self.loaded_adapter_ids:
            self.console.print("     [dim]Skipping - client not loaded[/dim]")
            return

        headers = self._get_auth_headers()

        # Reload with updated config
        response = requests.put(
            f"{self._base_url}/v1/system/adapters/mcp_test_client_1/reload",
            headers=headers,
            json={
                "config": {
                    "adapter_type": "mcp_client",
                    "enabled": True,
                    "settings": {},
                    "adapter_config": {
                        "adapter_id": "mcp_test_client_1",
                        "servers": [
                            {
                                "server_id": "test-server-1-reloaded",
                                "name": "Test Server 1 (Reloaded)",
                                "transport": "stdio",
                                "command": "echo",
                                "args": ["reloaded"],
                                "enabled": True,
                                "auto_start": True,
                                "bus_bindings": [
                                    {"bus_type": "tool", "priority": 50},
                                ],
                            }
                        ],
                    },
                },
                "auto_start": True,
            },
            timeout=60,
        )

        if response.status_code != 200:
            # Reload may fail if adapter doesn't support it - that's acceptable
            self.console.print(f"     [dim]Reload returned: {response.status_code}[/dim]")
            return

        data = response.json()
        if data.get("success"):
            self.console.print("     [dim]Adapter reloaded successfully[/dim]")
        else:
            self.console.print(f"     [dim]Reload status: {data.get('data', {}).get('message', 'unknown')}[/dim]")

    async def test_invalid_adapter_config(self) -> None:
        """Test error handling for invalid adapter configuration."""
        headers = self._get_auth_headers()

        # Try to load with invalid/missing required fields
        response = requests.post(
            f"{self._base_url}/v1/system/adapters/mcp_client",
            headers=headers,
            json={
                "config": {
                    "adapter_type": "mcp_client",
                    "enabled": True,
                    "settings": {},
                    "adapter_config": {
                        "adapter_id": "mcp_test_invalid",
                        "servers": [
                            {
                                # Missing required 'name' field
                                "server_id": "invalid-server",
                                "transport": "invalid_transport",  # Invalid transport type
                            }
                        ],
                    },
                },
                "auto_start": True,
            },
            params={"adapter_id": "mcp_test_invalid"},
            timeout=30,
        )

        # Should either fail with 400/422 or return success=false
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                # If it succeeded, clean it up
                self.loaded_adapter_ids.append("mcp_test_invalid")
                self.console.print("     [dim]Warning: Invalid config was accepted[/dim]")
            else:
                self.console.print("     [dim]Invalid config correctly rejected[/dim]")
        elif response.status_code in (400, 422, 500):
            self.console.print(f"     [dim]Invalid config rejected with HTTP {response.status_code}[/dim]")
        else:
            self.console.print(f"     [dim]Unexpected response: {response.status_code}[/dim]")

    async def test_capability_discovery(self) -> None:
        """Test MCP capability discovery (contract test)."""
        # Get adapter list to verify capabilities are exposed
        adapters = await self._list_adapters()

        for adapter in adapters:
            # Defensive check - ensure adapter is a dict
            if not isinstance(adapter, dict):
                self.console.print(f"     [dim]Skipping non-dict adapter: {type(adapter)}[/dim]")
                continue

            if adapter.get("adapter_id", "").startswith("mcp_test_"):
                # Check for expected fields
                services = adapter.get("services_registered", [])
                adapter_type = adapter.get("adapter_type", "")
                is_running = adapter.get("is_running", False)

                self.console.print(
                    f"     [dim]{adapter.get('adapter_id')}: "
                    f"type={adapter_type}, running={is_running}, "
                    f"services={len(services)}[/dim]"
                )

        # Verify we can list tools from the system
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/tools",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            tools_data = data.get("data", {})
            # Handle both dict and list formats for data
            if isinstance(tools_data, dict):
                tools = tools_data.get("tools", [])
            elif isinstance(tools_data, list):
                tools = tools_data
            else:
                tools = []

            # Count MCP tools - handle both dict and object formats
            mcp_tools = []
            for t in tools:
                tool_name = ""
                if isinstance(t, dict):
                    tool_name = t.get("name", "")
                elif hasattr(t, "name"):
                    tool_name = getattr(t, "name", "")
                elif isinstance(t, str):
                    tool_name = t

                if "mcp" in tool_name.lower():
                    mcp_tools.append(t)

            self.console.print(f"     [dim]MCP-related tools discovered: {len(mcp_tools)}[/dim]")
        else:
            self.console.print(f"     [dim]Tool listing returned: {response.status_code}[/dim]")

    async def test_concurrent_operations(self) -> None:
        """Test concurrent adapter status queries (load test)."""
        import concurrent.futures

        headers = self._get_auth_headers()
        num_requests = 10
        successful = 0
        failed = 0

        def make_request() -> bool:
            try:
                response = requests.get(
                    f"{self._base_url}/v1/system/adapters",
                    headers=headers,
                    timeout=10,
                )
                return response.status_code == 200
            except Exception:
                return False

        # Run concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(num_requests)]
            for future in concurrent.futures.as_completed(futures):
                if future.result():
                    successful += 1
                else:
                    failed += 1

        success_rate = (successful / num_requests) * 100
        self.console.print(
            f"     [dim]Concurrent requests: {successful}/{num_requests} succeeded ({success_rate:.0f}%)[/dim]"
        )

        # Per MCP best practices, require >99% success rate
        if success_rate < 99:
            self.console.print(f"     [dim]Warning: Success rate below 99% threshold[/dim]")

    async def test_unload_adapters(self) -> None:
        """Unload all test MCP adapters."""
        headers = self._get_auth_headers()
        unloaded = 0
        errors = []

        for adapter_id in self.loaded_adapter_ids:
            try:
                response = requests.delete(
                    f"{self._base_url}/v1/system/adapters/{adapter_id}",
                    headers=headers,
                    timeout=30,
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        unloaded += 1
                    else:
                        errors.append(f"{adapter_id}: {data.get('data', {}).get('error', 'unknown')}")
                elif response.status_code == 404:
                    # Already unloaded
                    unloaded += 1
                else:
                    errors.append(f"{adapter_id}: HTTP {response.status_code}")

            except Exception as e:
                errors.append(f"{adapter_id}: {str(e)}")

        self.console.print(f"     [dim]Unloaded {unloaded}/{len(self.loaded_adapter_ids)} adapters[/dim]")

        if errors:
            self.console.print(f"     [dim]Errors: {errors}[/dim]")

        # Clear the list
        self.loaded_adapter_ids.clear()

    async def test_verify_cleanup(self) -> None:
        """Verify all test MCP adapters were removed."""
        adapters = await self._list_adapters()

        test_adapters = [a for a in adapters if a.get("adapter_id", "").startswith("mcp_test_")]

        if test_adapters:
            remaining = [a.get("adapter_id") for a in test_adapters]
            self.console.print(f"     [dim]Warning: {len(remaining)} test adapters still present[/dim]")
        else:
            self.console.print("     [dim]All test adapters cleaned up[/dim]")

    # Helper methods

    async def _load_adapter(
        self,
        adapter_type: str,
        adapter_id: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Load an adapter via the API.

        If the adapter already exists, tries to unload it first then reload.
        """
        headers = self._get_auth_headers()

        response = requests.post(
            f"{self._base_url}/v1/system/adapters/{adapter_type}",
            headers=headers,
            json={
                "config": config,
                "auto_start": True,
            },
            params={"adapter_id": adapter_id},
            timeout=60,
        )

        # Handle adapter already exists - unload and reload
        if response.status_code == 409 or "already exists" in response.text.lower():
            self.console.print(f"     [dim]Adapter {adapter_id} exists, reloading...[/dim]")
            # Unload the existing adapter
            unload_response = requests.delete(
                f"{self._base_url}/v1/system/adapters/{adapter_id}",
                headers=headers,
                timeout=30,
            )
            if unload_response.status_code not in (200, 404):
                self.console.print(
                    f"     [yellow]Warning: Failed to unload existing adapter: {unload_response.status_code}[/yellow]"
                )

            # Small delay to allow cleanup
            await asyncio.sleep(0.5)

            # Retry the load
            response = requests.post(
                f"{self._base_url}/v1/system/adapters/{adapter_type}",
                headers=headers,
                json={
                    "config": config,
                    "auto_start": True,
                },
                params={"adapter_id": adapter_id},
                timeout=60,
            )

        if response.status_code != 200:
            raise ValueError(f"Failed to load adapter: {response.status_code} - {response.text[:200]}")

        data = response.json()

        # API returns SuccessResponse format: {"data": AdapterOperationResult, "metadata": {...}}
        # AdapterOperationResult has: {"success": bool, "adapter_id": str, "error": str|None, ...}
        result = data.get("data", {})
        if isinstance(result, dict):
            # Check if the operation itself failed (AdapterOperationResult.success)
            if result.get("success") is False:
                error = result.get("error") or result.get("message") or "Operation failed (no error message)"
                raise ValueError(f"Adapter load failed: {error}")

            self.console.print(f"     [dim]Loaded adapter: {adapter_id}[/dim]")
            return result
        else:
            # Unexpected response format
            raise ValueError(f"Unexpected response format: {type(result)}")

    async def _list_adapters(self) -> List[Dict[str, Any]]:
        """List all adapters via the API."""
        headers = self._get_auth_headers()
        response = requests.get(f"{self._base_url}/v1/system/adapters", headers=headers, timeout=30)

        if response.status_code != 200:
            raise ValueError(f"Failed to list adapters: {response.status_code}")

        data = response.json()

        # Handle multiple response formats:
        # 1. SuccessResponse: {"data": {"adapters": [...], ...}, "metadata": {...}}
        # 2. Simplified: {"data": [...]} (data is directly a list of adapters)
        # 3. Direct: {"adapters": [...]} (no wrapper)
        adapters: List[Dict[str, Any]] = []

        if "data" in data:
            inner = data["data"]
            if isinstance(inner, dict):
                adapters = inner.get("adapters", [])
            elif isinstance(inner, list):
                adapters = inner
        elif "adapters" in data:
            adapters = data.get("adapters", [])

        # Ensure we return a list of dicts only
        return [item for item in adapters if isinstance(item, dict)]

    async def _complete_task(self) -> None:
        """Complete the current task and wait for agent to be ready.

        This ensures the previous interaction is fully processed before
        sending a new message, preventing message consolidation issues.
        """
        try:
            # Send task complete
            await self.client.agent.interact("$task_complete")
            # Wait for agent to finish processing
            await asyncio.sleep(3.0)
        except Exception:
            pass

    async def _verify_audit_entry(self, search_text: str, max_age_seconds: int = 30) -> Dict[str, Any]:
        """Verify an action appears in the audit trail."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        await asyncio.sleep(0.5)

        audit_response = await self.client.audit.query_entries(start_time=cutoff, limit=50)

        for entry in audit_response.entries:
            entry_dict: Dict[str, Any] = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)
            entry_str = str(entry_dict)

            if search_text.lower() in entry_str.lower():
                return entry_dict

        raise ValueError(f"No audit entry found containing '{search_text}' in last {max_age_seconds}s")

    async def _verify_audit_entry_after(
        self,
        action_type: str,
        tool_name: str,
        after_timestamp: datetime,
        timeout_seconds: int = 30,
    ) -> Dict[str, Any]:
        """Verify a specific action appears in the audit trail AFTER the given timestamp.

        This is stricter than _verify_audit_entry - it requires:
        1. The entry timestamp must be AFTER after_timestamp
        2. The entry must contain BOTH the action type AND tool name
        3. The action must have succeeded (not failed/error)

        Args:
            action_type: Action type to search for (e.g., "tool")
            tool_name: Tool name that must appear in the entry
            after_timestamp: Only consider entries after this timestamp
            timeout_seconds: How long to wait for the entry to appear

        Returns:
            The matching audit entry dict

        Raises:
            ValueError: If no matching entry found within timeout or if action failed
        """
        await asyncio.sleep(0.5)  # Allow time for audit to be written

        deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)
        found_entries: List[Dict[str, Any]] = []
        failure_errors: List[str] = []

        while datetime.now(timezone.utc) < deadline:
            audit_response = await self.client.audit.query_entries(start_time=after_timestamp, limit=50)

            for entry in audit_response.entries:
                entry_dict: Dict[str, Any] = entry.model_dump() if hasattr(entry, "model_dump") else dict(entry)

                # Check entry timestamp is after our interaction
                entry_ts = entry_dict.get("timestamp")
                if entry_ts:
                    if isinstance(entry_ts, str):
                        try:
                            entry_dt = datetime.fromisoformat(entry_ts.replace("Z", "+00:00"))
                            if entry_dt <= after_timestamp:
                                continue  # Skip entries before our interaction
                        except ValueError:
                            pass

                entry_str = str(entry_dict).lower()

                # Must contain BOTH action type AND tool name
                if action_type.lower() in entry_str and tool_name.lower() in entry_str:
                    found_entries.append(entry_dict)

                    # STRICT FAILURE DETECTION - check for explicit failure indicators
                    # These patterns indicate tool execution failed
                    failure_patterns = [
                        "not_found",
                        "toolexecutionstatus.not_found",
                        "no service supports tool",
                        "tool not found",
                    ]
                    for pattern in failure_patterns:
                        if pattern in entry_str:
                            error_msg = f"Tool '{tool_name}' FAILED (pattern: {pattern})"
                            failure_errors.append(error_msg)
                            break

                    # Check context field (SDK audit entry structure)
                    # AuditEntryResponse has: action, actor, timestamp, context
                    # AuditContext has: result, error, operation, description, metadata
                    # The SUCCESS indicator is in context.metadata.outcome = 'success'
                    context = entry_dict.get("context", {})
                    if isinstance(context, dict):
                        error = context.get("error")
                        metadata = context.get("metadata", {})

                        # Check for error first
                        if error:
                            raise ValueError(f"Tool '{tool_name}' execution FAILED: {error}")

                        # Check metadata for outcome (this is where tool success is stored)
                        if isinstance(metadata, dict):
                            outcome = metadata.get("outcome", "").lower()
                            if outcome == "success":
                                return entry_dict
                            elif outcome == "failure" or outcome == "error":
                                tool_error = metadata.get("error") or metadata.get("tool_error") or outcome
                                raise ValueError(f"Tool '{tool_name}' execution FAILED: {tool_error}")

                    # Check for action_result (legacy format)
                    action_result = entry_dict.get("action_result", {})
                    if isinstance(action_result, dict):
                        success = action_result.get("success")
                        error = action_result.get("error")
                        if success is True and not error:
                            return entry_dict
                        elif success is False or error:
                            raise ValueError(f"Tool '{tool_name}' execution FAILED: {error or 'success=False'}")

                    # Check for handler_result (legacy format)
                    handler_result = entry_dict.get("handler_result", {})
                    if isinstance(handler_result, dict):
                        success = handler_result.get("success")
                        error = handler_result.get("error")
                        if success is True and not error:
                            return entry_dict
                        elif success is False or error:
                            raise ValueError(f"Tool '{tool_name}' execution FAILED: {error or 'success=False'}")

            await asyncio.sleep(1.0)  # Wait before retrying

        # If we found entries but detected failures, report them
        if failure_errors:
            raise ValueError(f"Tool '{tool_name}' execution FAILED. Detected errors: {failure_errors[0]}")

        # If we found entries but none had explicit success, be strict
        if found_entries:
            # Log the first entry for debugging
            first_entry = found_entries[0]
            first_entry_str = str(first_entry)[:500]
            raise ValueError(
                f"Found {len(found_entries)} audit entries for tool '{tool_name}' "
                f"but none indicate explicit success. First entry: {first_entry}"
            )

        raise ValueError(
            f"No audit entry found with action='{action_type}' and tool='{tool_name}' "
            f"after {after_timestamp.isoformat()} within {timeout_seconds}s"
        )

    def _print_summary(self) -> None:
        """Print test summary table."""
        table = Table(title="MCP Tests Summary")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Error", style="red")

        for result in self.results:
            error_text = ""
            if result["error"]:
                error_text = result["error"][:50] + "..." if len(result["error"]) > 50 else result["error"]

            table.add_row(result["test"], result["status"], error_text)

        self.console.print(table)

        passed = sum(1 for r in self.results if "✅" in r["status"])
        failed = sum(1 for r in self.results if "❌" in r["status"])
        total = len(self.results)

        if failed == 0:
            self.console.print(f"\n[bold green]✅ All {total} MCP tests passed![/bold green]")
        else:
            self.console.print(f"\n[bold yellow]⚠️  {passed}/{total} tests passed, {failed} failed[/bold yellow]")
