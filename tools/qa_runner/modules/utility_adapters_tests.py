"""
Utility Adapters QA Tests.

Tests the weather and navigation adapters:
1. Adapter loading via API
2. Tool registration verification
3. Basic tool execution (uses free public APIs)

These adapters use free APIs (NOAA, OpenStreetMap) requiring no API keys.
"""

import asyncio
from typing import Any, Dict, List

import requests
from rich.console import Console

from ciris_sdk.client import CIRISClient


class UtilityAdaptersTests:
    """QA tests for weather and navigation adapters."""

    def __init__(self, client: CIRISClient, console: Console):
        """Initialize test suite."""
        self.client = client
        self.console = console

        # Base URL for direct API calls
        self._base_url = getattr(client, "_base_url", "http://localhost:8080")
        if hasattr(client, "_transport") and hasattr(client._transport, "base_url"):
            self._base_url = client._transport.base_url
        elif hasattr(client, "_transport") and hasattr(client._transport, "_base_url"):
            self._base_url = client._transport._base_url

        # Track loaded adapters for cleanup
        self._loaded_adapters: List[str] = []

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
        return headers

    async def run(self) -> List[Dict]:
        """Run all utility adapter tests."""
        results = []

        # Weather adapter tests
        results.append(await self._test_load_weather_adapter())
        if results[-1]["status"] == "✅ PASS":
            results.append(await self._test_weather_tool_registration())

        # Navigation adapter tests
        results.append(await self._test_load_navigation_adapter())
        if results[-1]["status"] == "✅ PASS":
            results.append(await self._test_navigation_tool_registration())

        # Cleanup
        await self._cleanup()

        return results

    async def _load_adapter(
        self,
        adapter_type: str,
        adapter_id: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Load an adapter via the API."""
        headers = self._get_auth_headers()

        response = requests.post(
            f"{self._base_url}/v1/system/adapters/{adapter_type}",
            headers=headers,
            json={"config": config, "auto_start": True},
            params={"adapter_id": adapter_id},
            timeout=60,
        )

        # Handle adapter already exists
        if response.status_code == 409 or "already exists" in response.text.lower():
            self.console.print(f"     [dim]Adapter {adapter_id} exists, reloading...[/dim]")
            requests.delete(
                f"{self._base_url}/v1/system/adapters/{adapter_id}",
                headers=headers,
                timeout=30,
            )
            await asyncio.sleep(0.5)
            response = requests.post(
                f"{self._base_url}/v1/system/adapters/{adapter_type}",
                headers=headers,
                json={"config": config, "auto_start": True},
                params={"adapter_id": adapter_id},
                timeout=60,
            )

        if response.status_code != 200:
            raise ValueError(f"Failed to load adapter: {response.status_code} - {response.text[:200]}")

        self._loaded_adapters.append(adapter_id)
        return response.json().get("data", {})

    async def _test_load_weather_adapter(self) -> Dict:
        """Test loading the weather adapter."""
        try:
            self.console.print("[cyan]Test 1: Load Weather Adapter[/cyan]")

            await self._load_adapter(
                adapter_type="weather",
                adapter_id="weather_qa_test",
                config={
                    "adapter_type": "weather",
                    "enabled": True,
                    "adapter_config": {
                        "noaa_user_agent": "CIRIS-QA-Test/1.0 (qa@ciris.ai)",
                    },
                },
            )
            await asyncio.sleep(1.0)

            return {
                "test": "load_weather_adapter",
                "status": "✅ PASS",
                "details": {"adapter_id": "weather_qa_test"},
            }
        except Exception as e:
            return {
                "test": "load_weather_adapter",
                "status": "❌ FAIL",
                "error": str(e),
            }

    async def _test_weather_tool_registration(self) -> Dict:
        """Test that weather tools are registered in the system."""
        try:
            self.console.print("[cyan]Test 2: Weather Tool Registration[/cyan]")

            headers = self._get_auth_headers()

            # Check adapter status first
            adapter_response = requests.get(
                f"{self._base_url}/v1/system/adapters/weather_qa_test",
                headers=headers,
                timeout=30,
            )

            if adapter_response.status_code != 200:
                return {
                    "test": "weather_tool_registration",
                    "status": "❌ FAIL",
                    "error": f"Failed to get adapter info: HTTP {adapter_response.status_code}",
                }

            adapter_data = adapter_response.json().get("data", {})
            services = adapter_data.get("services_registered", [])

            # Check for weather tool service registration
            has_weather_service = any("WeatherToolService" in s for s in services)

            # Also check global tools list for weather tools
            tools_response = requests.get(
                f"{self._base_url}/v1/system/tools",
                headers=headers,
                timeout=30,
            )

            tool_names = []
            if tools_response.status_code == 200:
                tools_data = tools_response.json()
                if isinstance(tools_data, list):
                    tool_names = [t.get("name", "") if isinstance(t, dict) else str(t) for t in tools_data]
                else:
                    tools_list = tools_data.get("data", tools_data.get("tools", []))
                    tool_names = [t.get("name", "") if isinstance(t, dict) else str(t) for t in tools_list]

            # Look for weather-related tools
            weather_tools = [t for t in tool_names if "weather" in t.lower() or "forecast" in t.lower()]

            if has_weather_service:
                return {
                    "test": "weather_tool_registration",
                    "status": "✅ PASS",
                    "details": {
                        "services_registered": services,
                        "weather_tools_found": weather_tools if weather_tools else "Service registered, tools via ToolBus",
                    },
                }
            else:
                return {
                    "test": "weather_tool_registration",
                    "status": "❌ FAIL",
                    "error": f"WeatherToolService not found. Services: {services}",
                }
        except Exception as e:
            return {
                "test": "weather_tool_registration",
                "status": "❌ FAIL",
                "error": str(e),
            }

    async def _test_load_navigation_adapter(self) -> Dict:
        """Test loading the navigation adapter."""
        try:
            self.console.print("[cyan]Test 3: Load Navigation Adapter[/cyan]")

            await self._load_adapter(
                adapter_type="navigation",
                adapter_id="navigation_qa_test",
                config={
                    "adapter_type": "navigation",
                    "enabled": True,
                    "adapter_config": {
                        "osm_user_agent": "CIRIS-QA-Test/1.0 (qa@ciris.ai)",
                    },
                },
            )
            await asyncio.sleep(1.0)

            return {
                "test": "load_navigation_adapter",
                "status": "✅ PASS",
                "details": {"adapter_id": "navigation_qa_test"},
            }
        except Exception as e:
            return {
                "test": "load_navigation_adapter",
                "status": "❌ FAIL",
                "error": str(e),
            }

    async def _test_navigation_tool_registration(self) -> Dict:
        """Test that navigation tools are registered in the system."""
        try:
            self.console.print("[cyan]Test 4: Navigation Tool Registration[/cyan]")

            headers = self._get_auth_headers()

            # Check adapter status first
            adapter_response = requests.get(
                f"{self._base_url}/v1/system/adapters/navigation_qa_test",
                headers=headers,
                timeout=30,
            )

            if adapter_response.status_code != 200:
                return {
                    "test": "navigation_tool_registration",
                    "status": "❌ FAIL",
                    "error": f"Failed to get adapter info: HTTP {adapter_response.status_code}",
                }

            adapter_data = adapter_response.json().get("data", {})
            services = adapter_data.get("services_registered", [])

            # Check for navigation tool service registration
            has_nav_service = any("NavigationToolService" in s for s in services)

            # Also check global tools list for navigation tools
            tools_response = requests.get(
                f"{self._base_url}/v1/system/tools",
                headers=headers,
                timeout=30,
            )

            tool_names = []
            if tools_response.status_code == 200:
                tools_data = tools_response.json()
                if isinstance(tools_data, list):
                    tool_names = [t.get("name", "") if isinstance(t, dict) else str(t) for t in tools_data]
                else:
                    tools_list = tools_data.get("data", tools_data.get("tools", []))
                    tool_names = [t.get("name", "") if isinstance(t, dict) else str(t) for t in tools_list]

            # Look for navigation-related tools
            nav_tools = [t for t in tool_names if "geocode" in t.lower() or "route" in t.lower() or "navigation" in t.lower()]

            if has_nav_service:
                return {
                    "test": "navigation_tool_registration",
                    "status": "✅ PASS",
                    "details": {
                        "services_registered": services,
                        "navigation_tools_found": nav_tools if nav_tools else "Service registered, tools via ToolBus",
                    },
                }
            else:
                return {
                    "test": "navigation_tool_registration",
                    "status": "❌ FAIL",
                    "error": f"NavigationToolService not found. Services: {services}",
                }
        except Exception as e:
            return {
                "test": "navigation_tool_registration",
                "status": "❌ FAIL",
                "error": str(e),
            }

    async def _cleanup(self):
        """Clean up test adapters."""
        self.console.print("[dim]Cleaning up test adapters...[/dim]")
        headers = self._get_auth_headers()

        for adapter_id in self._loaded_adapters:
            try:
                requests.delete(
                    f"{self._base_url}/v1/system/adapters/{adapter_id}",
                    headers=headers,
                    timeout=30,
                )
                self.console.print(f"     [dim]Adapter {adapter_id} unloaded[/dim]")
            except Exception as e:
                self.console.print(f"     [yellow]Warning: Failed to unload {adapter_id}: {e}[/yellow]")

        self.console.print("[green]✅ Cleanup complete[/green]")
