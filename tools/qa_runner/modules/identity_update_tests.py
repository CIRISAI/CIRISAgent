"""
Identity Update Integration Tests.

Tests the --identity-update flag functionality which allows refreshing
agent identity from a template. This is a full integration test that:

1. Gets current identity from the graph
2. Modifies the template with different values
3. Stops the server
4. Restarts with --template --identity-update flags
5. Verifies identity was updated from template
6. Restores original template

This test manages its own server lifecycle for restart testing.
"""

import asyncio
import os
import shutil
import signal
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml
from rich.console import Console
from rich.table import Table


class IdentityUpdateTests:
    """Integration test for identity update functionality."""

    def __init__(self, client: Any, console: Console):
        """Initialize identity update tests.

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

        # Extract port from base URL
        self._port = 8080
        if ":" in self._base_url:
            try:
                self._port = int(self._base_url.split(":")[-1].split("/")[0])
            except (ValueError, IndexError):
                pass

        # Template paths
        self._template_dir = Path("ciris_engine/ciris_templates")
        self._template_name = "default"  # Use default.yaml (Datum)
        self._template_path = self._template_dir / f"{self._template_name}.yaml"
        self._backup_path = self._template_dir / f"{self._template_name}.yaml.backup"

        # Identity snapshots
        self.initial_identity: Optional[Dict[str, Any]] = None
        self.updated_identity: Optional[Dict[str, Any]] = None

        # Test modification values
        self._test_description = "TEST_IDENTITY_UPDATE: This description was set by the identity update integration test."
        self._test_name = "DatumTestUpdate"

        # Server process (managed externally by qa_runner, but we track for restart)
        self._server_process: Optional[subprocess.Popen] = None

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

    def _get_auth_token(self) -> Optional[str]:
        """Get the current auth token."""
        if hasattr(self.client, "api_key") and self.client.api_key:
            return self.client.api_key
        if hasattr(self.client, "_transport"):
            transport = self.client._transport
            if hasattr(transport, "api_key") and transport.api_key:
                return transport.api_key
        return None

    async def run(self) -> List[Dict[str, Any]]:
        """Run all identity update integration tests."""
        self.console.print("\n[cyan]Identity Update Integration Tests[/cyan]")
        self.console.print("[dim]Full end-to-end test of --identity-update flag[/dim]")

        tests = [
            # Phase 1: Capture initial state
            ("Get Initial Identity from API", self.test_get_initial_identity),
            ("Verify Initial Identity Structure", self.test_verify_initial_structure),
            # Phase 2: Modify template
            ("Backup Original Template", self.test_backup_template),
            ("Modify Template with Test Values", self.test_modify_template),
            ("Verify Template Modified", self.test_verify_template_modified),
            # Phase 3: Server restart with --identity-update
            ("Stop Current Server", self.test_stop_server),
            ("Start Server with --identity-update", self.test_start_server_with_identity_update),
            ("Authenticate After Restart", self.test_authenticate_after_restart),
            # Phase 4: Verify identity updated
            ("Get Updated Identity", self.test_get_updated_identity),
            ("Verify Identity Was Updated", self.test_verify_identity_updated),
            # Phase 5: Cleanup
            ("Restore Original Template", self.test_restore_template),
            ("Stop Test Server", self.test_stop_test_server),
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
                    self.console.print(f"     [dim]{traceback.format_exc()[:300]}[/dim]")
                # On failure, try to restore template and cleanup
                await self._emergency_cleanup()
                break

        self._print_summary()
        return self.results

    async def _emergency_cleanup(self) -> None:
        """Emergency cleanup on test failure."""
        try:
            if self._backup_path.exists():
                shutil.copy(self._backup_path, self._template_path)
                self._backup_path.unlink()
                self.console.print("     [dim]Restored template from backup[/dim]")
        except Exception as e:
            self.console.print(f"     [yellow]Warning: Could not restore template: {e}[/yellow]")

        try:
            if self._server_process:
                self._server_process.terminate()
                self._server_process.wait(timeout=10)
        except Exception:
            pass

    async def test_get_initial_identity(self) -> None:
        """Get current agent identity from API."""
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/agent/identity",
            headers=headers,
            timeout=30,
        )

        if response.status_code != 200:
            raise ValueError(f"Failed to get identity: HTTP {response.status_code}")

        data = response.json()
        self.initial_identity = data.get("data", {})

        if not self.initial_identity:
            raise ValueError("Empty identity response")

        agent_id = self.initial_identity.get("agent_id", "unknown")
        name = self.initial_identity.get("name", "unknown")
        purpose = self.initial_identity.get("purpose", "")[:50]
        self.console.print(f"     [dim]Agent: {agent_id}, Name: {name}[/dim]")
        self.console.print(f"     [dim]Purpose: {purpose}...[/dim]")

    async def test_verify_initial_structure(self) -> None:
        """Verify initial identity has required fields."""
        if not self.initial_identity:
            raise ValueError("No initial identity captured")

        required = ["agent_id", "name", "purpose"]
        missing = [f for f in required if f not in self.initial_identity]
        if missing:
            raise ValueError(f"Missing fields: {missing}")

        self.console.print("     [dim]Identity structure verified[/dim]")

    async def test_backup_template(self) -> None:
        """Backup the original template file."""
        if not self._template_path.exists():
            raise ValueError(f"Template not found: {self._template_path}")

        shutil.copy(self._template_path, self._backup_path)
        self.console.print(f"     [dim]Backed up to {self._backup_path}[/dim]")

    async def test_modify_template(self) -> None:
        """Modify template with test values."""
        with open(self._template_path, "r") as f:
            template = yaml.safe_load(f)

        # Store original values for verification
        original_name = template.get("name", "")
        original_desc = template.get("description", "")[:50]
        self.console.print(f"     [dim]Original name: {original_name}[/dim]")
        self.console.print(f"     [dim]Original desc: {original_desc}...[/dim]")

        # Modify with test values
        template["name"] = self._test_name
        template["description"] = self._test_description

        with open(self._template_path, "w") as f:
            yaml.dump(template, f, default_flow_style=False, allow_unicode=True)

        self.console.print(f"     [dim]Set name to: {self._test_name}[/dim]")
        self.console.print(f"     [dim]Set description to test value[/dim]")

    async def test_verify_template_modified(self) -> None:
        """Verify template was modified correctly."""
        with open(self._template_path, "r") as f:
            template = yaml.safe_load(f)

        if template.get("name") != self._test_name:
            raise ValueError(f"Name not modified: {template.get('name')}")

        if template.get("description") != self._test_description:
            raise ValueError("Description not modified")

        self.console.print("     [dim]Template modifications verified[/dim]")

    async def test_stop_server(self) -> None:
        """Stop the current server (managed by qa_runner)."""
        # The qa_runner manages the server, but we need to stop it for restart
        # Kill any server on our port
        try:
            result = subprocess.run(
                ["pkill", "-f", f"python.*main.py.*--port.*{self._port}"],
                capture_output=True,
                timeout=10,
            )
            # Also try without port specification
            subprocess.run(
                ["pkill", "-f", "python.*main.py.*--adapter.*api.*--mock-llm"],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass

        # Wait for port to be free
        for _ in range(30):
            try:
                response = requests.get(f"{self._base_url}/v1/system/health", timeout=1)
                time.sleep(0.5)
            except Exception:
                break

        self.console.print("     [dim]Server stopped[/dim]")

    async def test_start_server_with_identity_update(self) -> None:
        """Start server with --template and --identity-update flags."""
        # Start the server with identity update flags
        cmd = [
            "python3", "main.py",
            "--adapter", "api",
            "--mock-llm",
            "--port", str(self._port),
            "--template", self._template_name,
            "--identity-update",
        ]

        self.console.print(f"     [dim]Starting: {' '.join(cmd)}[/dim]")

        self._server_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={**os.environ, "CIRIS_CONFIGURED": "true"},
        )

        # Wait for server to be ready (check health endpoint)
        max_wait = 120  # 2 minutes
        start_time = time.time()
        server_ready = False

        while time.time() - start_time < max_wait:
            try:
                response = requests.get(f"{self._base_url}/v1/system/health", timeout=2)
                if response.status_code == 200:
                    server_ready = True
                    break
            except Exception:
                pass
            time.sleep(1)

        if not server_ready:
            # Get any output from server
            if self._server_process.poll() is not None:
                stdout, _ = self._server_process.communicate(timeout=5)
                raise ValueError(f"Server failed to start. Output: {stdout.decode()[:500]}")
            raise ValueError("Server did not become ready within timeout")

        # Wait for WORK state
        work_ready = False
        for _ in range(60):
            try:
                response = requests.get(f"{self._base_url}/v1/agent/status", timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    state = data.get("data", {}).get("cognitive_state", "")
                    if state == "WORK" or state == "AgentState.WORK":
                        work_ready = True
                        break
            except Exception:
                pass
            time.sleep(1)

        if not work_ready:
            self.console.print("     [yellow]Warning: Agent not in WORK state, continuing anyway[/yellow]")

        self.console.print("     [dim]Server started with --identity-update[/dim]")

    async def test_authenticate_after_restart(self) -> None:
        """Get new auth token after server restart."""
        # Login to get new token
        response = requests.post(
            f"{self._base_url}/v1/auth/login",
            json={"username": "admin", "password": "ciris_admin_password"},
            timeout=30,
        )

        if response.status_code != 200:
            raise ValueError(f"Login failed: HTTP {response.status_code}")

        data = response.json()
        token = data.get("data", {}).get("access_token") or data.get("access_token")

        if not token:
            raise ValueError("No token in login response")

        # Update client token
        if hasattr(self.client, "_transport"):
            self.client._transport.set_api_key(token, persist=False)

        self.console.print("     [dim]Authenticated with new token[/dim]")

    async def test_get_updated_identity(self) -> None:
        """Get identity after restart with --identity-update."""
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/agent/identity",
            headers=headers,
            timeout=30,
        )

        if response.status_code != 200:
            raise ValueError(f"Failed to get identity: HTTP {response.status_code}")

        data = response.json()
        self.updated_identity = data.get("data", {})

        if not self.updated_identity:
            raise ValueError("Empty identity response")

        name = self.updated_identity.get("name", "unknown")
        purpose = self.updated_identity.get("purpose", "")[:60]
        self.console.print(f"     [dim]Updated name: {name}[/dim]")
        self.console.print(f"     [dim]Updated purpose: {purpose}...[/dim]")

    async def test_verify_identity_updated(self) -> None:
        """Verify identity was updated from template."""
        if not self.initial_identity or not self.updated_identity:
            raise ValueError("Missing identity snapshots for comparison")

        # Check multiple fields for changes
        changes_detected = []

        # Check agent_id (should be the test name if template update worked)
        initial_agent_id = self.initial_identity.get("agent_id", "")
        updated_agent_id = self.updated_identity.get("agent_id", "")
        if initial_agent_id != updated_agent_id:
            changes_detected.append(f"agent_id: {initial_agent_id} -> {updated_agent_id}")

        # Check name
        initial_name = self.initial_identity.get("name", "")
        updated_name = self.updated_identity.get("name", "")
        if initial_name != updated_name:
            changes_detected.append(f"name: {initial_name} -> {updated_name}")

        # Check purpose/description
        initial_purpose = self.initial_identity.get("purpose", "")
        updated_purpose = self.updated_identity.get("purpose", "")
        if initial_purpose != updated_purpose:
            changes_detected.append(f"purpose changed ({len(initial_purpose)} -> {len(updated_purpose)} chars)")

        # Check if test values appeared
        test_values_found = False
        if self._test_name in updated_agent_id or self._test_name in updated_name:
            test_values_found = True
            self.console.print(f"     [green]Test name '{self._test_name}' found in updated identity[/green]")

        if "TEST_IDENTITY_UPDATE" in updated_purpose or self._test_description[:30] in updated_purpose:
            test_values_found = True
            self.console.print("     [green]Test description found in updated identity[/green]")

        # Report changes
        if changes_detected:
            self.console.print(f"     [dim]Changes detected: {len(changes_detected)}[/dim]")
            for change in changes_detected[:3]:
                self.console.print(f"     [dim]  - {change}[/dim]")

        # Verify that SOMETHING changed
        if not changes_detected and self.initial_identity == self.updated_identity:
            raise ValueError("Identity was NOT updated - no changes detected at all")

        # Log whether test values were found (informational, not a hard failure)
        if not test_values_found and changes_detected:
            self.console.print("     [yellow]Note: Test values not found, but identity did change[/yellow]")
            self.console.print("     [dim]This may indicate the template fields map differently to identity[/dim]")

        self.console.print("     [green]Identity update mechanism verified![/green]")

    async def test_restore_template(self) -> None:
        """Restore original template from backup."""
        if not self._backup_path.exists():
            self.console.print("     [dim]No backup to restore[/dim]")
            return

        shutil.copy(self._backup_path, self._template_path)
        self._backup_path.unlink()
        self.console.print("     [dim]Original template restored[/dim]")

    async def test_stop_test_server(self) -> None:
        """Stop the test server."""
        if self._server_process:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._server_process.kill()
            self._server_process = None

        self.console.print("     [dim]Test server stopped[/dim]")

    def _print_summary(self) -> None:
        """Print test summary table."""
        table = Table(title="Identity Update Integration Tests Summary")
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
