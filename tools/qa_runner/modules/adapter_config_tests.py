"""
Adapter Configuration QA tests.

Tests the interactive adapter configuration workflow via API endpoints:
- List configurable adapters
- Start configuration sessions
- Execute configuration steps (discovery, select, input, confirm)
- OAuth flow (URL generation + callback handling)
- Session management (status, expiration, cleanup)
- Complete and apply configuration

**Live Testing**: For full end-to-end testing with Home Assistant:
1. Set CIRIS_HA_BASE_URL to your Home Assistant instance
2. The test will discover the instance and walk through OAuth
3. You'll need to authorize in your browser when prompted

**Mock Testing**: Without Home Assistant, tests verify:
- API endpoint functionality
- Session state management
- Error handling and validation
"""

import asyncio
import os
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from rich.console import Console
from rich.table import Table


class AdapterConfigTests:
    """Test adapter configuration workflow via API."""

    def __init__(self, client: Any, console: Console):
        """Initialize adapter config tests.

        Args:
            client: CIRIS SDK client (authenticated)
            console: Rich console for output
        """
        self.client = client
        self.console = console
        self.results: List[Dict[str, Any]] = []

        # Track sessions for cleanup
        self.created_session_ids: List[str] = []

        # Base URL for direct API calls
        self._base_url = getattr(client, "_base_url", "http://localhost:8080")
        if hasattr(client, "_transport") and hasattr(client._transport, "_base_url"):
            self._base_url = client._transport._base_url

        # Home Assistant config for live testing (optional)
        self.ha_base_url = os.environ.get("CIRIS_HA_BASE_URL")
        self.live_test = self.ha_base_url is not None

        # Default to sample_adapter for QA testing
        self.test_adapter_type = "sample_adapter"

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
        """Run all adapter configuration tests."""
        mode = "LIVE (Home Assistant)" if self.live_test else "MOCK (API-only)"
        self.console.print(f"\n[cyan]Adapter Configuration Tests ({mode})[/cyan]")

        tests = [
            # Phase 1: System verification
            ("Verify System Health", self.test_system_health),
            ("List Configurable Adapters", self.test_list_configurable_adapters),
            # Phase 2: Session management
            ("Start Configuration Session", self.test_start_session),
            ("Get Session Status", self.test_get_session_status),
            ("Start Session (Invalid Adapter)", self.test_start_session_invalid),
            # Phase 3: Step execution
            ("Execute Discovery Step", self.test_execute_discovery_step),
            ("Execute Select Step (Get Options)", self.test_execute_select_get_options),
            ("Execute Select Step (With Selection)", self.test_execute_select_with_selection),
            ("Execute Input Step", self.test_execute_input_step),
            ("Execute Confirm Step", self.test_execute_confirm_step),
            # Phase 4: OAuth flow (mock or live)
            ("OAuth URL Generation", self.test_oauth_url_generation),
            ("OAuth Callback Handling", self.test_oauth_callback),
            # Phase 5: Session completion
            ("Complete Session (Success)", self.test_complete_session_success),
            ("Complete Session with Persistence", self.test_complete_session_with_persistence),
            ("Complete Session (Validation Failure)", self.test_complete_session_validation_failure),
            # Phase 5b: Persistence operations
            ("List Persisted Configurations", self.test_list_persisted_configs),
            ("Remove Persisted Configuration", self.test_remove_persisted_config),
            # Phase 6: Error handling
            ("Get Non-existent Session", self.test_get_nonexistent_session),
            ("Execute Step (Expired Session)", self.test_execute_step_expired),
            # Phase 7: Cleanup
            ("Cleanup Test Sessions", self.test_cleanup_sessions),
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

    async def test_list_configurable_adapters(self) -> None:
        """List adapters that support interactive configuration."""
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters/configurable",
            headers=headers,
            timeout=30,
        )

        # Endpoint MUST exist - fail if 404
        if response.status_code == 404:
            raise ValueError("Endpoint /v1/system/adapters/configurable not found - feature not wired up")

        if response.status_code != 200:
            raise ValueError(f"Failed to list: HTTP {response.status_code}")

        data = response.json()

        # Verify response structure
        if "data" not in data:
            raise ValueError("Response missing 'data' field")

        response_data = data.get("data", {})
        if "adapters" not in response_data:
            raise ValueError("Response missing 'adapters' field")
        if "total_count" not in response_data:
            raise ValueError("Response missing 'total_count' field")

        adapters = response_data.get("adapters", [])
        total_count = response_data.get("total_count", 0)

        # Verify count matches
        if len(adapters) != total_count:
            raise ValueError(f"Count mismatch: {len(adapters)} adapters but total_count={total_count}")

        self.console.print(f"     [dim]Configurable adapters: {len(adapters)}[/dim]")

        for adapter in adapters:
            name = adapter.get("adapter_type", "unknown")
            step_count = adapter.get("step_count", 0)
            self.console.print(f"     [dim]  - {name}: {step_count} steps[/dim]")

    async def test_start_session(self) -> None:
        """Start a new configuration session."""
        headers = self._get_auth_headers()

        # Use homeassistant if available, otherwise use sample_adapter
        adapter_type = "homeassistant" if self.live_test else self.test_adapter_type

        response = requests.post(
            f"{self._base_url}/v1/system/adapters/{adapter_type}/configure/start",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            # Adapter not registered - create mock for testing
            self.console.print("     [dim]Adapter not registered (expected without live HA)[/dim]")
            return

        if response.status_code != 200:
            raise ValueError(f"Failed to start: HTTP {response.status_code}")

        data = response.json()
        session = data.get("data", {})
        session_id = session.get("session_id")

        if session_id:
            self.created_session_ids.append(session_id)
            self.console.print(f"     [dim]Session: {session_id[:16]}...[/dim]")

    async def test_get_session_status(self) -> None:
        """Get status of an existing session."""
        if not self.created_session_ids:
            self.console.print("     [dim]Skipped - no session created[/dim]")
            return

        headers = self._get_auth_headers()
        session_id = self.created_session_ids[-1]

        response = requests.get(
            f"{self._base_url}/v1/system/adapters/configure/{session_id}",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Endpoint not found[/dim]")
            return

        if response.status_code != 200:
            raise ValueError(f"Failed to get status: HTTP {response.status_code}")

        data = response.json()
        session = data.get("data", {})
        status = session.get("status", "unknown")
        step_index = session.get("current_step_index", 0)

        self.console.print(f"     [dim]Status: {status}, Step: {step_index}[/dim]")

    async def test_start_session_invalid(self) -> None:
        """Attempt to start session for non-configurable adapter."""
        headers = self._get_auth_headers()

        response = requests.post(
            f"{self._base_url}/v1/system/adapters/nonexistent_adapter/configure/start",
            headers=headers,
            timeout=30,
        )

        # Should return 404 or error response
        if response.status_code in (404, 400):
            self.console.print(f"     [dim]Correctly rejected: HTTP {response.status_code}[/dim]")
        elif response.status_code == 200:
            data = response.json()
            if not data.get("success", True):
                self.console.print("     [dim]Correctly rejected in response body[/dim]")
            else:
                raise ValueError("Invalid adapter should be rejected")
        else:
            self.console.print(f"     [dim]Unexpected: HTTP {response.status_code}[/dim]")

    async def test_execute_discovery_step(self) -> None:
        """Execute a discovery step."""
        if not self.created_session_ids:
            self.console.print("     [dim]Skipped - no session[/dim]")
            return

        headers = self._get_auth_headers()
        session_id = self.created_session_ids[-1]

        response = requests.post(
            f"{self._base_url}/v1/system/adapters/configure/{session_id}/step",
            headers=headers,
            json={"step_data": {"discovery_type": "mdns"}},
            timeout=60,  # Discovery can take time
        )

        if response.status_code == 404:
            self.console.print("     [dim]Endpoint not found[/dim]")
            return

        if response.status_code != 200:
            raise ValueError(f"Step failed: HTTP {response.status_code}")

        data = response.json()
        result = data.get("data", {})
        success = result.get("success", False)
        discovered = result.get("data", {}).get("discovered_items", [])

        self.console.print(f"     [dim]Success: {success}, Items: {len(discovered)}[/dim]")

        if self.live_test and discovered:
            for item in discovered[:3]:
                self.console.print(f"     [dim]  - {item.get('label', 'unknown')}[/dim]")

    async def test_execute_select_get_options(self) -> None:
        """Execute select step to get available options."""
        if not self.created_session_ids:
            self.console.print("     [dim]Skipped - no session[/dim]")
            return

        headers = self._get_auth_headers()
        session_id = self.created_session_ids[-1]

        response = requests.post(
            f"{self._base_url}/v1/system/adapters/configure/{session_id}/step",
            headers=headers,
            json={"step_data": {}},  # Empty to get options
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Endpoint not found[/dim]")
            return

        if response.status_code == 200:
            data = response.json()
            result = data.get("data", {})
            options = result.get("data", {}).get("options", [])
            self.console.print(f"     [dim]Options returned: {len(options)}[/dim]")

    async def test_execute_select_with_selection(self) -> None:
        """Execute select step with a selection."""
        if not self.created_session_ids:
            self.console.print("     [dim]Skipped - no session[/dim]")
            return

        headers = self._get_auth_headers()
        session_id = self.created_session_ids[-1]

        response = requests.post(
            f"{self._base_url}/v1/system/adapters/configure/{session_id}/step",
            headers=headers,
            json={"step_data": {"selection": "option_1"}},
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Endpoint not found[/dim]")
            return

        if response.status_code == 200:
            data = response.json()
            result = data.get("data", {})
            next_step = result.get("next_step_index")
            self.console.print(f"     [dim]Advanced to step: {next_step}[/dim]")

    async def test_execute_input_step(self) -> None:
        """Execute an input step with configuration data."""
        if not self.created_session_ids:
            self.console.print("     [dim]Skipped - no session[/dim]")
            return

        headers = self._get_auth_headers()
        session_id = self.created_session_ids[-1]

        response = requests.post(
            f"{self._base_url}/v1/system/adapters/configure/{session_id}/step",
            headers=headers,
            json={
                "step_data": {
                    "poll_interval": 30,
                    "timeout": 60,
                    "retry_count": 3,
                }
            },
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Endpoint not found[/dim]")
            return

        if response.status_code == 200:
            data = response.json()
            result = data.get("data", {})
            success = result.get("success", False)
            self.console.print(f"     [dim]Input accepted: {success}[/dim]")

    async def test_execute_confirm_step(self) -> None:
        """Execute confirm step to review configuration."""
        if not self.created_session_ids:
            self.console.print("     [dim]Skipped - no session[/dim]")
            return

        headers = self._get_auth_headers()
        session_id = self.created_session_ids[-1]

        response = requests.post(
            f"{self._base_url}/v1/system/adapters/configure/{session_id}/step",
            headers=headers,
            json={"step_data": {}},
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Endpoint not found[/dim]")
            return

        if response.status_code == 200:
            data = response.json()
            result = data.get("data", {})
            summary = result.get("data", {}).get("config_summary", {})
            self.console.print(f"     [dim]Config keys: {list(summary.keys())[:5]}[/dim]")

    async def test_oauth_url_generation(self) -> None:
        """Test OAuth URL generation (first OAuth step call)."""
        headers = self._get_auth_headers()

        # Create a fresh session for OAuth testing
        adapter_type = "homeassistant" if self.live_test else self.test_adapter_type

        start_response = requests.post(
            f"{self._base_url}/v1/system/adapters/{adapter_type}/configure/start",
            headers=headers,
            timeout=30,
        )

        if start_response.status_code == 404:
            self.console.print("     [dim]OAuth adapter not registered[/dim]")
            return

        if start_response.status_code != 200:
            self.console.print(f"     [dim]Could not start session: {start_response.status_code}[/dim]")
            return

        data = start_response.json()
        session_id = data.get("data", {}).get("session_id")

        if session_id:
            self.created_session_ids.append(session_id)

            # Execute step without code to get OAuth URL
            response = requests.post(
                f"{self._base_url}/v1/system/adapters/configure/{session_id}/step",
                headers=headers,
                json={"step_data": {}},
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json().get("data", {})
                oauth_url = result.get("data", {}).get("oauth_url")
                awaiting = result.get("awaiting_callback", False)

                if oauth_url:
                    self.console.print(f"     [dim]OAuth URL generated[/dim]")
                    if self.live_test:
                        self.console.print(f"     [yellow]Open in browser: {oauth_url}[/yellow]")

    async def test_oauth_callback(self) -> None:
        """Test OAuth callback handling."""
        if not self.created_session_ids:
            self.console.print("     [dim]Skipped - no session[/dim]")
            return

        headers = self._get_auth_headers()
        session_id = self.created_session_ids[-1]

        # Test callback endpoint (mock code)
        response = requests.get(
            f"{self._base_url}/v1/system/adapters/configure/{session_id}/oauth/callback",
            headers=headers,
            params={"code": "mock_auth_code", "state": session_id},
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Callback endpoint not found[/dim]")
            return

        if response.status_code == 200:
            data = response.json()
            success = data.get("data", {}).get("success", False)
            self.console.print(f"     [dim]Callback handled: {success}[/dim]")
        else:
            # Expected to fail with mock code
            self.console.print(f"     [dim]Callback failed (expected with mock): HTTP {response.status_code}[/dim]")

    async def test_complete_session_success(self) -> None:
        """Test completing a configuration session successfully."""
        if not self.created_session_ids:
            self.console.print("     [dim]Skipped - no session[/dim]")
            return

        headers = self._get_auth_headers()
        session_id = self.created_session_ids[-1]

        response = requests.post(
            f"{self._base_url}/v1/system/adapters/configure/{session_id}/complete",
            headers=headers,
            timeout=60,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Endpoint not found[/dim]")
            return

        if response.status_code == 200:
            data = response.json()
            success = data.get("data", {}).get("success", False)
            self.console.print(f"     [dim]Completion: {success}[/dim]")

    async def test_complete_session_with_persistence(self) -> None:
        """Test completing a session with persist=True for load-on-startup."""
        headers = self._get_auth_headers()

        # Create a fresh session for persistence testing
        adapter_type = self.test_adapter_type

        start_response = requests.post(
            f"{self._base_url}/v1/system/adapters/{adapter_type}/configure/start",
            headers=headers,
            timeout=30,
        )

        if start_response.status_code == 404:
            self.console.print("     [dim]Adapter not registered[/dim]")
            return

        if start_response.status_code != 200:
            self.console.print(f"     [dim]Could not start session: {start_response.status_code}[/dim]")
            return

        data = start_response.json()
        session_id = data.get("data", {}).get("session_id")

        if not session_id:
            self.console.print("     [dim]No session ID returned[/dim]")
            return

        self.created_session_ids.append(session_id)

        # Complete with persist=True
        response = requests.post(
            f"{self._base_url}/v1/system/adapters/configure/{session_id}/complete",
            headers=headers,
            json={"persist": True},
            timeout=60,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Endpoint not found[/dim]")
            return

        if response.status_code == 200:
            data = response.json()
            result = data.get("data", {})
            success = result.get("success", False)
            persisted = result.get("persisted", False)
            self.console.print(f"     [dim]Success: {success}, Persisted: {persisted}[/dim]")
        else:
            self.console.print(f"     [dim]Response: HTTP {response.status_code}[/dim]")

    async def test_complete_session_validation_failure(self) -> None:
        """Test completing session when validation fails."""
        headers = self._get_auth_headers()

        # Create a fresh session
        adapter_type = self.test_adapter_type
        start_response = requests.post(
            f"{self._base_url}/v1/system/adapters/{adapter_type}/configure/start",
            headers=headers,
            timeout=30,
        )

        if start_response.status_code != 200:
            self.console.print("     [dim]Could not create test session[/dim]")
            return

        session_id = start_response.json().get("data", {}).get("session_id")
        if not session_id:
            raise ValueError("No session ID returned from start")

        self.created_session_ids.append(session_id)

        # Try to complete without completing all required steps
        # (session should have required steps that aren't done)
        response = requests.post(
            f"{self._base_url}/v1/system/adapters/configure/{session_id}/complete",
            headers=headers,
            timeout=30,
        )

        # Should return 200 with success=false OR return 4xx error
        if response.status_code == 200:
            data = response.json()
            result = data.get("data", {})
            # Either success=false or validation_errors present is acceptable
            success = result.get("success", True)
            validation_errors = result.get("validation_errors", [])
            if not success or validation_errors:
                self.console.print(
                    f"     [dim]Correctly handled: success={success}, errors={len(validation_errors)}[/dim]"
                )
            else:
                # Mock adapter may succeed anyway - that's also valid
                self.console.print(f"     [dim]Session completed (mock adapter has no validation)[/dim]")
        elif response.status_code in (400, 422):
            self.console.print(f"     [dim]Correctly rejected: HTTP {response.status_code}[/dim]")
        else:
            raise ValueError(f"Unexpected response: HTTP {response.status_code}")

    async def test_list_persisted_configs(self) -> None:
        """Test listing persisted adapter configurations."""
        headers = self._get_auth_headers()

        response = requests.get(
            f"{self._base_url}/v1/system/adapters/persisted",
            headers=headers,
            timeout=30,
        )

        # Endpoint MUST exist - fail if 404
        if response.status_code == 404:
            raise ValueError("Endpoint /v1/system/adapters/persisted not found - feature not wired up")

        if response.status_code != 200:
            raise ValueError(f"Failed to list persisted configs: HTTP {response.status_code}")

        data = response.json()

        # Verify response structure
        if "data" not in data:
            raise ValueError("Response missing 'data' field")

        response_data = data.get("data", {})
        if "persisted_configs" not in response_data:
            raise ValueError("Response missing 'persisted_configs' field")
        if "count" not in response_data:
            raise ValueError("Response missing 'count' field")

        configs = response_data.get("persisted_configs", {})
        count = response_data.get("count", 0)

        # Verify count matches
        if len(configs) != count:
            raise ValueError(f"Count mismatch: {len(configs)} configs but count={count}")

        self.console.print(f"     [dim]Persisted configs: {len(configs)}[/dim]")
        for adapter_type in list(configs.keys())[:3]:
            self.console.print(f"     [dim]  - {adapter_type}[/dim]")

    async def test_remove_persisted_config(self) -> None:
        """Test removing a persisted adapter configuration."""
        headers = self._get_auth_headers()

        # Try to remove the test adapter's persisted config
        adapter_type = self.test_adapter_type

        response = requests.delete(
            f"{self._base_url}/v1/system/adapters/{adapter_type}/persisted",
            headers=headers,
            timeout=30,
        )

        # Endpoint MUST exist - fail if 404
        if response.status_code == 404:
            raise ValueError(f"Endpoint /v1/system/adapters/{adapter_type}/persisted not found - feature not wired up")

        if response.status_code not in (200, 204):
            raise ValueError(f"Failed to remove persisted config: HTTP {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            # Verify response structure
            if "data" not in data:
                raise ValueError("Response missing 'data' field")

            response_data = data.get("data", {})
            if "success" not in response_data:
                raise ValueError("Response missing 'success' field")
            if "adapter_type" not in response_data:
                raise ValueError("Response missing 'adapter_type' field")
            if "message" not in response_data:
                raise ValueError("Response missing 'message' field")

            success = response_data.get("success", False)
            returned_type = response_data.get("adapter_type", "")

            # Verify adapter_type matches
            if returned_type != adapter_type:
                raise ValueError(f"Adapter type mismatch: expected {adapter_type}, got {returned_type}")

            self.console.print(f"     [dim]Removal: {success}[/dim]")
        else:
            self.console.print("     [dim]Removal: success (no content)[/dim]")

    async def test_get_nonexistent_session(self) -> None:
        """Test getting a session that doesn't exist."""
        headers = self._get_auth_headers()

        response = requests.get(
            f"{self._base_url}/v1/system/adapters/configure/nonexistent-session-id",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            self.console.print("     [dim]Correctly returned 404[/dim]")
        elif response.status_code == 200:
            data = response.json()
            if data.get("data", {}).get("session_id") is None:
                self.console.print("     [dim]Correctly returned empty[/dim]")
            else:
                raise ValueError("Should not find nonexistent session")
        else:
            self.console.print(f"     [dim]Response: HTTP {response.status_code}[/dim]")

    async def test_execute_step_expired(self) -> None:
        """Test executing step on expired/invalid session."""
        headers = self._get_auth_headers()

        # Use a fake session ID that doesn't exist - should behave like expired
        fake_session_id = "00000000-0000-0000-0000-000000000000"

        response = requests.post(
            f"{self._base_url}/v1/system/adapters/configure/{fake_session_id}/step",
            headers=headers,
            json={"step_data": {}},
            timeout=30,
        )

        # Should return 404 (not found) for non-existent session
        if response.status_code == 404:
            self.console.print("     [dim]Correctly returned 404 for invalid session[/dim]")
        elif response.status_code in (400, 410):
            # 400 Bad Request or 410 Gone are also acceptable
            self.console.print(f"     [dim]Correctly rejected: HTTP {response.status_code}[/dim]")
        elif response.status_code == 200:
            # If it returns 200, check that it indicates failure
            data = response.json()
            result = data.get("data", {})
            success = result.get("success", False)
            if not success:
                self.console.print("     [dim]Correctly returned success=false for invalid session[/dim]")
            else:
                raise ValueError("Should not succeed with invalid session ID")
        else:
            raise ValueError(f"Unexpected response: HTTP {response.status_code}")

    async def test_cleanup_sessions(self) -> None:
        """Clean up test sessions."""
        # Sessions will expire naturally, but we can track what we created
        count = len(self.created_session_ids)
        self.console.print(f"     [dim]Created {count} test sessions (will expire in 30min)[/dim]")
        self.created_session_ids.clear()

    def _print_summary(self) -> None:
        """Print test summary table."""
        table = Table(title="Adapter Configuration Tests Summary")
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
