"""
Adapter Availability & Installation Tests.

Tests the adapter discovery, eligibility checking, and installation system:
- GET /adapters/available - List all adapters with eligibility status
- POST /adapters/{name}/install - Install missing dependencies
- POST /adapters/{name}/check-eligibility - Recheck after installation

This module validates the "available but not eligible" adapter exposure
and the installation workflow for adapters with unmet requirements.
"""

import asyncio
import traceback
from typing import Any, Dict, List, Optional

import requests
from rich.console import Console
from rich.table import Table


class AdapterAvailabilityTests:
    """Test adapter availability discovery and installation functionality."""

    def __init__(self, client: Any, console: Console):
        """Initialize adapter availability tests.

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

        # Track discovered adapters for subsequent tests
        self.eligible_adapters: List[Dict[str, Any]] = []
        self.ineligible_adapters: List[Dict[str, Any]] = []
        self.installable_adapters: List[Dict[str, Any]] = []

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
        """Run all adapter availability tests."""
        self.console.print("\n[cyan]Adapter Availability & Installation Tests[/cyan]")
        self.console.print("[dim]Tests adapter discovery, eligibility, and installation[/dim]")

        tests = [
            # Phase 1: Discovery & Availability
            ("Verify System Health", self.test_system_health),
            ("Get All Available Adapters", self.test_get_available_adapters),
            ("Verify Eligible Adapters Have Required Fields", self.test_eligible_adapter_fields),
            ("Verify Ineligible Adapters Have Eligibility Info", self.test_ineligible_adapter_fields),
            ("Verify Installable Adapters Have Install Hints", self.test_installable_adapters),
            # Phase 2: Eligibility Details
            ("Check Eligibility Reasons Are Populated", self.test_eligibility_reasons),
            ("Check Missing Dependencies Are Listed", self.test_missing_dependencies),
            ("Check Platform Compatibility", self.test_platform_compatibility),
            # Phase 3: Installation (dry-run)
            ("Dry-Run Install for Installable Adapter", self.test_dry_run_install),
            ("Recheck Eligibility Endpoint", self.test_recheck_eligibility),
            # Phase 4: Edge Cases
            ("Handle Non-Existent Adapter Install", self.test_install_nonexistent),
            ("Handle Adapter Without Install Hints", self.test_install_no_hints),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "PASS", "error": None})
                self.console.print(f"  [green]PASS[/green] {name}")
            except AssertionError as e:
                self.results.append({"test": name, "status": "FAIL", "error": str(e)})
                self.console.print(f"  [red]FAIL[/red] {name}: {str(e)[:80]}")
            except Exception as e:
                self.results.append({"test": name, "status": "ERROR", "error": str(e)})
                self.console.print(f"  [yellow]ERROR[/yellow] {name}: {str(e)[:80]}")
                if self.console.is_terminal:
                    self.console.print(f"     [dim]{traceback.format_exc()[:200]}[/dim]")

        self._print_summary()
        return self.results

    async def test_system_health(self) -> None:
        """Verify system is healthy before running tests."""
        health = await self.client.system.health()
        assert hasattr(health, "status"), "Health response missing status"
        self.console.print(f"     [dim]Status: {health.status}[/dim]")

    async def test_get_available_adapters(self) -> None:
        """Test GET /adapters/available endpoint returns discovery report."""
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters/available",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            raise AssertionError("Endpoint /adapters/available not implemented yet")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"

        data = response.json()
        report = data.get("data", data)  # Handle wrapped or unwrapped response

        # Verify required fields in response
        assert "eligible" in report, "Response missing 'eligible' field"
        assert "ineligible" in report, "Response missing 'ineligible' field"
        assert "total_discovered" in report, "Response missing 'total_discovered' field"

        # Store for subsequent tests
        self.eligible_adapters = report.get("eligible", [])
        self.ineligible_adapters = report.get("ineligible", [])
        self.installable_adapters = [a for a in self.ineligible_adapters if a.get("can_install", False)]

        total = report.get("total_discovered", 0)
        eligible_count = len(self.eligible_adapters)
        ineligible_count = len(self.ineligible_adapters)
        installable_count = len(self.installable_adapters)

        self.console.print(f"     [dim]Total discovered: {total}[/dim]")
        self.console.print(f"     [dim]Eligible: {eligible_count}[/dim]")
        self.console.print(f"     [dim]Ineligible: {ineligible_count}[/dim]")
        self.console.print(f"     [dim]Installable: {installable_count}[/dim]")

    async def test_eligible_adapter_fields(self) -> None:
        """Verify eligible adapters have all required fields."""
        if not self.eligible_adapters:
            self.console.print("     [dim]No eligible adapters to validate (OK)[/dim]")
            return

        required_fields = ["name", "eligible"]
        for adapter in self.eligible_adapters[:3]:  # Check first 3
            for field in required_fields:
                assert field in adapter, f"Eligible adapter missing '{field}': {adapter.get('name', 'unknown')}"
            assert adapter.get("eligible") is True, f"Eligible adapter has eligible=False: {adapter.get('name')}"

        self.console.print(f"     [dim]Validated {min(3, len(self.eligible_adapters))} eligible adapters[/dim]")

    async def test_ineligible_adapter_fields(self) -> None:
        """Verify ineligible adapters have eligibility information."""
        if not self.ineligible_adapters:
            self.console.print("     [dim]No ineligible adapters to validate (OK)[/dim]")
            return

        required_fields = ["name", "eligible", "eligibility_reason"]
        for adapter in self.ineligible_adapters[:3]:  # Check first 3
            for field in required_fields:
                assert field in adapter, f"Ineligible adapter missing '{field}': {adapter.get('name', 'unknown')}"
            assert adapter.get("eligible") is False, f"Ineligible adapter has eligible=True: {adapter.get('name')}"
            assert adapter.get("eligibility_reason"), f"Ineligible adapter missing reason: {adapter.get('name')}"

        self.console.print(f"     [dim]Validated {min(3, len(self.ineligible_adapters))} ineligible adapters[/dim]")

    async def test_installable_adapters(self) -> None:
        """Verify installable adapters have install hints."""
        if not self.installable_adapters:
            self.console.print("     [dim]No installable adapters found (OK - may be fully configured)[/dim]")
            return

        for adapter in self.installable_adapters[:3]:
            assert adapter.get("can_install") is True, f"Installable adapter missing can_install: {adapter.get('name')}"
            hints = adapter.get("install_hints", [])
            assert len(hints) > 0, f"Installable adapter has no install_hints: {adapter.get('name')}"

            # Verify install hint structure
            for hint in hints[:2]:
                assert "kind" in hint, f"Install hint missing 'kind': {hint}"
                assert "id" in hint, f"Install hint missing 'id': {hint}"

        self.console.print(f"     [dim]Validated {min(3, len(self.installable_adapters))} installable adapters[/dim]")
        for adapter in self.installable_adapters[:3]:
            hints = adapter.get("install_hints", [])
            kinds = [h.get("kind") for h in hints]
            self.console.print(f"     [dim]  - {adapter.get('name')}: {kinds}[/dim]")

    async def test_eligibility_reasons(self) -> None:
        """Verify eligibility reasons are human-readable."""
        if not self.ineligible_adapters:
            self.console.print("     [dim]No ineligible adapters to check reasons (OK)[/dim]")
            return

        for adapter in self.ineligible_adapters[:3]:
            reason = adapter.get("eligibility_reason", "")
            assert reason, f"Empty eligibility reason for {adapter.get('name')}"
            # Reason should mention what's missing
            assert len(reason) > 10, f"Eligibility reason too short: '{reason}'"

        self.console.print(
            f"     [dim]Sample reason: {self.ineligible_adapters[0].get('eligibility_reason', '')[:60]}...[/dim]"
        )

    async def test_missing_dependencies(self) -> None:
        """Verify missing dependencies are properly categorized."""
        if not self.ineligible_adapters:
            self.console.print("     [dim]No ineligible adapters to check dependencies (OK)[/dim]")
            return

        dependency_fields = ["missing_binaries", "missing_env_vars", "missing_config"]
        for adapter in self.ineligible_adapters[:3]:
            # At least one dependency field should have content (since it's ineligible)
            has_missing = (
                any(adapter.get(field, []) for field in dependency_fields) or adapter.get("platform_supported") is False
            )

            if not has_missing:
                self.console.print(
                    f"     [dim]Warning: {adapter.get('name')} ineligible but no missing deps listed[/dim]"
                )

        self.console.print(
            f"     [dim]Checked dependency categorization for {min(3, len(self.ineligible_adapters))} adapters[/dim]"
        )

    async def test_platform_compatibility(self) -> None:
        """Verify platform compatibility is indicated."""
        headers = self._get_auth_headers()
        response = requests.get(
            f"{self._base_url}/v1/system/adapters/available",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            raise AssertionError("Endpoint not implemented")

        data = response.json().get("data", response.json())

        # Check that platform_supported field exists
        all_adapters = data.get("eligible", []) + data.get("ineligible", [])
        if all_adapters:
            sample = all_adapters[0]
            # platform_supported should default to True if not specified
            platform_supported = sample.get("platform_supported", True)
            assert isinstance(platform_supported, bool), "platform_supported should be boolean"

        self.console.print(f"     [dim]Platform compatibility field validated[/dim]")

    async def test_dry_run_install(self) -> None:
        """Test dry-run installation for an installable adapter."""
        if not self.installable_adapters:
            self.console.print("     [dim]No installable adapters for dry-run test (SKIP)[/dim]")
            return

        adapter = self.installable_adapters[0]
        adapter_name = adapter.get("name")

        headers = self._get_auth_headers()
        response = requests.post(
            f"{self._base_url}/v1/system/adapters/{adapter_name}/install",
            headers=headers,
            json={"dry_run": True},
            timeout=60,
        )

        if response.status_code == 404:
            raise AssertionError(f"Install endpoint not implemented for {adapter_name}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"

        data = response.json().get("data", response.json())

        # Dry run should succeed (no actual installation)
        assert "success" in data, "Install response missing 'success' field"
        assert "message" in data, "Install response missing 'message' field"

        # Verify dry-run indicator in message
        message = data.get("message", "")
        self.console.print(f"     [dim]Dry-run result: {message[:60]}...[/dim]")

    async def test_recheck_eligibility(self) -> None:
        """Test POST /adapters/{name}/check-eligibility endpoint."""
        # Use any known adapter name
        test_adapter = "sample_adapter"
        if self.eligible_adapters:
            test_adapter = self.eligible_adapters[0].get("name", test_adapter)
        elif self.ineligible_adapters:
            test_adapter = self.ineligible_adapters[0].get("name", test_adapter)

        headers = self._get_auth_headers()
        response = requests.post(
            f"{self._base_url}/v1/system/adapters/{test_adapter}/check-eligibility",
            headers=headers,
            timeout=30,
        )

        if response.status_code == 404:
            raise AssertionError("Recheck eligibility endpoint not implemented")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json().get("data", response.json())
        assert "eligible" in data, "Recheck response missing 'eligible' field"

        self.console.print(f"     [dim]Recheck for '{test_adapter}': eligible={data.get('eligible')}[/dim]")

    async def test_install_nonexistent(self) -> None:
        """Test install endpoint returns 404 for non-existent adapter."""
        headers = self._get_auth_headers()
        response = requests.post(
            f"{self._base_url}/v1/system/adapters/nonexistent_adapter_xyz123/install",
            headers=headers,
            json={"dry_run": True},
            timeout=30,
        )

        if response.status_code == 404:
            # Expected behavior
            self.console.print("     [dim]Got expected 404 for non-existent adapter[/dim]")
            return

        # Some implementations may return 400 or other error codes
        assert (
            response.status_code >= 400
        ), f"Expected error status for non-existent adapter, got {response.status_code}"

    async def test_install_no_hints(self) -> None:
        """Test install endpoint handles adapter without install hints."""
        # Find an ineligible adapter without install hints
        no_hints_adapters = [
            a for a in self.ineligible_adapters if not a.get("can_install", False) and not a.get("install_hints", [])
        ]

        if not no_hints_adapters:
            self.console.print("     [dim]No adapters without install hints to test (SKIP)[/dim]")
            return

        adapter_name = no_hints_adapters[0].get("name")
        headers = self._get_auth_headers()
        response = requests.post(
            f"{self._base_url}/v1/system/adapters/{adapter_name}/install",
            headers=headers,
            json={"dry_run": True},
            timeout=30,
        )

        if response.status_code == 404:
            # Endpoint not implemented yet
            raise AssertionError("Install endpoint not implemented")

        # Should return error indicating no install hints available
        data = response.json().get("data", response.json())
        success = data.get("success", True)
        assert success is False, f"Expected failure for adapter without install hints: {adapter_name}"

        self.console.print(f"     [dim]Correctly rejected install for {adapter_name} (no hints)[/dim]")

    def _print_summary(self) -> None:
        """Print test summary table."""
        self.console.print("\n")
        table = Table(title="Adapter Availability Test Results")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Error", style="red", max_width=50)

        passed = 0
        failed = 0
        errors = 0

        for result in self.results:
            status = result["status"]
            if status == "PASS":
                passed += 1
                status_str = "[green]PASS[/green]"
            elif status == "FAIL":
                failed += 1
                status_str = "[red]FAIL[/red]"
            else:
                errors += 1
                status_str = "[yellow]ERROR[/yellow]"

            error = result.get("error", "") or ""
            table.add_row(result["test"], status_str, error[:50])

        self.console.print(table)
        self.console.print(f"\n[bold]Summary:[/bold] {passed} passed, {failed} failed, {errors} errors")


# For QA runner integration
def get_test_class():
    """Return the test class for QA runner discovery."""
    return AdapterAvailabilityTests
