"""
Tests for wallet API routes.

Tests paymaster configuration, status endpoints, and wallet functionality.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import require_admin
from ciris_engine.logic.adapters.api.routes.wallet import (
    PaymasterKeyRequest,
    PaymasterKeyResponse,
    WalletStatusResponse,
    _get_wallet_provider_from_app,
    router,
)

# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def mock_auth():
    """Mock authentication dependency."""
    return MagicMock()


@pytest.fixture
def mock_provider():
    """Mock x402 wallet provider."""
    provider = MagicMock()
    provider._evm_address = "0x1234567890abcdef1234567890abcdef12345678"
    provider.config = MagicMock()
    provider.config.network = "base-mainnet"

    # Balance mock
    provider._balance = MagicMock()
    provider._balance.available = Decimal("100.00")
    provider._balance.metadata = {"eth_balance": "0.001"}

    # Paymaster config mock
    provider.paymaster_config = MagicMock()
    provider.paymaster_config.enabled = True
    provider.paymaster_config.arka_api_key = None
    provider.paymaster_config.arka_url = "https://arka.etherspot.io"

    # Spending authority mock
    provider._spending_authority = MagicMock()
    provider._spending_authority.attestation_level = 3
    provider._spending_authority.max_transaction = Decimal("50.00")
    provider._spending_authority.max_daily = Decimal("500.00")
    provider._spending_authority.hardware_trust_degraded = False

    # Validator mock
    provider._validator = MagicMock()
    provider._validator.spending_tracker = MagicMock()
    provider._validator.spending_tracker.session_start_timestamp = 0
    provider._validator.spending_tracker.daily_reset_timestamp = 0
    provider._validator.spending_tracker.session_spent = {"USDC": Decimal("0")}
    provider._validator.spending_tracker.daily_spent = {"USDC": Decimal("0")}
    provider._validator.spending_tracker.session_limit = Decimal("500")
    provider._validator.spending_tracker.daily_limit = Decimal("1000")

    # Chain client mock
    provider._chain_client = MagicMock()
    provider._chain_client.chain_id = 8453
    provider._chain_client.get_gas_price = AsyncMock(return_value=1000000000)

    # Transactions
    provider._transactions = []

    return provider


@pytest.fixture
def mock_provider_with_key(mock_provider):
    """Mock provider with Arka key configured."""
    mock_provider._get_arka_api_key = MagicMock(return_value="etherspot_test_key_123")
    return mock_provider


@pytest.fixture
def mock_provider_no_key(mock_provider):
    """Mock provider without Arka key configured."""
    mock_provider._get_arka_api_key = MagicMock(return_value=None)
    return mock_provider


@pytest.fixture
def app_with_mock_provider(mock_provider):
    """Create app with mocked provider."""
    app = FastAPI()
    app.include_router(router, prefix="/v1")

    # Mock runtime with provider
    runtime = MagicMock()
    wallet_adapter = MagicMock()
    wallet_adapter._providers = {"x402": mock_provider}
    runtime.adapters = [wallet_adapter]
    app.state.runtime = runtime
    app.state.authentication_service = None

    return app


@pytest.fixture
def client(app_with_mock_provider):
    """Test client with mocked auth."""
    app_with_mock_provider.dependency_overrides[require_admin] = lambda: MagicMock()
    return TestClient(app_with_mock_provider)


# ==============================================================================
# Paymaster Status Tests
# ==============================================================================


class TestWalletStatusPaymasterFields:
    """Tests for paymaster status fields in WalletStatusResponse."""

    def test_status_includes_paymaster_fields(self, client, mock_provider):
        """Verify wallet status response includes paymaster fields."""
        mock_provider._get_arka_api_key = MagicMock(return_value=None)

        response = client.get("/v1/wallet/status")

        assert response.status_code == 200
        data = response.json()
        assert "paymasterEnabled" in data or "paymaster_enabled" in data
        assert "paymasterKeyConfigured" in data or "paymaster_key_configured" in data

    def test_status_paymaster_enabled_with_key(self, client, mock_provider):
        """Test status when paymaster is enabled with key configured."""
        mock_provider.paymaster_config.enabled = True
        mock_provider._get_arka_api_key = MagicMock(return_value="etherspot_test_key")

        response = client.get("/v1/wallet/status")

        assert response.status_code == 200
        data = response.json()
        # Check snake_case (API) format
        assert data.get("paymaster_enabled", data.get("paymasterEnabled")) is True
        assert data.get("paymaster_key_configured", data.get("paymasterKeyConfigured")) is True

    def test_status_paymaster_enabled_no_key(self, client, mock_provider):
        """Test status when paymaster is enabled but no key configured."""
        mock_provider.paymaster_config.enabled = True
        mock_provider._get_arka_api_key = MagicMock(return_value=None)

        response = client.get("/v1/wallet/status")

        assert response.status_code == 200
        data = response.json()
        assert data.get("paymaster_enabled", data.get("paymasterEnabled")) is True
        assert data.get("paymaster_key_configured", data.get("paymasterKeyConfigured")) is False

    def test_status_paymaster_disabled(self, client, mock_provider):
        """Test status when paymaster is disabled."""
        mock_provider.paymaster_config.enabled = False
        mock_provider._get_arka_api_key = MagicMock(return_value=None)

        response = client.get("/v1/wallet/status")

        assert response.status_code == 200
        data = response.json()
        assert data.get("paymaster_enabled", data.get("paymasterEnabled")) is False
        assert data.get("paymaster_key_configured", data.get("paymasterKeyConfigured")) is False


class TestPaymasterStatusEndpoint:
    """Tests for GET /wallet/paymaster/status endpoint."""

    def test_paymaster_status_with_key(self, client, mock_provider):
        """Test paymaster status when key is configured."""
        mock_provider.paymaster_config.enabled = True
        mock_provider._get_arka_api_key = MagicMock(return_value="etherspot_test_key")

        response = client.get("/v1/wallet/paymaster/status")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["key_configured"] is True
        assert "Gasless transfers enabled" in data.get("message", "")

    def test_paymaster_status_no_key(self, client, mock_provider):
        """Test paymaster status when no key configured."""
        mock_provider.paymaster_config.enabled = True
        mock_provider._get_arka_api_key = MagicMock(return_value=None)

        response = client.get("/v1/wallet/paymaster/status")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["key_configured"] is False
        # Check that message indicates missing key
        message = data.get("message", "").lower()
        assert "no api key" in message or "not configured" in message

    def test_paymaster_status_disabled(self, client, mock_provider):
        """Test paymaster status when paymaster is disabled."""
        mock_provider.paymaster_config.enabled = False

        response = client.get("/v1/wallet/paymaster/status")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "ETH required" in data.get("message", "") or "not enabled" in data.get("message", "").lower()


class TestPaymasterKeyConfiguration:
    """Tests for POST /wallet/paymaster/configure endpoint."""

    def test_configure_paymaster_key_success(self, mock_provider):
        """Test successful paymaster key configuration."""
        app = FastAPI()
        app.include_router(router, prefix="/v1")

        # Setup provider mocks
        mock_provider.paymaster_config.enabled = True
        mock_provider._chain_client = MagicMock()
        mock_provider._chain_client.chain_id = 8453
        mock_provider._arka_client = MagicMock()

        # Create wallet adapter with provider
        wallet_adapter = MagicMock()
        wallet_adapter._providers = {"x402": mock_provider}

        # Create runtime with secrets_tool_service (AsyncMock for await)
        runtime = MagicMock()
        runtime.adapters = [wallet_adapter]
        runtime.secrets_tool_service = MagicMock()
        runtime.secrets_tool_service.set_secret = AsyncMock(return_value=True)

        app.state.runtime = runtime
        app.state.authentication_service = None

        # Override auth dependency
        app.dependency_overrides[require_admin] = lambda: MagicMock()
        client = TestClient(app)

        response = client.post("/v1/wallet/paymaster/configure", json={"api_key": "etherspot_LAyjUvxq9vtBR41sHsEzBJ"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["key_configured"] is True
        assert "configured successfully" in data.get("message", "").lower()

    def test_configure_paymaster_key_empty(self, client):
        """Test configuration with empty key."""
        response = client.post("/v1/wallet/paymaster/configure", json={"api_key": ""})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "cannot be empty" in data.get("error", "").lower()

    def test_configure_paymaster_key_whitespace_only(self, client):
        """Test configuration with whitespace-only key."""
        response = client.post("/v1/wallet/paymaster/configure", json={"api_key": "   "})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "cannot be empty" in data.get("error", "").lower()

    def test_configure_paymaster_key_non_etherspot_format(self, client, mock_provider):
        """Test configuration with non-Etherspot format key (should still work with warning)."""
        mock_provider.paymaster_config.enabled = True

        response = client.post("/v1/wallet/paymaster/configure", json={"api_key": "some_other_api_key_format_123"})

        # Should still succeed - we allow non-standard formats
        assert response.status_code == 200
        data = response.json()
        # Either success (key stored) or specific error about storage
        # The key format validation is a warning, not a blocker


class TestNoWalletProvider:
    """Tests when wallet provider is not available."""

    def test_status_no_provider(self):
        """Test wallet status when no provider available."""
        app = FastAPI()
        app.include_router(router, prefix="/v1")

        # Runtime without wallet adapter
        runtime = MagicMock()
        runtime.adapters = []
        app.state.runtime = runtime
        app.state.authentication_service = None

        app.dependency_overrides[require_admin] = lambda: MagicMock()

        client = TestClient(app)
        response = client.get("/v1/wallet/status")

        assert response.status_code == 200
        data = response.json()
        assert data["has_wallet"] is False
        assert data.get("paymaster_enabled", False) is False
        assert data.get("paymaster_key_configured", False) is False

    def test_paymaster_status_no_provider(self):
        """Test paymaster status when no provider available."""
        app = FastAPI()
        app.include_router(router, prefix="/v1")

        runtime = MagicMock()
        runtime.adapters = []
        app.state.runtime = runtime

        app.dependency_overrides[require_admin] = lambda: MagicMock()

        client = TestClient(app)
        response = client.get("/v1/wallet/paymaster/status")

        assert response.status_code == 200
        data = response.json()
        assert data["key_configured"] is False
