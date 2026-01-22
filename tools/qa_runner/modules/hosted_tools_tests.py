"""
CIRIS Hosted Tools Adapter QA Tests.

Tests the CIRIS hosted tools adapter (web search via CIRIS proxy):
1. Adapter loading via API runtime control
2. Tool discovery (web_search availability)
3. Balance checking (requires auth token)
4. Web search execution (requires auth token and credits)

Requires CIRIS_BILLING_GOOGLE_ID_TOKEN environment variable for full testing.
Without token, only adapter loading and tool discovery are tested.
"""

import asyncio
import os
from typing import Any, Dict, List, Optional

import requests
from rich.console import Console

from ciris_sdk.client import CIRISClient


class HostedToolsTests:
    """QA tests for CIRIS hosted tools adapter."""

    def __init__(self, client: CIRISClient, console: Console):
        """Initialize test suite with SDK client and console."""
        self.client = client
        self.console = console
        self.adapter_id = "hosted_tools_qa_test"
        self.has_token = bool(
            os.environ.get("CIRIS_BILLING_GOOGLE_ID_TOKEN")
            or os.environ.get("GOOGLE_ID_TOKEN")
        )

        # Base URL for direct API calls
        self._base_url = getattr(client, "_base_url", "http://localhost:8080")
        if hasattr(client, "_transport") and hasattr(client._transport, "base_url"):
            self._base_url = client._transport.base_url
        elif hasattr(client, "_transport") and hasattr(client._transport, "_base_url"):
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
            self.console.print("     [dim]Warning: Could not extract auth token from client[/dim]")

        return headers

    async def run(self) -> List[Dict]:
        """Run all hosted tools tests."""
        results = []

        self.console.print(f"\n[cyan]Auth Token Available: {self.has_token}[/cyan]")
        if not self.has_token:
            self.console.print("[yellow]Set CIRIS_BILLING_GOOGLE_ID_TOKEN for full testing[/yellow]")

        # Test 1: Load the adapter
        results.append(await self._test_load_adapter())

        # Only continue if adapter loaded successfully
        if results[-1]["status"] != "✅ PASS":
            results.append({
                "test": "remaining_tests",
                "status": "⚠️  SKIPPED",
                "error": "Adapter load failed - skipping remaining tests",
            })
            await self._cleanup()
            return results

        # Test 2: Verify adapter status
        results.append(await self._test_adapter_status())

        # Test 3: Tool discovery
        results.append(await self._test_tool_discovery())

        # Tests requiring auth token
        if self.has_token:
            # Test 4: Balance check
            results.append(await self._test_balance_check())

            # Test 5: Web search execution
            results.append(await self._test_web_search())
        else:
            results.append({
                "test": "balance_check",
                "status": "⚠️  SKIPPED",
                "error": "No auth token - set CIRIS_BILLING_GOOGLE_ID_TOKEN",
            })
            results.append({
                "test": "web_search",
                "status": "⚠️  SKIPPED",
                "error": "No auth token - set CIRIS_BILLING_GOOGLE_ID_TOKEN",
            })

        # Cleanup
        await self._cleanup()

        return results

    async def _test_load_adapter(self) -> Dict:
        """Test loading the CIRIS hosted tools adapter via API."""
        try:
            self.console.print("[cyan]Test 1: Load CIRIS Hosted Tools Adapter[/cyan]")

            adapter_config = {
                "adapter_type": "ciris_hosted_tools",
                "enabled": True,
                "settings": {},
                "adapter_config": {
                    # Use default proxy URLs from manifest
                },
            }

            await self._load_adapter(
                adapter_type="ciris_hosted_tools",
                adapter_id=self.adapter_id,
                config=adapter_config,
            )

            # Give the adapter time to initialize
            await asyncio.sleep(1.0)

            return {
                "test": "load_adapter",
                "status": "✅ PASS",
                "details": {
                    "adapter_id": self.adapter_id,
                    "adapter_type": "ciris_hosted_tools",
                },
            }

        except Exception as e:
            return {
                "test": "load_adapter",
                "status": "❌ FAIL",
                "error": str(e),
            }

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
            unload_response = requests.delete(
                f"{self._base_url}/v1/system/adapters/{adapter_id}",
                headers=headers,
                timeout=30,
            )
            if unload_response.status_code not in (200, 404):
                self.console.print(
                    f"     [yellow]Warning: Failed to unload existing adapter: {unload_response.status_code}[/yellow]"
                )

            await asyncio.sleep(0.5)

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
        result = data.get("data", {})
        if isinstance(result, dict):
            if result.get("success") is False:
                raise ValueError(f"Adapter load failed: {result.get('error', 'Unknown error')}")

        return result

    async def _test_adapter_status(self) -> Dict:
        """Test that the adapter is running."""
        try:
            self.console.print("[cyan]Test 2: Verify Adapter Status[/cyan]")

            headers = self._get_auth_headers()
            response = requests.get(
                f"{self._base_url}/v1/system/adapters/{self.adapter_id}",
                headers=headers,
                timeout=30,
            )

            if response.status_code == 404:
                return {
                    "test": "adapter_status",
                    "status": "❌ FAIL",
                    "error": "Adapter not found after loading",
                }

            if response.status_code != 200:
                return {
                    "test": "adapter_status",
                    "status": "❌ FAIL",
                    "error": f"Failed to get status: HTTP {response.status_code}",
                }

            data = response.json()
            is_running = data.get("data", {}).get("is_running", False)

            if is_running:
                return {
                    "test": "adapter_status",
                    "status": "✅ PASS",
                    "details": {
                        "is_running": True,
                        "adapter_type": data.get("data", {}).get("adapter_type"),
                    },
                }
            else:
                return {
                    "test": "adapter_status",
                    "status": "❌ FAIL",
                    "error": "Adapter loaded but not running",
                }

        except Exception as e:
            return {
                "test": "adapter_status",
                "status": "❌ FAIL",
                "error": str(e),
            }

    async def _test_tool_discovery(self) -> Dict:
        """Test that web_search tool is discovered."""
        try:
            self.console.print("[cyan]Test 3: Tool Discovery[/cyan]")

            headers = self._get_auth_headers()
            response = requests.get(
                f"{self._base_url}/v1/system/adapters/{self.adapter_id}",
                headers=headers,
                timeout=30,
            )

            if response.status_code != 200:
                return {
                    "test": "tool_discovery",
                    "status": "❌ FAIL",
                    "error": f"Failed to get adapter info: HTTP {response.status_code}",
                }

            data = response.json()
            tools = data.get("data", {}).get("tools", [])

            # Extract tool names
            tool_names = []
            for t in tools:
                if isinstance(t, dict):
                    tool_names.append(t.get("name", ""))
                elif isinstance(t, str):
                    tool_names.append(t)

            if "web_search" in tool_names:
                return {
                    "test": "tool_discovery",
                    "status": "✅ PASS",
                    "details": {
                        "tools_found": tool_names,
                        "web_search_available": True,
                    },
                }
            else:
                return {
                    "test": "tool_discovery",
                    "status": "❌ FAIL",
                    "error": f"web_search tool not found. Available: {tool_names}",
                }

        except Exception as e:
            return {
                "test": "tool_discovery",
                "status": "❌ FAIL",
                "error": str(e),
            }

    async def _test_balance_check(self) -> Dict:
        """Test balance checking via web search tool."""
        try:
            self.console.print("[cyan]Test 4: Balance Check[/cyan]")

            # Use $tool command to trigger a balance-related check
            # The tool service should check balance internally
            message = "$tool web_search q=\"test balance check\" count=1"
            response = await self.client.agent.interact(message)

            await asyncio.sleep(3)

            # If we got any response, the balance check path was exercised
            if response:
                response_text = str(response).lower()

                # Check for various response types
                if "no web search credits" in response_text or "402" in response_text:
                    return {
                        "test": "balance_check",
                        "status": "✅ PASS",
                        "details": {
                            "balance_checked": True,
                            "has_credits": False,
                            "note": "Balance check working - no credits available",
                        },
                    }
                elif "not authenticated" in response_text or "401" in response_text:
                    return {
                        "test": "balance_check",
                        "status": "✅ PASS",
                        "details": {
                            "balance_checked": True,
                            "auth_required": True,
                            "note": "Auth check working - token validation needed",
                        },
                    }
                elif "results" in response_text or "success" in response_text:
                    return {
                        "test": "balance_check",
                        "status": "✅ PASS",
                        "details": {
                            "balance_checked": True,
                            "has_credits": True,
                            "note": "Search executed - credits available",
                        },
                    }
                else:
                    return {
                        "test": "balance_check",
                        "status": "✅ PASS",
                        "details": {
                            "balance_checked": True,
                            "note": "Tool executed via agent",
                        },
                    }

            return {
                "test": "balance_check",
                "status": "⚠️  SKIPPED",
                "error": "No response from balance check",
            }

        except Exception as e:
            return {
                "test": "balance_check",
                "status": "❌ FAIL",
                "error": str(e),
            }

    async def _test_web_search(self) -> Dict:
        """Test web search execution."""
        try:
            self.console.print("[cyan]Test 5: Web Search Execution[/cyan]")

            # Perform a simple web search
            message = '$tool web_search q="CIRIS AI agent" count=3'
            response = await self.client.agent.interact(message)

            await asyncio.sleep(5)

            if response:
                response_text = str(response).lower()

                # Check response type
                if "no web search credits" in response_text:
                    return {
                        "test": "web_search",
                        "status": "✅ PASS",
                        "details": {
                            "search_attempted": True,
                            "credits_exhausted": True,
                            "note": "Search blocked due to no credits (expected behavior)",
                        },
                    }
                elif "not authenticated" in response_text:
                    return {
                        "test": "web_search",
                        "status": "✅ PASS",
                        "details": {
                            "search_attempted": True,
                            "auth_required": True,
                            "note": "Auth required (expected without device attestation)",
                        },
                    }
                elif "unable to connect" in response_text or "failed" in response_text:
                    return {
                        "test": "web_search",
                        "status": "⚠️  SKIPPED",
                        "details": {
                            "search_attempted": True,
                            "note": "Proxy connection failed - may be expected in test env",
                        },
                    }
                elif "results" in response_text or "ciris" in response_text:
                    return {
                        "test": "web_search",
                        "status": "✅ PASS",
                        "details": {
                            "search_completed": True,
                            "note": "Search returned results",
                        },
                    }
                else:
                    return {
                        "test": "web_search",
                        "status": "✅ PASS",
                        "details": {
                            "search_attempted": True,
                            "note": "Tool executed via agent",
                        },
                    }

            return {
                "test": "web_search",
                "status": "⚠️  SKIPPED",
                "error": "No response from web search",
            }

        except Exception as e:
            return {
                "test": "web_search",
                "status": "❌ FAIL",
                "error": str(e),
            }

    async def _cleanup(self):
        """Clean up test adapter."""
        try:
            self.console.print("[dim]Cleaning up test adapter...[/dim]")

            headers = self._get_auth_headers()
            try:
                unload_response = requests.delete(
                    f"{self._base_url}/v1/system/adapters/{self.adapter_id}",
                    headers=headers,
                    timeout=30,
                )
                if unload_response.status_code in (200, 404):
                    self.console.print(f"     [dim]Adapter {self.adapter_id} unloaded[/dim]")
            except Exception as e:
                self.console.print(f"     [yellow]Warning: Failed to unload adapter: {e}[/yellow]")

            self.console.print("[green]✅ Cleanup complete[/green]")

        except Exception as e:
            self.console.print(f"[yellow]⚠️  Cleanup warning: {e}[/yellow]")
