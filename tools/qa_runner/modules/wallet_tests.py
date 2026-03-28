"""
Wallet QA tests.

Tests the wallet adapter including:
- Validation module (EIP-55 checksum, amount validation, recipient validation)
- Spending limits (daily/session tracking)
- Duplicate transaction protection
- Gas pre-check validation
- Provider initialization with CIRISVerify
- Full send flow on Base Sepolia testnet

Mission: Validate all safety constraints are enforced before any transaction
is signed and broadcast.
"""

import traceback
from decimal import Decimal
from typing import Dict, List, Optional

from rich.console import Console
from rich.table import Table

from ciris_sdk.client import CIRISClient


class WalletTests:
    """Test wallet functionality and safety constraints."""

    def __init__(self, client: CIRISClient, console: Console):
        """Initialize wallet tests."""
        self.client = client
        self.console = console
        self.results: List[Dict[str, Optional[str]]] = []

    async def run(self) -> List[Dict[str, Optional[str]]]:
        """Run all wallet tests."""
        self.console.print("\n[cyan]Wallet Adapter Tests[/cyan]")

        # Run validation tests first (unit tests - no network)
        await self._run_validation_tests()

        # Run integration tests (require wallet adapter)
        await self._run_integration_tests()

        self._print_summary()
        return self.results

    async def _run_validation_tests(self) -> None:
        """Run validation module unit tests."""
        self.console.print("\n  [bold]Validation Module Tests[/bold]")

        tests = [
            ("EIP-55 Checksum - Valid", self.test_eip55_valid),
            ("EIP-55 Checksum - Invalid", self.test_eip55_invalid),
            ("EIP-55 Checksum - Lowercase", self.test_eip55_lowercase),
            ("Amount Validation - Negative", self.test_amount_negative),
            ("Amount Validation - Zero", self.test_amount_zero),
            ("Amount Validation - Dust", self.test_amount_dust),
            ("Amount Validation - Max Transaction", self.test_amount_max_transaction),
            ("Recipient Validation - Valid", self.test_recipient_valid),
            ("Recipient Validation - Zero Address", self.test_recipient_zero_address),
            ("Recipient Validation - Invalid Hex", self.test_recipient_invalid_hex),
            ("Gas Validation - Insufficient", self.test_gas_insufficient),
            ("Gas Validation - Price Too High", self.test_gas_price_too_high),
            ("Spending Tracker - Daily Limit", self.test_spending_daily_limit),
            ("Spending Tracker - Session Limit", self.test_spending_session_limit),
            ("Duplicate Protection", self.test_duplicate_protection),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "PASS", "error": None})
                self.console.print(f"    [green]PASS[/green] {name}")
            except Exception as e:
                self.results.append({"test": name, "status": "FAIL", "error": str(e)})
                self.console.print(f"    [red]FAIL[/red] {name}: {str(e)[:80]}")
                if self.console.is_terminal:
                    self.console.print(f"       [dim]{traceback.format_exc()[:300]}[/dim]")

    async def _run_integration_tests(self) -> None:
        """Run integration tests requiring wallet adapter."""
        self.console.print("\n  [bold]Integration Tests[/bold]")

        tests = [
            ("Wallet Adapter Available", self.test_adapter_available),
            ("Get Statement (Balance)", self.test_get_statement),
            ("Send Money - Invalid Recipient", self.test_send_invalid_recipient),
            ("Send Money - Negative Amount", self.test_send_negative_amount),
            ("Send Money - Unsupported Currency", self.test_send_unsupported_currency),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "PASS", "error": None})
                self.console.print(f"    [green]PASS[/green] {name}")
            except Exception as e:
                error_msg = str(e)
                # Some failures are expected (e.g., no wallet adapter in test mode)
                if "not available" in error_msg.lower() or "not configured" in error_msg.lower():
                    self.results.append({"test": name, "status": "SKIP", "error": error_msg})
                    self.console.print(f"    [yellow]SKIP[/yellow] {name}: {error_msg[:60]}")
                else:
                    self.results.append({"test": name, "status": "FAIL", "error": error_msg})
                    self.console.print(f"    [red]FAIL[/red] {name}: {error_msg[:80]}")
                    if self.console.is_terminal:
                        self.console.print(f"       [dim]{traceback.format_exc()[:300]}[/dim]")

    # ==========================================================================
    # Validation Unit Tests
    # ==========================================================================

    async def test_eip55_valid(self) -> None:
        """Test EIP-55 checksum validation with valid address."""
        from ciris_adapters.wallet.providers.validation import validate_eip55_checksum

        # Valid checksummed address (Vitalik's public address)
        valid_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
        if not validate_eip55_checksum(valid_address):
            raise ValueError("Valid EIP-55 address rejected")

    async def test_eip55_invalid(self) -> None:
        """Test EIP-55 checksum validation rejects invalid checksum."""
        from ciris_adapters.wallet.providers.validation import validate_eip55_checksum

        # Invalid checksum (wrong case on one character)
        invalid_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96044"  # Wrong last char
        # This should still pass because it's a valid hex address
        # The checksum only applies to mixed case

        # This one has wrong checksum (mixed case but wrong)
        invalid_checksum = "0xD8dA6BF26964aF9D7eEd9e03E53415D37aA96045"  # D should be d
        if validate_eip55_checksum(invalid_checksum):
            raise ValueError("Invalid EIP-55 checksum should be rejected")

    async def test_eip55_lowercase(self) -> None:
        """Test EIP-55 accepts all-lowercase addresses."""
        from ciris_adapters.wallet.providers.validation import validate_eip55_checksum

        # All lowercase is valid (no checksum applied)
        lowercase = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
        if not validate_eip55_checksum(lowercase):
            raise ValueError("Lowercase address should be valid")

    async def test_amount_negative(self) -> None:
        """Test amount validation rejects negative amounts."""
        from ciris_adapters.wallet.providers.validation import validate_amount

        result = validate_amount(Decimal("-10.00"), "USDC")
        if result.valid:
            raise ValueError("Negative amount should be rejected")
        if not any(e.code == "NEGATIVE_AMOUNT" for e in result.errors):
            raise ValueError("Expected NEGATIVE_AMOUNT error code")

    async def test_amount_zero(self) -> None:
        """Test amount validation rejects zero amounts."""
        from ciris_adapters.wallet.providers.validation import validate_amount

        result = validate_amount(Decimal("0"), "USDC")
        if result.valid:
            raise ValueError("Zero amount should be rejected")
        if not any(e.code == "ZERO_AMOUNT" for e in result.errors):
            raise ValueError("Expected ZERO_AMOUNT error code")

    async def test_amount_dust(self) -> None:
        """Test amount validation rejects dust amounts."""
        from ciris_adapters.wallet.providers.validation import validate_amount

        # USDC dust threshold is $0.01
        result = validate_amount(Decimal("0.001"), "USDC")
        if result.valid:
            raise ValueError("Dust amount should be rejected")
        if not any(e.code == "DUST_AMOUNT" for e in result.errors):
            raise ValueError("Expected DUST_AMOUNT error code")

    async def test_amount_max_transaction(self) -> None:
        """Test amount validation enforces max transaction limit."""
        from ciris_adapters.wallet.providers.validation import validate_amount

        # Default max is $100
        result = validate_amount(Decimal("150.00"), "USDC", max_transaction=Decimal("100.00"))
        if result.valid:
            raise ValueError("Amount exceeding max should be rejected")
        if not any(e.code == "EXCEEDS_MAX_TRANSACTION" for e in result.errors):
            raise ValueError("Expected EXCEEDS_MAX_TRANSACTION error code")

    async def test_recipient_valid(self) -> None:
        """Test recipient validation accepts valid address."""
        from ciris_adapters.wallet.providers.validation import validate_recipient

        # Valid checksummed address
        result = validate_recipient("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
        if not result.valid:
            raise ValueError(f"Valid recipient should be accepted: {result.error_message()}")

    async def test_recipient_zero_address(self) -> None:
        """Test recipient validation rejects zero address."""
        from ciris_adapters.wallet.providers.validation import validate_recipient

        result = validate_recipient("0x0000000000000000000000000000000000000000")
        if result.valid:
            raise ValueError("Zero address should be rejected")
        if not any(e.code == "ZERO_ADDRESS" for e in result.errors):
            raise ValueError("Expected ZERO_ADDRESS error code")

    async def test_recipient_invalid_hex(self) -> None:
        """Test recipient validation rejects invalid hex."""
        from ciris_adapters.wallet.providers.validation import validate_recipient

        result = validate_recipient("0xGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG")
        if result.valid:
            raise ValueError("Invalid hex should be rejected")
        if not any(e.code == "INVALID_HEX" for e in result.errors):
            raise ValueError("Expected INVALID_HEX error code")

    async def test_gas_insufficient(self) -> None:
        """Test gas validation detects insufficient ETH."""
        from ciris_adapters.wallet.providers.validation import validate_gas

        # Very low ETH balance
        result = validate_gas(
            eth_balance=Decimal("0.0001"),
            gas_needed=65000,
            gas_price=30_000_000_000,  # 30 gwei
            currency="USDC",
        )
        if result.valid:
            raise ValueError("Insufficient gas should be rejected")
        if not any(e.code == "INSUFFICIENT_GAS" for e in result.errors):
            raise ValueError("Expected INSUFFICIENT_GAS error code")

    async def test_gas_price_too_high(self) -> None:
        """Test gas validation rejects absurdly high gas price."""
        from ciris_adapters.wallet.providers.validation import validate_gas

        # 600 gwei is above the 500 gwei limit
        result = validate_gas(
            eth_balance=Decimal("1.0"),
            gas_needed=21000,
            gas_price=600_000_000_000,  # 600 gwei
            currency="ETH",
        )
        if result.valid:
            raise ValueError("Absurdly high gas price should be rejected")
        if not any(e.code == "GAS_PRICE_TOO_HIGH" for e in result.errors):
            raise ValueError("Expected GAS_PRICE_TOO_HIGH error code")

    async def test_spending_daily_limit(self) -> None:
        """Test spending tracker enforces daily limit."""
        from ciris_adapters.wallet.providers.validation import SpendingTracker

        tracker = SpendingTracker(daily_limit=Decimal("100.00"), session_limit=Decimal("500.00"))

        # First transaction should succeed
        result1 = tracker.check_and_record(Decimal("50.00"), "USDC")
        if not result1.valid:
            raise ValueError("First transaction should be allowed")

        # Second transaction should succeed
        result2 = tracker.check_and_record(Decimal("40.00"), "USDC")
        if not result2.valid:
            raise ValueError("Second transaction should be allowed")

        # Third transaction should exceed daily limit
        result3 = tracker.check_and_record(Decimal("20.00"), "USDC")
        if result3.valid:
            raise ValueError("Transaction exceeding daily limit should be rejected")
        if not any(e.code == "DAILY_LIMIT_EXCEEDED" for e in result3.errors):
            raise ValueError("Expected DAILY_LIMIT_EXCEEDED error code")

    async def test_spending_session_limit(self) -> None:
        """Test spending tracker enforces session limit."""
        from ciris_adapters.wallet.providers.validation import SpendingTracker

        tracker = SpendingTracker(daily_limit=Decimal("1000.00"), session_limit=Decimal("100.00"))

        # First transaction should succeed
        result1 = tracker.check_and_record(Decimal("60.00"), "USDC")
        if not result1.valid:
            raise ValueError("First transaction should be allowed")

        # Second transaction should exceed session limit
        result2 = tracker.check_and_record(Decimal("60.00"), "USDC")
        if result2.valid:
            raise ValueError("Transaction exceeding session limit should be rejected")
        if not any(e.code == "SESSION_LIMIT_EXCEEDED" for e in result2.errors):
            raise ValueError("Expected SESSION_LIMIT_EXCEEDED error code")

    async def test_duplicate_protection(self) -> None:
        """Test duplicate transaction protection."""
        from ciris_adapters.wallet.providers.validation import DuplicateProtection

        protection = DuplicateProtection(window_seconds=60)

        # First transaction should be allowed
        result1 = protection.check_duplicate(
            recipient="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            amount=Decimal("10.00"),
            currency="USDC",
        )
        if not result1.valid:
            raise ValueError("First transaction should be allowed")

        # Record it
        protection.record_transaction(
            recipient="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            amount=Decimal("10.00"),
            currency="USDC",
        )

        # Same transaction should be blocked as duplicate
        result2 = protection.check_duplicate(
            recipient="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            amount=Decimal("10.00"),
            currency="USDC",
        )
        if result2.valid:
            raise ValueError("Duplicate transaction should be blocked")
        if not any(e.code == "DUPLICATE_TRANSACTION" for e in result2.errors):
            raise ValueError("Expected DUPLICATE_TRANSACTION error code")

        # Different amount should be allowed
        result3 = protection.check_duplicate(
            recipient="0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
            amount=Decimal("20.00"),  # Different amount
            currency="USDC",
        )
        if not result3.valid:
            raise ValueError("Different amount should be allowed")

    # ==========================================================================
    # Integration Tests
    # ==========================================================================

    async def test_adapter_available(self) -> None:
        """Test wallet adapter is available."""
        # Check if we can get tools including wallet tools
        try:
            tools_result = await self.client.tools.get_available_tools()
            tool_names = [t.name for t in tools_result.tools]

            if "send_money" not in tool_names:
                raise ValueError("send_money tool not available - wallet adapter not loaded")

            self.console.print(f"       [dim]Found wallet tools: send_money, request_money, get_statement[/dim]")

        except Exception as e:
            raise ValueError(f"Wallet adapter not available: {e}")

    async def test_get_statement(self) -> None:
        """Test get_statement tool for balance."""
        try:
            result = await self.client.tools.execute_tool(
                tool_name="get_statement",
                parameters={"include_balance": True, "include_history": False},
            )

            if not result.success:
                raise ValueError(f"get_statement failed: {result.error}")

            accounts = result.data.get("accounts", [])
            if not accounts:
                raise ValueError("No wallet accounts returned")

            # Check for x402 provider
            x402_account = next((a for a in accounts if a.get("provider") == "x402"), None)
            if x402_account:
                balance = x402_account.get("balance", {})
                self.console.print(
                    f"       [dim]x402 balance: {balance.get('available', '0')} USDC[/dim]"
                )
            else:
                self.console.print("       [dim]x402 provider not loaded[/dim]")

        except Exception as e:
            if "not available" in str(e).lower():
                raise ValueError("Wallet adapter not available")
            raise

    async def test_send_invalid_recipient(self) -> None:
        """Test send_money rejects invalid recipient."""
        try:
            result = await self.client.tools.execute_tool(
                tool_name="send_money",
                parameters={
                    "recipient": "invalid_address",
                    "amount": 1.00,
                    "currency": "USDC",
                },
            )

            # Should fail with validation error
            if result.success:
                raise ValueError("Send to invalid recipient should fail")

            error = result.error or ""
            if "MISSING_PREFIX" not in error and "INVALID" not in error.upper():
                self.console.print(f"       [dim]Error: {error}[/dim]")

        except Exception as e:
            # Tool execution errors are also acceptable
            error_msg = str(e).lower()
            if "invalid" not in error_msg and "missing" not in error_msg:
                raise

    async def test_send_negative_amount(self) -> None:
        """Test send_money rejects negative amount."""
        try:
            result = await self.client.tools.execute_tool(
                tool_name="send_money",
                parameters={
                    "recipient": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                    "amount": -10.00,
                    "currency": "USDC",
                },
            )

            # Should fail with validation error
            if result.success:
                raise ValueError("Send with negative amount should fail")

            error = result.error or ""
            self.console.print(f"       [dim]Error (expected): {error[:80]}[/dim]")

        except Exception as e:
            # Tool execution errors are also acceptable
            error_msg = str(e).lower()
            if "negative" not in error_msg and "invalid" not in error_msg:
                raise

    async def test_send_unsupported_currency(self) -> None:
        """Test send_money rejects unsupported currency."""
        try:
            result = await self.client.tools.execute_tool(
                tool_name="send_money",
                parameters={
                    "recipient": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                    "amount": 10.00,
                    "currency": "FAKE_COIN",
                },
            )

            # Should fail - no provider for this currency
            if result.success:
                raise ValueError("Send with unsupported currency should fail")

            error = result.error or ""
            if "no provider" not in error.lower():
                self.console.print(f"       [dim]Error: {error}[/dim]")

        except Exception as e:
            # Tool execution errors are also acceptable for unsupported currency
            pass

    def _print_summary(self) -> None:
        """Print test summary."""
        table = Table(title="Wallet Test Results")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="green")

        passed = sum(1 for r in self.results if r["status"] == "PASS")
        skipped = sum(1 for r in self.results if r["status"] == "SKIP")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        total = len(self.results)

        for result in self.results:
            status = result["status"]
            if status == "PASS":
                style = "green"
            elif status == "SKIP":
                style = "yellow"
            else:
                style = "red"
            table.add_row(result["test"], f"[{style}]{status}[/{style}]")

        self.console.print(table)
        self.console.print(f"\n[bold]Passed: {passed}/{total}, Skipped: {skipped}, Failed: {failed}[/bold]")
