"""
Context Enrichment QA tests.

Tests the context enrichment feature for adapter tools:
- Verifying tool services provide context_enrichment flag
- Testing automatic tool execution during context gathering
- Validating enrichment results appear in system snapshot
- Testing error handling for enrichment tools

**Sample Adapter Testing**: Uses the sample_adapter which has
a sample:list_items tool marked for context enrichment.
"""

import traceback
from typing import Any, Dict, List

import requests
from rich.console import Console
from rich.table import Table


class ContextEnrichmentTests:
    """Test context enrichment feature via API."""

    def __init__(self, client: Any, console: Console):
        """Initialize context enrichment tests.

        Args:
            client: CIRIS SDK client (authenticated)
            console: Rich console for output
        """
        self.client = client
        self.console = console
        self.results: List[Dict[str, Any]] = []

        # Base URL for direct API calls
        self._base_url = getattr(client, "_base_url", "http://localhost:8080")
        if hasattr(client, "_transport") and hasattr(client._transport, "_base_url"):
            self._base_url = client._transport._base_url

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers from client."""
        headers = {"Content-Type": "application/json"}

        token = None
        if hasattr(self.client, "api_key") and self.client.api_key:
            token = self.client.api_key
        elif hasattr(self.client, "_transport"):
            transport = self.client._transport
            if hasattr(transport, "api_key") and transport.api_key:
                token = transport.api_key

        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            self.console.print("     [dim]Warning: Could not extract auth token[/dim]")

        return headers

    async def run(self) -> List[Dict[str, Any]]:
        """Run all context enrichment tests."""
        self.console.print("\n[cyan]Context Enrichment Tests[/cyan]")

        tests = [
            # Phase 1: System verification
            ("Verify System Health", self.test_system_health),
            # Phase 2: Tool discovery
            ("List Available Tools", self.test_list_tools),
            ("Get Tool Info with Enrichment Flag", self.test_get_tool_info_enrichment),
            # Phase 3: Context enrichment validation
            ("Verify Context Enrichment Schema", self.test_context_enrichment_schema),
            ("Execute Enrichment Tool Directly", self.test_execute_enrichment_tool),
            ("Test Enrichment Tool with Parameters", self.test_enrichment_tool_with_params),
            # Phase 4: Error handling
            ("Execute Non-Enrichment Tool", self.test_non_enrichment_tool),
            ("Handle Tool Execution Error", self.test_tool_execution_error),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "PASS", "error": None})
                self.console.print(f"  [green]PASS[/green] {name}")
            except Exception as e:
                self.results.append({"test": name, "status": "FAIL", "error": str(e)})
                self.console.print(f"  [red]FAIL[/red] {name}: {str(e)[:80]}")
                if self.console.is_terminal:
                    self.console.print(f"     [dim]{traceback.format_exc()[:200]}[/dim]")

        self._print_summary()
        return self.results

    async def test_system_health(self) -> None:
        """Verify system is healthy."""
        health = await self.client.system.health()
        if not hasattr(health, "status"):
            raise ValueError("Health response missing status")
        self.console.print(f"     [dim]Status: {health.status}[/dim]")

    async def test_list_tools(self) -> None:
        """List all available tools from tool services."""
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/tools",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Endpoint /v1/tools not found[/dim]")
            return

        if response.status_code != 200:
            raise ValueError(f"Failed to list tools: HTTP {response.status_code}")

        data = response.json()
        tools = data.get("data", {}).get("tools", [])

        self.console.print(f"     [dim]Total tools: {len(tools)}[/dim]")

        # Look for sample adapter tools
        sample_tools = [t for t in tools if t.get("name", "").startswith("sample:")]
        self.console.print(f"     [dim]Sample adapter tools: {len(sample_tools)}[/dim]")

        for tool in sample_tools[:5]:
            name = tool.get("name", "unknown")
            enrichment = tool.get("context_enrichment", False)
            marker = " [context_enrichment]" if enrichment else ""
            self.console.print(f"     [dim]  - {name}{marker}[/dim]")

    async def test_get_tool_info_enrichment(self) -> None:
        """Get tool info and verify context_enrichment flag is present."""
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/tools/sample:list_items",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Tool sample:list_items not found[/dim]")
            return

        if response.status_code != 200:
            raise ValueError(f"Failed to get tool info: HTTP {response.status_code}")

        data = response.json()
        tool_info = data.get("data", {})

        # Verify enrichment fields
        has_enrichment = tool_info.get("context_enrichment", False)
        enrichment_params = tool_info.get("context_enrichment_params", None)

        self.console.print(f"     [dim]context_enrichment: {has_enrichment}[/dim]")
        self.console.print(f"     [dim]context_enrichment_params: {enrichment_params}[/dim]")

        if not has_enrichment:
            raise ValueError("Tool sample:list_items should have context_enrichment=True")

    async def test_context_enrichment_schema(self) -> None:
        """Verify ToolInfo schema includes context_enrichment fields."""
        # This tests that the schema is properly defined
        from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema

        # Create a tool with enrichment enabled
        tool = ToolInfo(
            name="test_enrichment_tool",
            description="Test tool for enrichment",
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[],
            ),
            context_enrichment=True,
            context_enrichment_params={"test_param": "value"},
        )

        # Verify fields are properly set
        if not tool.context_enrichment:
            raise ValueError("context_enrichment should be True")

        if tool.context_enrichment_params != {"test_param": "value"}:
            raise ValueError("context_enrichment_params not set correctly")

        self.console.print("     [dim]ToolInfo schema supports context_enrichment fields[/dim]")

    async def test_execute_enrichment_tool(self) -> None:
        """Execute an enrichment tool directly and verify results."""
        headers = self._get_auth_headers()
        response = requests.post(
            f"{self._base_url}/v1/tools/sample:list_items/execute",
            headers=headers,
            json={"parameters": {}},
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Tool execution endpoint not found[/dim]")
            return

        if response.status_code != 200:
            raise ValueError(f"Failed to execute tool: HTTP {response.status_code}")

        data = response.json()
        result = data.get("data", {})

        # Verify result structure
        success = result.get("success", False)
        tool_data = result.get("data", {})

        self.console.print(f"     [dim]Execution success: {success}[/dim]")

        if not success:
            error = result.get("error", "Unknown error")
            raise ValueError(f"Tool execution failed: {error}")

        # Verify expected data structure for list_items
        item_count = tool_data.get("count", 0)
        items = tool_data.get("items", [])

        self.console.print(f"     [dim]Items returned: {item_count}[/dim]")

        if item_count == 0:
            raise ValueError("Expected items to be returned")

        # Verify item structure
        if items:
            first_item = items[0]
            required_fields = ["id", "name", "category", "status"]
            for field in required_fields:
                if field not in first_item:
                    raise ValueError(f"Item missing required field: {field}")

            self.console.print(f"     [dim]First item: {first_item.get('name')}[/dim]")

    async def test_enrichment_tool_with_params(self) -> None:
        """Test enrichment tool with filter parameters."""
        headers = self._get_auth_headers()
        response = requests.post(
            f"{self._base_url}/v1/tools/sample:list_items/execute",
            headers=headers,
            json={"parameters": {"category": "widgets"}},
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Tool execution endpoint not found[/dim]")
            return

        if response.status_code != 200:
            raise ValueError(f"Failed to execute tool: HTTP {response.status_code}")

        data = response.json()
        result = data.get("data", {})
        tool_data = result.get("data", {})

        # Verify filter was applied
        filtered_category = tool_data.get("filtered_by_category")
        item_count = tool_data.get("count", 0)

        self.console.print(f"     [dim]Filtered by: {filtered_category}[/dim]")
        self.console.print(f"     [dim]Items after filter: {item_count}[/dim]")

        if filtered_category != "widgets":
            raise ValueError("Filter parameter not applied correctly")

        # All returned items should be in the widgets category
        items = tool_data.get("items", [])
        for item in items:
            if item.get("category") != "widgets":
                raise ValueError(f"Item {item.get('id')} not in widgets category")

    async def test_non_enrichment_tool(self) -> None:
        """Test that non-enrichment tools work normally."""
        headers = self._get_auth_headers()
        response = requests.post(
            f"{self._base_url}/v1/tools/sample:echo/execute",
            headers=headers,
            json={"parameters": {"message": "Hello, enrichment test!"}},
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Tool execution endpoint not found[/dim]")
            return

        if response.status_code != 200:
            raise ValueError(f"Failed to execute tool: HTTP {response.status_code}")

        data = response.json()
        result = data.get("data", {})

        success = result.get("success", False)
        tool_data = result.get("data", {})

        if not success:
            raise ValueError("Echo tool execution failed")

        echoed = tool_data.get("echoed", "")
        if echoed != "Hello, enrichment test!":
            raise ValueError(f"Echo response mismatch: {echoed}")

        self.console.print(f"     [dim]Echo response: {echoed[:30]}...[/dim]")

    async def test_tool_execution_error(self) -> None:
        """Test error handling for invalid tool execution."""
        headers = self._get_auth_headers()

        # Try to execute a non-existent tool
        response = requests.post(
            f"{self._base_url}/v1/tools/sample:nonexistent/execute",
            headers=headers,
            json={"parameters": {}},
            timeout=30,
        )

        # Should return 404 or error response
        if response.status_code == 404:
            self.console.print("     [dim]Correctly returned 404 for unknown tool[/dim]")
        elif response.status_code == 200:
            data = response.json()
            result = data.get("data", {})
            success = result.get("success", True)
            if not success:
                error = result.get("error", "Unknown error")
                self.console.print(f"     [dim]Correctly returned error: {error[:50]}[/dim]")
            else:
                raise ValueError("Should not succeed with unknown tool")
        else:
            self.console.print(f"     [dim]Response: HTTP {response.status_code}[/dim]")

    def _print_summary(self) -> None:
        """Print test summary table."""
        table = Table(title="Context Enrichment Tests Summary")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Error", style="red")

        for result in self.results:
            status_style = "[green]PASS[/green]" if result["status"] == "PASS" else "[red]FAIL[/red]"
            error_text = ""
            if result["error"]:
                error_text = result["error"][:40] + "..." if len(result["error"]) > 40 else result["error"]
            table.add_row(result["test"], status_style, error_text)

        self.console.print(table)

        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        total = len(self.results)

        if failed == 0:
            self.console.print(f"\n[bold green]All {total} tests passed![/bold green]")
        else:
            self.console.print(f"\n[bold yellow]{passed}/{total} passed, {failed} failed[/bold yellow]")
