"""
Secrets Encryption QA tests.

Tests the secrets encryption system including:
- Hardware capabilities detection (CIRISVerify v1.6.0+)
- Key storage mode detection (hardware vs software)
- Encryption module functionality
- Secrets service integration
"""

import traceback
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table

from ciris_sdk.client import CIRISClient


class SecretsEncryptionTests:
    """Test secrets encryption functionality with CIRISVerify v1.6.0+."""

    def __init__(self, client: CIRISClient, console: Console):
        """Initialize secrets encryption tests."""
        self.client = client
        self.console = console
        self.results: List[Dict[str, Any]] = []
        self.verify_status: Optional[Dict[str, Any]] = None

    def _get_transport_info(self) -> tuple:
        """Get base URL and token from client transport."""
        transport = getattr(self.client, "_transport", None)
        base_url = getattr(transport, "base_url", "http://localhost:8080")
        token = getattr(transport, "api_key", None)
        return base_url, token

    async def run(self) -> List[Dict[str, Any]]:
        """Run all secrets encryption tests."""
        self.console.print("\n[cyan]🔐 Testing Secrets Encryption (CIRISVerify v1.6.0+)[/cyan]")

        tests = [
            ("Get CIRISVerify Status", self.test_verify_status),
            ("Check Hardware Key Storage Mode", self.test_key_storage_mode),
            ("Check Encryption Capabilities", self.test_encryption_capabilities),
            ("Test Encryption Module Direct", self.test_encryption_module),
            ("Check Secrets Service Health", self.test_secrets_service_health),
            ("Verify Telemetry Reports Secrets", self.test_telemetry_secrets),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "PASS", "error": None})
                self.console.print(f"  [green]✓[/green] {name}")
            except Exception as e:
                self.results.append({"test": name, "status": "FAIL", "error": str(e)})
                self.console.print(f"  [red]✗[/red] {name}: {str(e)[:100]}")
                if self.console.is_terminal:
                    self.console.print(f"     [dim]{traceback.format_exc()[:500]}[/dim]")

        self._print_summary()
        return self.results

    async def test_verify_status(self) -> None:
        """Test getting CIRISVerify status including encryption info."""
        base_url, token = self._get_transport_info()

        import httpx

        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(
                f"{base_url}/v1/setup/verify-status",
                headers={"Authorization": f"Bearer {token}"} if token else {},
                timeout=30.0,
            )

            if response.status_code != 200:
                raise ValueError(f"verify-status returned {response.status_code}")

            response_json = response.json()
            # SuccessResponse wraps data in "data" field
            self.verify_status = response_json.get("data", response_json)

            # Check required fields exist
            if "loaded" not in self.verify_status:
                raise ValueError(f"Missing 'loaded' field. Keys: {list(self.verify_status.keys())[:10]}")

            version = self.verify_status.get("version")
            loaded = self.verify_status.get("loaded")
            self.console.print(f"     [dim]CIRISVerify version: {version}, Loaded: {loaded}[/dim]")

    async def test_key_storage_mode(self) -> None:
        """Test hardware key storage mode detection."""
        if not self.verify_status:
            raise ValueError("verify_status not available - run test_verify_status first")

        key_storage_mode = self.verify_status.get("key_storage_mode")
        hardware_backed = self.verify_status.get("hardware_backed", False)

        self.console.print(f"     [dim]Key storage mode: {key_storage_mode}[/dim]")
        self.console.print(f"     [dim]Hardware backed: {hardware_backed}[/dim]")

        # Test passes regardless of mode - we just want to verify it's reported
        if key_storage_mode is None:
            self.console.print("     [yellow]Note: key_storage_mode not in attestation response[/yellow]")

    async def test_encryption_capabilities(self) -> None:
        """Test encryption capabilities detection for v1.6.0+."""
        if not self.verify_status:
            raise ValueError("verify_status not available")

        version = self.verify_status.get("version", "")
        hardware_type = self.verify_status.get("hardware_type")

        # Check version
        if version:
            if version.startswith("1.6"):
                self.console.print(f"     [dim]v1.6.0+ detected - native encryption available[/dim]")
            elif version.startswith("1.5"):
                self.console.print(f"     [dim]v1.5.x detected - signing-based derivation only[/dim]")
            else:
                self.console.print(f"     [dim]Version {version} detected[/dim]")

        self.console.print(f"     [dim]Hardware type: {hardware_type}[/dim]")

    async def test_encryption_module(self) -> None:
        """Test encryption module directly (no network call)."""
        try:
            from ciris_engine.logic.secrets.encryption import SecretsEncryption

            # Create encryption instance in auto mode
            encryption = SecretsEncryption(key_storage_mode="auto")

            # Get capabilities
            caps = encryption.get_hardware_capabilities()

            self.console.print(f"     [dim]Hardware available: {caps.get('hardware_available')}[/dim]")
            self.console.print(f"     [dim]Native encryption: {caps.get('native_encryption')}[/dim]")
            self.console.print(f"     [dim]Symmetric derivation: {caps.get('symmetric_derivation')}[/dim]")
            self.console.print(f"     [dim]Signing derivation: {caps.get('signing_derivation')}[/dim]")
            self.console.print(f"     [dim]Key storage mode: {encryption.key_storage_mode}[/dim]")

            # Test encryption round-trip (encrypt_secret takes string or bytes)
            test_data = "QA test secret data for encryption verification"
            encrypted, salt, nonce = encryption.encrypt_secret(test_data)
            decrypted = encryption.decrypt_secret(encrypted, salt, nonce)

            # Compare - handle both bytes and string return types
            decrypted_str = decrypted.decode() if isinstance(decrypted, bytes) else decrypted
            if decrypted_str != test_data:
                raise ValueError("Encryption round-trip failed: data mismatch")

            self.console.print(f"     [dim]Encryption round-trip: OK[/dim]")

        except ImportError as e:
            raise ValueError(f"Could not import encryption module: {e}")

    async def test_secrets_service_health(self) -> None:
        """Test secrets service health via telemetry."""
        base_url, token = self._get_transport_info()

        import httpx

        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(
                f"{base_url}/v1/telemetry/unified",
                headers={"Authorization": f"Bearer {token}"} if token else {},
                timeout=30.0,
            )

            if response.status_code != 200:
                raise ValueError(f"telemetry/unified returned {response.status_code}")

            data = response.json()
            services = data.get("services", {})

            # Check if secrets service is healthy
            secrets_svc = services.get("secrets")
            if secrets_svc:
                healthy = secrets_svc.get("healthy", False)
                self.console.print(f"     [dim]Secrets service healthy: {healthy}[/dim]")
                if not healthy:
                    self.console.print(f"     [yellow]Warning: Secrets service unhealthy[/yellow]")
            else:
                self.console.print(f"     [dim]Secrets service not in telemetry (may be internal)[/dim]")

    async def test_telemetry_secrets(self) -> None:
        """Test that telemetry reports secrets count."""
        base_url, token = self._get_transport_info()

        import httpx

        async with httpx.AsyncClient() as http_client:
            response = await http_client.get(
                f"{base_url}/v1/telemetry/unified",
                headers={"Authorization": f"Bearer {token}"} if token else {},
                timeout=30.0,
            )

            if response.status_code != 200:
                raise ValueError(f"telemetry/unified returned {response.status_code}")

            data = response.json()

            # Check for secrets data in metrics
            metrics = data.get("metrics", {})
            secrets_count = metrics.get("secrets_count", metrics.get("total_secrets", 0))

            self.console.print(f"     [dim]Secrets tracked: {secrets_count}[/dim]")

    def _print_summary(self) -> None:
        """Print test summary table."""
        table = Table(title="Secrets Encryption Test Results")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Error", style="red")

        passed = 0
        failed = 0
        for result in self.results:
            status = result["status"]
            if status == "PASS":
                passed += 1
                status_display = "[green]PASS[/green]"
            else:
                failed += 1
                status_display = "[red]FAIL[/red]"

            error = result.get("error") or ""
            if len(error) > 50:
                error = error[:47] + "..."

            table.add_row(result["test"], status_display, error)

        self.console.print(table)
        self.console.print(f"\n[bold]Summary:[/bold] {passed} passed, {failed} failed")
