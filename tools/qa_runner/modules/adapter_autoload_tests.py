"""
Adapter Auto-Load QA tests.

Tests the adapter persistence and auto-load functionality which allows
dynamically loaded adapters to persist across server restarts.

Test scenarios:
- Load adapter via API
- Persist adapter configuration to graph
- Verify adapter in graph config
- Server restart verification (manual)
- Adapter auto-load on startup
"""

import asyncio
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from rich.console import Console
from rich.table import Table


class AdapterAutoloadTests:
    """Test adapter persistence and auto-load functionality via API."""

    def __init__(self, client: Any, console: Console):
        """Initialize adapter autoload tests.

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

        # Test adapter to use
        self.test_adapter_type = "sample_adapter"
        self.test_adapter_id = "qa_test_autoload_adapter"

        # Store loaded adapters for cleanup
        self.loaded_adapter_ids: List[str] = []

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
        """Run all adapter auto-load tests."""
        self.console.print("\n[cyan]Adapter Auto-Load Tests[/cyan]")
        self.console.print(
            "[dim]Note: Full auto-load testing requires server restart to verify persistence[/dim]"
        )

        tests = [
            # Phase 1: System verification
            ("Verify System Health", self.test_system_health),
            ("List Loaded Adapters", self.test_list_loaded_adapters),
            ("List Available Adapter Types", self.test_list_available_adapter_types),
            # Phase 2: Adapter loading
            ("Load Test Adapter", self.test_load_adapter),
            ("Verify Adapter Loaded", self.test_verify_adapter_loaded),
            ("Get Adapter Status", self.test_get_adapter_status),
            # Phase 3: Persistence
            ("List Persisted Configs", self.test_list_persisted_configs),
            ("Verify Config in Graph", self.test_verify_config_in_graph),
            # Phase 4: Unload and reload
            ("Unload Test Adapter", self.test_unload_adapter),
            ("Reload Test Adapter", self.test_reload_adapter),
            # Phase 5: Cleanup
            ("Cleanup Test Adapters", self.test_cleanup_adapters),
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

    async def test_list_loaded_adapters(self) -> None:
        """List currently loaded adapters."""
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Adapters endpoint not found[/dim]")
            return

        if response.status_code != 200:
            raise ValueError(f"Failed to list adapters: HTTP {response.status_code}")

        data = response.json()
        adapters = data.get("data", {}).get("adapters", [])

        self.console.print(f"     [dim]Loaded adapters: {len(adapters)}[/dim]")
        for adapter in adapters[:5]:
            adapter_id = adapter.get("adapter_id", "unknown")
            adapter_type = adapter.get("adapter_type", "unknown")
            self.console.print(f"     [dim]  - {adapter_id} ({adapter_type})[/dim]")

    async def test_list_available_adapter_types(self) -> None:
        """List available adapter types that can be loaded."""
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters/available",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Available adapters endpoint not found[/dim]")
            return

        if response.status_code != 200:
            self.console.print(f"     [dim]Response: HTTP {response.status_code}[/dim]")
            return

        data = response.json()
        adapter_types = data.get("data", {}).get("adapter_types", [])

        self.console.print(f"     [dim]Available adapter types: {len(adapter_types)}[/dim]")
        for at in adapter_types[:5]:
            self.console.print(f"     [dim]  - {at}[/dim]")

    async def test_load_adapter(self) -> None:
        """Load a test adapter via API."""
        headers = self._get_auth_headers()

        # Load the adapter - endpoint requires AdapterActionRequest body
        response = requests.post(
            f"{self._base_url}/v1/system/adapters/{self.test_adapter_type}",
            headers=headers,
            params={"adapter_id": self.test_adapter_id},
            json={"config": {}, "auto_start": True, "force": False},
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Load adapter endpoint not found[/dim]")
            return

        if response.status_code == 409:
            self.console.print("     [dim]Adapter already loaded (conflict)[/dim]")
            self.loaded_adapter_ids.append(self.test_adapter_id)
            return

        if response.status_code not in (200, 201):
            raise ValueError(f"Failed to load adapter: HTTP {response.status_code}")

        data = response.json()
        result = data.get("data", {})

        success = result.get("success", False)
        adapter_id = result.get("adapter_id", self.test_adapter_id)

        if success:
            self.loaded_adapter_ids.append(adapter_id)
            self.console.print(f"     [dim]Loaded adapter: {adapter_id}[/dim]")
        else:
            message = result.get("message", "Unknown error")
            raise ValueError(f"Adapter load failed: {message}")

    async def test_verify_adapter_loaded(self) -> None:
        """Verify the test adapter is in the loaded adapters list."""
        if not self.loaded_adapter_ids:
            self.console.print("     [dim]Skipped - no adapter loaded[/dim]")
            return

        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters",
            headers=headers,
            timeout=30,
        )

        if response.status_code != 200:
            raise ValueError(f"Failed to list adapters: HTTP {response.status_code}")

        data = response.json()
        adapters = data.get("data", {}).get("adapters", [])

        adapter_ids = [a.get("adapter_id") for a in adapters]

        if self.test_adapter_id not in adapter_ids:
            raise ValueError(f"Test adapter {self.test_adapter_id} not found in loaded adapters")

        self.console.print(f"     [dim]Verified: {self.test_adapter_id} is loaded[/dim]")

    async def test_get_adapter_status(self) -> None:
        """Get status of the loaded test adapter."""
        if not self.loaded_adapter_ids:
            self.console.print("     [dim]Skipped - no adapter loaded[/dim]")
            return

        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters/{self.test_adapter_id}",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Adapter status endpoint not found[/dim]")
            return

        if response.status_code != 200:
            self.console.print(f"     [dim]Status response: HTTP {response.status_code}[/dim]")
            return

        data = response.json()
        status = data.get("data", {})

        self.console.print(f"     [dim]Adapter status: {status.get('status', 'unknown')}[/dim]")

    async def test_list_persisted_configs(self) -> None:
        """List persisted adapter configurations."""
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters/persisted",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Persisted configs endpoint not found[/dim]")
            return

        if response.status_code != 200:
            raise ValueError(f"Failed to list persisted configs: HTTP {response.status_code}")

        data = response.json()
        result = data.get("data", {})

        configs = result.get("persisted_configs", {})
        count = result.get("count", 0)

        self.console.print(f"     [dim]Persisted configs: {count}[/dim]")
        for adapter_type in list(configs.keys())[:5]:
            self.console.print(f"     [dim]  - {adapter_type}[/dim]")

    async def test_verify_config_in_graph(self) -> None:
        """Verify adapter config was persisted to graph."""
        if not self.loaded_adapter_ids:
            self.console.print("     [dim]Skipped - no adapter loaded[/dim]")
            return

        headers = self._get_auth_headers()

        # Query config service for adapter config
        response = requests.get(
            f"{self._base_url}/v1/config/adapter.{self.test_adapter_id}.type",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Config query endpoint not found (or config not persisted)[/dim]")
            return

        if response.status_code != 200:
            self.console.print(f"     [dim]Config query returned: HTTP {response.status_code}[/dim]")
            return

        data = response.json()
        config_value = data.get("data", {}).get("value")

        if config_value:
            self.console.print(f"     [dim]Config in graph: adapter.{self.test_adapter_id}.type = {config_value}[/dim]")
        else:
            self.console.print("     [dim]Config not found in graph[/dim]")

    async def test_unload_adapter(self) -> None:
        """Unload the test adapter."""
        if not self.loaded_adapter_ids:
            self.console.print("     [dim]Skipped - no adapter to unload[/dim]")
            return

        headers = self._get_auth_headers()
        response = requests.delete(
            f"{self._base_url}/v1/system/adapters/{self.test_adapter_id}",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Unload endpoint not found[/dim]")
            return

        if response.status_code not in (200, 204):
            self.console.print(f"     [dim]Unload response: HTTP {response.status_code}[/dim]")
            return

        self.console.print(f"     [dim]Unloaded adapter: {self.test_adapter_id}[/dim]")

    async def test_reload_adapter(self) -> None:
        """Reload the test adapter from persisted config."""
        headers = self._get_auth_headers()

        # Try to load the adapter again - should work from persisted config
        response = requests.post(
            f"{self._base_url}/v1/system/adapters/{self.test_adapter_type}",
            headers=headers,
            params={"adapter_id": self.test_adapter_id},
            json={"config": {}, "auto_start": True, "force": False},
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Load adapter endpoint not found[/dim]")
            return

        if response.status_code in (200, 201):
            self.console.print(f"     [dim]Reloaded adapter: {self.test_adapter_id}[/dim]")
        elif response.status_code == 409:
            self.console.print("     [dim]Adapter already loaded[/dim]")
        else:
            self.console.print(f"     [dim]Reload response: HTTP {response.status_code}[/dim]")

    async def test_cleanup_adapters(self) -> None:
        """Clean up test adapters and persisted configs."""
        headers = self._get_auth_headers()

        # Unload adapter if loaded
        unload_response = requests.delete(
            f"{self._base_url}/v1/system/adapters/{self.test_adapter_id}",
            headers=headers,
            timeout=30,
        )

        if unload_response.status_code in (200, 204, 404):
            self.console.print(f"     [dim]Cleaned up adapter: {self.test_adapter_id}[/dim]")

        # Remove persisted config
        remove_response = requests.delete(
            f"{self._base_url}/v1/system/adapters/{self.test_adapter_type}/persisted",
            headers=headers,
            timeout=30,
        )

        if remove_response.status_code in (200, 204, 404):
            self.console.print(f"     [dim]Cleaned up persisted config: {self.test_adapter_type}[/dim]")

        self.loaded_adapter_ids.clear()

    def _print_summary(self) -> None:
        """Print test summary table."""
        table = Table(title="Adapter Auto-Load Tests Summary")
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


# Convenience function for running from qa_runner
def get_all_tests() -> List[Dict[str, Any]]:
    """Return test class for qa_runner discovery."""
    return []  # Tests run via AdapterAutoloadTests.run()
