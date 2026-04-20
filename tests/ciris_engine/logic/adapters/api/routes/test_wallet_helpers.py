"""
Unit tests for wallet.py helper functions.

Tests the extracted helper functions that reduce cognitive complexity
in get_wallet_status() endpoint.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from typing import Any

from ciris_engine.logic.adapters.api.routes.wallet import (
    AttestationInfo,
    _get_attestation_info,
    _get_balance_info,
    _get_spending_progress,
    _get_gas_estimate,
    _get_recent_transactions,
    _get_paymaster_status,
    SpendingProgress,
    GasEstimate,
    TransactionSummary,
    SecurityAdvisory,
)


# =============================================================================
# AttestationInfo Tests
# =============================================================================


class TestAttestationInfo:
    """Tests for AttestationInfo data class."""

    def test_default_values(self):
        """AttestationInfo defaults to receive-only level 0."""
        info = AttestationInfo()
        assert info.level == 0
        assert info.max_tx == "0.00"
        assert info.daily == "0.00"
        assert info.is_receive_only is True
        assert info.hardware_degraded is False
        assert info.degradation_reason is None
        assert info.security_advisories == []

    def test_custom_values(self):
        """AttestationInfo accepts custom values."""
        advisories = [
            SecurityAdvisory(cve="CVE-2024-1234", title="Test", impact="High", remediation="Patch")
        ]
        info = AttestationInfo(
            level=3,
            max_tx="100.00",
            daily="500.00",
            is_receive_only=False,
            hardware_degraded=True,
            degradation_reason="Old TEE firmware",
            security_advisories=advisories,
        )
        assert info.level == 3
        assert info.max_tx == "100.00"
        assert info.daily == "500.00"
        assert info.is_receive_only is False
        assert info.hardware_degraded is True
        assert info.degradation_reason == "Old TEE firmware"
        assert len(info.security_advisories) == 1


# =============================================================================
# _get_attestation_info Tests
# =============================================================================


class TestGetAttestationInfo:
    """Tests for _get_attestation_info helper."""

    def test_no_auth_service_returns_defaults(self):
        """Returns default AttestationInfo when auth service unavailable."""
        request = Mock()
        request.app.state = Mock(spec=[])  # No authentication_service attr

        info = _get_attestation_info(request)

        assert info.level == 0
        assert info.is_receive_only is True

    def test_no_cached_attestation_returns_defaults(self):
        """Returns defaults when no cached attestation available."""
        request = Mock()
        auth_service = Mock()
        auth_service.get_cached_attestation.return_value = None
        request.app.state.authentication_service = auth_service

        info = _get_attestation_info(request)

        assert info.level == 0
        assert info.is_receive_only is True

    def test_with_cached_attestation(self):
        """Returns attestation info from cached result."""
        request = Mock()
        auth_service = Mock()

        # Mock cached attestation result
        cached_result = Mock()
        cached_result.max_level = 3
        cached_result.hardware_trust_degraded = False
        cached_result.trust_degradation_reason = None
        cached_result.security_advisories = None
        auth_service.get_cached_attestation.return_value = cached_result

        request.app.state.authentication_service = auth_service

        # Mock SpendingAuthority
        with patch(
            "ciris_adapters.wallet.providers.x402_provider.SpendingAuthority"
        ) as mock_sa:
            mock_authority = Mock()
            mock_authority.max_transaction = Decimal("100")
            mock_authority.max_daily = Decimal("500")
            mock_sa.from_attestation.return_value = mock_authority

            info = _get_attestation_info(request)

            assert info.level == 3
            assert info.max_tx == "100"
            assert info.daily == "500"
            assert info.is_receive_only is False

    def test_with_security_advisories(self):
        """Extracts security advisories from cached result."""
        request = Mock()
        auth_service = Mock()

        cached_result = Mock()
        cached_result.max_level = 2
        cached_result.hardware_trust_degraded = True
        cached_result.trust_degradation_reason = "TEE vulnerability"
        cached_result.security_advisories = [
            {"cve": "CVE-2024-1234", "title": "Test CVE", "impact": "High", "remediation": "Update"}
        ]
        auth_service.get_cached_attestation.return_value = cached_result

        request.app.state.authentication_service = auth_service

        with patch(
            "ciris_adapters.wallet.providers.x402_provider.SpendingAuthority"
        ) as mock_sa:
            mock_authority = Mock()
            mock_authority.max_transaction = Decimal("50")
            mock_authority.max_daily = Decimal("200")
            mock_sa.from_attestation.return_value = mock_authority

            info = _get_attestation_info(request)

            assert info.level == 2
            assert info.hardware_degraded is True
            assert info.degradation_reason == "TEE vulnerability"
            assert len(info.security_advisories) == 1
            assert info.security_advisories[0].cve == "CVE-2024-1234"

    def test_exception_returns_defaults(self):
        """Returns defaults when exception occurs."""
        request = Mock()
        auth_service = Mock()
        auth_service.get_cached_attestation.side_effect = Exception("Auth error")
        request.app.state.authentication_service = auth_service

        info = _get_attestation_info(request)

        assert info.level == 0
        assert info.is_receive_only is True


# =============================================================================
# _get_balance_info Tests
# =============================================================================


class TestGetBalanceInfo:
    """Tests for _get_balance_info helper."""

    def test_no_balance_attribute(self):
        """Returns zeros when provider has no _balance."""
        provider = Mock(spec=[])

        balance, eth_balance, needs_gas = _get_balance_info(provider)

        assert balance == "0.00"
        assert eth_balance == "0.00"
        assert needs_gas is True

    def test_with_balance_no_metadata(self):
        """Returns balance when metadata is None."""
        provider = Mock()
        provider._balance = Mock()
        provider._balance.available = Decimal("123.45")
        provider._balance.metadata = None

        balance, eth_balance, needs_gas = _get_balance_info(provider)

        assert balance == "123.45"
        assert eth_balance == "0.00"
        assert needs_gas is True

    def test_with_balance_and_eth(self):
        """Returns both balances when available."""
        provider = Mock()
        provider._balance = Mock()
        provider._balance.available = Decimal("100.00")
        provider._balance.metadata = {"eth_balance": "0.05"}

        balance, eth_balance, needs_gas = _get_balance_info(provider)

        assert balance == "100.00"
        assert eth_balance == "0.05"
        assert needs_gas is False

    def test_low_gas_threshold(self):
        """needs_gas is True when ETH below 0.0001."""
        provider = Mock()
        provider._balance = Mock()
        provider._balance.available = Decimal("100.00")
        provider._balance.metadata = {"eth_balance": "0.00009"}

        balance, eth_balance, needs_gas = _get_balance_info(provider)

        assert needs_gas is True

    def test_exactly_at_threshold(self):
        """needs_gas is False when ETH exactly at 0.0001."""
        provider = Mock()
        provider._balance = Mock()
        provider._balance.available = Decimal("100.00")
        provider._balance.metadata = {"eth_balance": "0.0001"}

        balance, eth_balance, needs_gas = _get_balance_info(provider)

        assert needs_gas is False

    def test_invalid_eth_balance(self):
        """needs_gas is True for invalid ETH balance string."""
        provider = Mock()
        provider._balance = Mock()
        provider._balance.available = Decimal("100.00")
        provider._balance.metadata = {"eth_balance": "invalid"}

        balance, eth_balance, needs_gas = _get_balance_info(provider)

        assert needs_gas is True


# =============================================================================
# _get_spending_progress Tests
# =============================================================================


class TestGetSpendingProgress:
    """Tests for _get_spending_progress helper."""

    def test_no_validator(self):
        """Returns None when provider has no validator."""
        provider = Mock(spec=[])

        progress = _get_spending_progress(provider)

        assert progress is None

    def test_with_validator(self):
        """Returns SpendingProgress from validator tracker."""
        provider = Mock()
        validator = Mock()
        tracker = Mock()

        # Mock tracker attributes
        import time

        tracker.session_start_timestamp = time.time() - 1800  # 30 min ago
        tracker.daily_reset_timestamp = time.time() - 43200  # 12 hours ago
        tracker.session_spent = {"USDC": Decimal("50.00")}
        tracker.daily_spent = {"USDC": Decimal("200.00")}
        tracker.session_limit = Decimal("500.00")
        tracker.daily_limit = Decimal("1000.00")

        validator.spending_tracker = tracker
        provider._validator = validator

        progress = _get_spending_progress(provider)

        assert progress is not None
        assert progress.session_spent == "50.00"
        assert progress.session_remaining == "450.00"
        assert progress.session_limit == "500.00"
        # Allow ±1 minute tolerance for test execution time
        assert 29 <= progress.session_reset_minutes <= 31
        assert progress.daily_spent == "200.00"
        assert progress.daily_remaining == "800.00"
        # Allow ±1 hour tolerance for test execution time
        assert 11 <= progress.daily_reset_hours <= 13

    def test_exception_returns_none(self):
        """Returns None when exception occurs."""
        provider = Mock()
        provider._validator = Mock()
        provider._validator.spending_tracker = Mock()
        provider._validator.spending_tracker.session_start_timestamp = "invalid"

        progress = _get_spending_progress(provider)

        assert progress is None


# =============================================================================
# _get_gas_estimate Tests
# =============================================================================


class TestGetGasEstimate:
    """Tests for _get_gas_estimate helper."""

    @pytest.mark.asyncio
    async def test_no_chain_client(self):
        """Returns None when provider has no chain client."""
        provider = Mock(spec=[])

        estimate = await _get_gas_estimate(provider)

        assert estimate is None

    @pytest.mark.asyncio
    async def test_with_chain_client(self):
        """Returns GasEstimate from chain client."""
        provider = Mock()
        chain_client = AsyncMock()
        chain_client.get_gas_price.return_value = 1_000_000_000  # 1 gwei
        provider._chain_client = chain_client

        estimate = await _get_gas_estimate(provider)

        assert estimate is not None
        assert estimate.gas_price_gwei == "1.00"
        assert estimate.usdc_transfer_gas == 65000
        assert estimate.eth_transfer_gas == 21000

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        """Returns None when gas price fetch times out."""
        import asyncio

        provider = Mock()
        chain_client = AsyncMock()

        async def slow_gas_price():
            await asyncio.sleep(10)
            return 1_000_000_000

        chain_client.get_gas_price = slow_gas_price
        provider._chain_client = chain_client

        # This should timeout after 2s
        estimate = await _get_gas_estimate(provider)

        assert estimate is None

    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        """Returns None when chain client raises exception."""
        provider = Mock()
        chain_client = AsyncMock()
        chain_client.get_gas_price.side_effect = Exception("RPC error")
        provider._chain_client = chain_client

        estimate = await _get_gas_estimate(provider)

        assert estimate is None


# =============================================================================
# _get_recent_transactions Tests
# =============================================================================


class TestGetRecentTransactions:
    """Tests for _get_recent_transactions helper."""

    def test_no_transactions(self):
        """Returns empty list when no transactions."""
        provider = Mock(spec=[])

        transactions = _get_recent_transactions(provider)

        assert transactions == []

    def test_empty_transactions(self):
        """Returns empty list when transactions list is empty."""
        provider = Mock()
        provider._transactions = []

        transactions = _get_recent_transactions(provider)

        assert transactions == []

    def test_with_transactions(self):
        """Returns TransactionSummary list from transactions."""
        from datetime import datetime
        from enum import Enum

        class TxType(Enum):
            SEND = "send"

        class TxStatus(Enum):
            CONFIRMED = "confirmed"

        provider = Mock()
        tx = Mock()
        tx.transaction_id = "tx123"
        tx.type = TxType.SEND
        tx.amount = Decimal("-50.00")
        tx.currency = "USDC"
        tx.recipient = "0x1234"
        tx.sender = "0x5678"
        tx.status = TxStatus.CONFIRMED
        tx.timestamp = datetime(2024, 1, 15, 12, 0, 0)
        tx.confirmation = {"explorer_url": "https://basescan.org/tx/123"}
        provider._transactions = [tx]

        transactions = _get_recent_transactions(provider)

        assert len(transactions) == 1
        assert transactions[0].transaction_id == "tx123"
        assert transactions[0].type == "send"
        assert transactions[0].amount == "50.00"  # Absolute value
        assert transactions[0].currency == "USDC"
        assert transactions[0].explorer_url == "https://basescan.org/tx/123"

    def test_respects_limit(self):
        """Returns only up to limit transactions."""
        from datetime import datetime

        provider = Mock()
        transactions_list = []
        for i in range(10):
            tx = Mock()
            tx.transaction_id = f"tx{i}"
            tx.type = "send"
            tx.amount = Decimal("10.00")
            tx.currency = "USDC"
            tx.recipient = "0x1234"
            tx.sender = "0x5678"
            tx.status = "confirmed"
            tx.timestamp = datetime(2024, 1, 15, 12, 0, 0)
            tx.confirmation = None
            transactions_list.append(tx)
        provider._transactions = transactions_list

        # Default limit is 5
        transactions = _get_recent_transactions(provider)
        assert len(transactions) == 5

        # Custom limit
        transactions = _get_recent_transactions(provider, limit=3)
        assert len(transactions) == 3

    def test_handles_parsing_errors(self):
        """Skips transactions that fail to parse."""
        provider = Mock()
        tx1 = Mock()
        tx1.transaction_id = "tx1"
        tx1.timestamp = "invalid"  # Will cause error

        tx2 = Mock()
        tx2.transaction_id = "tx2"
        tx2.type = "send"
        tx2.amount = Decimal("10.00")
        tx2.currency = "USDC"
        tx2.recipient = "0x1234"
        tx2.sender = "0x5678"
        tx2.status = "confirmed"
        from datetime import datetime

        tx2.timestamp = datetime(2024, 1, 15, 12, 0, 0)
        tx2.confirmation = None

        provider._transactions = [tx1, tx2]

        transactions = _get_recent_transactions(provider)

        # Should have 1 transaction (tx2), tx1 should be skipped
        assert len(transactions) == 1
        assert transactions[0].transaction_id == "tx2"


# =============================================================================
# _get_paymaster_status Tests
# =============================================================================


class TestGetPaymasterStatus:
    """Tests for _get_paymaster_status helper."""

    def test_coinbase_paymaster_active(self):
        """Returns (True, True) when Coinbase paymaster is active."""
        provider = Mock()
        provider._coinbase_paymaster = Mock()  # Not None

        enabled, configured = _get_paymaster_status(provider)

        assert enabled is True
        assert configured is True

    def test_no_paymaster(self):
        """Returns (False, False) when no paymaster configured."""
        provider = Mock(spec=[])

        enabled, configured = _get_paymaster_status(provider)

        assert enabled is False
        assert configured is False

    def test_arka_paymaster_with_method(self):
        """Returns Arka paymaster status using _get_arka_api_key method."""
        provider = Mock()
        provider._coinbase_paymaster = None
        provider.paymaster_config = Mock()
        provider.paymaster_config.enabled = True
        provider._get_arka_api_key.return_value = "test-api-key"

        enabled, configured = _get_paymaster_status(provider)

        assert enabled is True
        assert configured is True

    def test_arka_paymaster_no_key(self):
        """Returns (True, False) when Arka enabled but no key."""
        provider = Mock()
        provider._coinbase_paymaster = None
        provider.paymaster_config = Mock()
        provider.paymaster_config.enabled = True
        provider._get_arka_api_key.return_value = None

        enabled, configured = _get_paymaster_status(provider)

        assert enabled is True
        assert configured is False

    def test_arka_paymaster_from_config(self):
        """Returns Arka paymaster status from config attribute."""
        provider = Mock(spec=["paymaster_config"])
        provider.paymaster_config = Mock()
        provider.paymaster_config.enabled = True
        provider.paymaster_config.arka_api_key = "config-key"

        enabled, configured = _get_paymaster_status(provider)

        assert enabled is True
        assert configured is True

    def test_arka_paymaster_disabled(self):
        """Returns (False, False) when Arka paymaster disabled and no key."""
        provider = Mock(spec=["paymaster_config"])
        provider.paymaster_config = Mock()
        provider.paymaster_config.enabled = False
        provider.paymaster_config.arka_api_key = None  # No key configured

        enabled, configured = _get_paymaster_status(provider)

        assert enabled is False
        assert configured is False
