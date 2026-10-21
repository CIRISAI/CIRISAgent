"""
Comprehensive tests for billing endpoints.

This test file covers:
- GET /api/billing/credits - Credit balance and status
- POST /api/billing/purchase/initiate - Create payment intent
- GET /api/billing/purchase/status/{payment_id} - Check payment status
- GET /api/billing/transactions - Transaction history

Tests cover both SimpleCreditProvider and CIRISBillingProvider scenarios,
as well as all error handling paths and the implemented TODOs.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes.billing import (
    ERROR_BILLING_SERVICE_UNAVAILABLE,
    ERROR_CREDIT_PROVIDER_NOT_CONFIGURED,
    ERROR_RESOURCE_MONITOR_UNAVAILABLE,
    _billing_get,
    _billing_post,
    get_credits,
    get_purchase_status,
    get_transactions,
    initiate_purchase,
)
from ciris_engine.schemas.api.auth import AuthContext, UserRole


class TestGetCredits:
    """Test GET /api/billing/credits endpoint."""

    @pytest.fixture
    def mock_auth_context(self):
        """Create mock auth context."""
        auth = Mock(spec=AuthContext)
        auth.user_id = "user-123"
        auth.role = UserRole.OBSERVER
        auth.api_key_id = None  # Required by _derive_credit_account
        return auth

    @pytest.fixture
    def mock_request_no_monitor(self):
        """Mock request without resource monitor."""
        request = Mock()
        request.app.state = Mock(spec=[])  # No resource_monitor attribute
        return request

    @pytest.fixture
    def mock_request_no_credit_provider(self):
        """Mock request with resource monitor but no credit provider."""
        request = Mock()
        request.app.state = Mock()
        request.app.state.resource_monitor = Mock(spec=[])  # No credit_provider attribute
        return request

    @pytest.fixture
    def mock_request_simple_provider_with_credit(self):
        """Mock request with SimpleCreditProvider (has credit)."""
        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None
        request.app.state.runtime = Mock()
        request.app.state.runtime.agent_identity.agent_id = "test-agent"

        # Mock resource monitor with SimpleCreditProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "SimpleCreditProvider"

        # Mock check_credit to return has_credit=True
        async def check_credit_success(*args, **kwargs):
            return Mock(has_credit=True)

        resource_monitor.check_credit = AsyncMock(side_effect=check_credit_success)
        request.app.state.resource_monitor = resource_monitor

        return request

    @pytest.fixture
    def mock_request_simple_provider_no_credit(self):
        """Mock request with SimpleCreditProvider (no credit)."""
        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None
        request.app.state.runtime = Mock()
        request.app.state.runtime.agent_identity.agent_id = "test-agent"

        # Mock resource monitor with SimpleCreditProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "SimpleCreditProvider"

        # Mock check_credit to return has_credit=False
        async def check_credit_exhausted(*args, **kwargs):
            return Mock(has_credit=False)

        resource_monitor.check_credit = AsyncMock(side_effect=check_credit_exhausted)
        request.app.state.resource_monitor = resource_monitor

        return request

    @pytest.mark.asyncio
    async def test_get_credits_no_resource_monitor(self, mock_auth_context, mock_request_no_monitor):
        """Test that missing resource monitor returns 503."""
        with pytest.raises(HTTPException) as exc_info:
            await get_credits(mock_request_no_monitor, mock_auth_context)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == ERROR_RESOURCE_MONITOR_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_get_credits_no_credit_provider(self, mock_auth_context, mock_request_no_credit_provider):
        """Test that no credit provider returns unlimited credits."""
        response = await get_credits(mock_request_no_credit_provider, mock_auth_context)

        assert response.has_credit is True
        assert response.credits_remaining == 999
        assert response.free_uses_remaining == 999
        assert response.plan_name == "unlimited"
        assert response.purchase_required is False

    @pytest.mark.asyncio
    async def test_get_credits_simple_provider_has_credit(
        self, mock_auth_context, mock_request_simple_provider_with_credit
    ):
        """Test SimpleCreditProvider with available free credit."""
        response = await get_credits(mock_request_simple_provider_with_credit, mock_auth_context)

        assert response.has_credit is True
        assert response.credits_remaining == 0
        assert response.free_uses_remaining == 1
        assert response.plan_name == "free"
        assert response.purchase_required is False

    @pytest.mark.asyncio
    async def test_get_credits_simple_provider_no_credit(
        self, mock_auth_context, mock_request_simple_provider_no_credit
    ):
        """Test SimpleCreditProvider with exhausted free credit."""
        response = await get_credits(mock_request_simple_provider_no_credit, mock_auth_context)

        assert response.has_credit is False
        assert response.credits_remaining == 0
        assert response.free_uses_remaining == 0
        assert response.total_uses == 1
        assert response.plan_name == "free"
        assert response.purchase_required is False
        # purchase_options is None for SDK compatibility
        assert response.purchase_options is None

    @pytest.mark.asyncio
    async def test_get_credits_billing_provider_jwt_mode(self, mock_auth_context):
        """Test CIRISBillingProvider in JWT mode (no API key) - uses CreditCheckResult directly."""
        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None
        request.app.state.runtime = Mock()
        request.app.state.runtime.agent_identity.agent_id = "test-agent"

        # Mock resource monitor with CIRISBillingProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"

        async def check_credit_success(*args, **kwargs):
            result = Mock()
            result.has_credit = True
            result.credits_remaining = 45
            result.free_uses_remaining = 5
            result.daily_free_uses_remaining = 0
            return result

        resource_monitor.check_credit = AsyncMock(side_effect=check_credit_success)
        request.app.state.resource_monitor = resource_monitor

        # JWT mode - no API key needed, uses CreditCheckResult directly
        import os

        with pytest.MonkeyPatch.context() as mp:
            mp.delenv("CIRIS_BILLING_API_KEY", raising=False)
            response = await get_credits(request, mock_auth_context)

        assert response.has_credit is True
        assert response.credits_remaining == 45
        assert response.free_uses_remaining == 5
        assert response.plan_name == "CIRIS Mobile"

    @pytest.mark.asyncio
    async def test_get_credits_billing_provider_success(self, mock_auth_context):
        """Test CIRISBillingProvider with successful API call (server mode with API key)."""
        from unittest.mock import patch

        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None
        request.app.state.runtime = Mock()
        request.app.state.runtime.agent_identity.agent_id = "test-agent"

        # Mock resource monitor with CIRISBillingProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"

        async def check_credit_success(*args, **kwargs):
            return Mock(has_credit=True)

        resource_monitor.check_credit = AsyncMock(side_effect=check_credit_success)
        request.app.state.resource_monitor = resource_monitor

        # Mock _billing_post to return expected data
        async def mock_billing_post(*args, **kwargs):
            return {
                "has_credit": True,
                "credits_remaining": 45,
                "free_uses_remaining": 5,
                "total_uses": 12,
                "plan_name": "standard",
                "purchase_required": False,
            }

        # Server mode - with API key, queries billing backend
        import os

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            with patch(
                "ciris_engine.logic.adapters.api.routes.billing._billing_post",
                side_effect=mock_billing_post,
            ):
                response = await get_credits(request, mock_auth_context)

        assert response.has_credit is True
        assert response.credits_remaining == 45
        assert response.free_uses_remaining == 5
        assert response.plan_name == "standard"

    @pytest.mark.asyncio
    async def test_get_credits_billing_provider_api_error(self, mock_auth_context):
        """Test CIRISBillingProvider with API error (server mode with API key)."""
        from unittest.mock import patch

        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None
        request.app.state.runtime = Mock()
        request.app.state.runtime.agent_identity.agent_id = "test-agent"

        # Mock resource monitor with CIRISBillingProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"

        async def check_credit_success(*args, **kwargs):
            return Mock(has_credit=True)

        resource_monitor.check_credit = AsyncMock(side_effect=check_credit_success)
        request.app.state.resource_monitor = resource_monitor

        # Mock _billing_post to raise HTTPException (simulating API error)
        async def mock_billing_post_error(*args, **kwargs):
            raise HTTPException(status_code=503, detail="Billing service unavailable")

        # Server mode - with API key, queries billing backend
        import os

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            with patch(
                "ciris_engine.logic.adapters.api.routes.billing._billing_post",
                side_effect=mock_billing_post_error,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await get_credits(request, mock_auth_context)

        assert exc_info.value.status_code == 503
        assert "Billing service unavailable" in exc_info.value.detail


class TestInitiatePurchase:
    """Test POST /api/billing/purchase/initiate endpoint."""

    @pytest.fixture
    def mock_auth_context(self):
        """Create mock auth context."""
        auth = Mock(spec=AuthContext)
        auth.user_id = "user-123"
        auth.role = UserRole.OBSERVER
        auth.api_key_id = None  # Required by _derive_credit_account
        return auth

    @pytest.fixture
    def mock_purchase_request(self):
        """Mock purchase request."""
        from ciris_engine.logic.adapters.api.routes.billing import PurchaseInitiateRequest

        return PurchaseInitiateRequest(return_url="https://app.example.com/success")

    @pytest.mark.asyncio
    async def test_initiate_purchase_no_resource_monitor(self, mock_auth_context, mock_purchase_request):
        """Test that missing resource monitor returns 503."""
        request = Mock()
        request.app.state = Mock(spec=[])  # No resource_monitor

        with pytest.raises(HTTPException) as exc_info:
            await initiate_purchase(request, mock_purchase_request, mock_auth_context)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == ERROR_RESOURCE_MONITOR_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_initiate_purchase_simple_provider(self, mock_auth_context, mock_purchase_request):
        """Test that SimpleCreditProvider returns 403 (billing not enabled)."""
        request = Mock()
        request.app.state = Mock()

        # Mock resource monitor with SimpleCreditProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "SimpleCreditProvider"
        request.app.state.resource_monitor = resource_monitor

        with pytest.raises(HTTPException) as exc_info:
            await initiate_purchase(request, mock_purchase_request, mock_auth_context)

        assert exc_info.value.status_code == 403
        assert "Billing not enabled" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_initiate_purchase_success_with_email(self, mock_auth_context, mock_purchase_request):
        """Test successful purchase initiation with user email from OAuth."""
        from unittest.mock import patch

        request = Mock()
        request.app.state = Mock()

        # Mock auth service with OAuth user
        auth_service = Mock()
        oauth_user = Mock()
        oauth_user.marketing_opt_in = True
        oauth_user.oauth_email = "user@example.com"
        oauth_user.oauth_provider = None
        oauth_user.oauth_external_id = None
        auth_service.get_user = Mock(return_value=oauth_user)
        request.app.state.auth_service = auth_service

        # Mock resource monitor with CIRISBillingProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"
        request.app.state.resource_monitor = resource_monitor

        # Mock runtime
        request.app.state.runtime = Mock()
        request.app.state.runtime.agent_identity.agent_id = "test-agent"

        # Mock _billing_post to return expected data
        captured_payload = {}

        async def mock_billing_post(base_url, path, headers, json_data):
            captured_payload.update(json_data)
            return {
                "payment_id": "pi_123",
                "client_secret": "pi_123_secret",
                "amount_minor": 500,
                "currency": "USD",
                "uses_purchased": 20,
                "publishable_key": "pk_test_123",
            }

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            with patch(
                "ciris_engine.logic.adapters.api.routes.billing._billing_post",
                side_effect=mock_billing_post,
            ):
                response = await initiate_purchase(request, mock_purchase_request, mock_auth_context)

        assert response.payment_id == "pi_123"
        assert response.client_secret == "pi_123_secret"
        assert response.amount_minor == 500
        assert response.uses_purchased == 20
        assert response.publishable_key == "pk_test_123"

        # Verify customer email was extracted from OAuth
        assert captured_payload.get("customer_email") == "user@example.com"

    @pytest.mark.asyncio
    async def test_initiate_purchase_no_email(self, mock_auth_context, mock_purchase_request):
        """Test purchase rejection when OAuth email not available.

        CRITICAL: Without a valid email, we cannot safely charge the customer
        or send receipts. The request MUST be rejected with 400 error.
        This prevents billing the wrong account or leaking receipts.
        """
        request = Mock()
        request.app.state = Mock()

        # Mock auth service with user without email
        auth_service = Mock()
        user_without_email = Mock()
        user_without_email.marketing_opt_in = False
        user_without_email.oauth_email = None  # No email available
        user_without_email.oauth_provider = None
        user_without_email.oauth_external_id = None
        auth_service.get_user = Mock(return_value=user_without_email)
        request.app.state.auth_service = auth_service

        # Mock resource monitor with CIRISBillingProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"
        request.app.state.resource_monitor = resource_monitor

        # Mock runtime
        request.app.state.runtime = Mock()
        request.app.state.runtime.agent_identity.agent_id = "test-agent"

        # Set API key so billing config can be retrieved
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            # Should raise 400 error - email required for purchase
            with pytest.raises(HTTPException) as exc_info:
                await initiate_purchase(request, mock_purchase_request, mock_auth_context)

        # Verify correct error
        assert exc_info.value.status_code == 400
        assert "Email address required" in exc_info.value.detail
        assert "OAuth provider" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_initiate_purchase_api_error(self, mock_auth_context, mock_purchase_request):
        """Test purchase with billing API error."""
        from unittest.mock import patch

        request = Mock()
        request.app.state = Mock()

        # Mock auth service with OAuth user (has email)
        auth_service = Mock()
        oauth_user = Mock()
        oauth_user.marketing_opt_in = False
        oauth_user.oauth_email = "user@example.com"
        oauth_user.oauth_provider = None
        oauth_user.oauth_external_id = None
        auth_service.get_user = Mock(return_value=oauth_user)
        request.app.state.auth_service = auth_service

        # Mock resource monitor
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"
        request.app.state.resource_monitor = resource_monitor

        # Mock runtime
        request.app.state.runtime = Mock()
        request.app.state.runtime.agent_identity.agent_id = "test-agent"

        # Mock _billing_post to raise HTTPException (simulating network error)
        async def mock_billing_post_error(*args, **kwargs):
            raise HTTPException(status_code=503, detail="Billing service unavailable")

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            with patch(
                "ciris_engine.logic.adapters.api.routes.billing._billing_post",
                side_effect=mock_billing_post_error,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await initiate_purchase(request, mock_purchase_request, mock_auth_context)

        assert exc_info.value.status_code == 503
        assert "Billing service unavailable" in exc_info.value.detail


class TestGetPurchaseStatus:
    """Test GET /api/billing/purchase/status/{payment_id} endpoint."""

    @pytest.fixture
    def mock_auth_context(self):
        """Create mock auth context."""
        auth = Mock(spec=AuthContext)
        auth.user_id = "user-123"
        auth.role = UserRole.OBSERVER
        auth.api_key_id = None  # Required by _derive_credit_account
        return auth

    @pytest.mark.asyncio
    async def test_get_purchase_status_simple_provider(self, mock_auth_context):
        """Test that SimpleCreditProvider returns 404."""
        request = Mock()
        request.app.state = Mock()

        # Mock resource monitor with SimpleCreditProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "SimpleCreditProvider"
        request.app.state.resource_monitor = resource_monitor

        with pytest.raises(HTTPException) as exc_info:
            await get_purchase_status("pi_123", request, mock_auth_context)

        assert exc_info.value.status_code == 404
        assert "Billing not enabled" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_purchase_status_success(self, mock_auth_context):
        """Test successful payment status query."""
        from unittest.mock import patch

        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None

        # Mock resource monitor with CIRISBillingProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"
        request.app.state.resource_monitor = resource_monitor

        # Mock _billing_get to return payment status
        async def mock_billing_get(base_url, path, headers, params=None):
            return {"status": "succeeded", "credits_added": 20}

        # Mock _billing_post to return credits check
        async def mock_billing_post(base_url, path, headers, json_data):
            return {"credits_remaining": 65}

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            with patch(
                "ciris_engine.logic.adapters.api.routes.billing._billing_get",
                side_effect=mock_billing_get,
            ):
                with patch(
                    "ciris_engine.logic.adapters.api.routes.billing._billing_post",
                    side_effect=mock_billing_post,
                ):
                    response = await get_purchase_status("pi_123", request, mock_auth_context)

        assert response.status == "succeeded"
        assert response.credits_added == 20
        assert response.balance_after == 65

    @pytest.mark.asyncio
    async def test_get_purchase_status_pending_404(self, mock_auth_context):
        """Test payment status when payment not found (404)."""
        from unittest.mock import patch

        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None

        # Mock resource monitor
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"
        request.app.state.resource_monitor = resource_monitor

        # Mock _billing_get to return empty response (simulating 404)
        async def mock_billing_get(base_url, path, headers, params=None):
            return {"transactions": [], "total_count": 0, "has_more": False}

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            with patch(
                "ciris_engine.logic.adapters.api.routes.billing._billing_get",
                side_effect=mock_billing_get,
            ):
                response = await get_purchase_status("pi_nonexistent", request, mock_auth_context)

        assert response.status == "pending"
        assert response.credits_added == 0
        assert response.balance_after is None

    @pytest.mark.asyncio
    async def test_get_purchase_status_api_error(self, mock_auth_context):
        """Test payment status with billing API error."""
        from unittest.mock import patch

        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None

        # Mock resource monitor
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"
        request.app.state.resource_monitor = resource_monitor

        # Mock _billing_get to raise HTTPException (simulating server error)
        async def mock_billing_get_error(*args, **kwargs):
            raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            with patch(
                "ciris_engine.logic.adapters.api.routes.billing._billing_get",
                side_effect=mock_billing_get_error,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await get_purchase_status("pi_123", request, mock_auth_context)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == ERROR_BILLING_SERVICE_UNAVAILABLE


class TestGetTransactions:
    """Test GET /api/billing/transactions endpoint."""

    @pytest.fixture
    def mock_auth_context(self):
        """Create mock auth context."""
        auth = Mock(spec=AuthContext)
        auth.user_id = "google:115300315355793131383"
        auth.role = UserRole.OBSERVER
        auth.api_key_id = None
        return auth

    @pytest.mark.asyncio
    async def test_get_transactions_no_resource_monitor(self, mock_auth_context):
        """Test that missing resource monitor returns 503."""
        request = Mock()
        request.app.state = Mock(spec=[])  # No resource_monitor

        with pytest.raises(HTTPException) as exc_info:
            await get_transactions(request, mock_auth_context, limit=50, offset=0)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == ERROR_RESOURCE_MONITOR_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_get_transactions_no_credit_provider(self, mock_auth_context):
        """Test that no credit provider returns empty list."""
        request = Mock()
        request.app.state = Mock()
        request.app.state.resource_monitor = Mock(spec=[])  # No credit_provider

        response = await get_transactions(request, mock_auth_context, limit=50, offset=0)

        assert response.transactions == []
        assert response.total_count == 0
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_get_transactions_simple_provider(self, mock_auth_context):
        """Test that SimpleCreditProvider returns empty list (no transaction tracking)."""
        request = Mock()
        request.app.state = Mock()

        # Mock resource monitor with SimpleCreditProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "SimpleCreditProvider"
        request.app.state.resource_monitor = resource_monitor

        response = await get_transactions(request, mock_auth_context, limit=50, offset=0)

        assert response.transactions == []
        assert response.total_count == 0
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_get_transactions_billing_provider_success(self, mock_auth_context):
        """Test CIRISBillingProvider with successful transaction listing."""
        from unittest.mock import patch

        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None

        # Mock resource monitor with CIRISBillingProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"
        request.app.state.resource_monitor = resource_monitor

        # Capture params for verification
        captured_params = {}

        # Mock _billing_get to return transaction data
        async def mock_billing_get(base_url, path, headers, params=None):
            captured_params.update(params or {})
            return {
                "transactions": [
                    {
                        "transaction_id": "charge_abc123",
                        "type": "charge",
                        "amount_minor": -100,
                        "currency": "USD",
                        "description": "Agent interaction",
                        "created_at": "2025-10-16T12:00:00Z",
                        "balance_after": 900,
                        "metadata": {"agent_id": "test-agent", "channel": "discord"},
                    },
                    {
                        "transaction_id": "credit_xyz789",
                        "type": "credit",
                        "amount_minor": 1000,
                        "currency": "USD",
                        "description": "Purchased 20 uses",
                        "created_at": "2025-10-15T10:00:00Z",
                        "balance_after": 1000,
                        "transaction_type": "purchase",
                        "external_transaction_id": "pi_stripe123",
                    },
                ],
                "total_count": 2,
                "has_more": False,
            }

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            with patch(
                "ciris_engine.logic.adapters.api.routes.billing._billing_get",
                side_effect=mock_billing_get,
            ):
                response = await get_transactions(request, mock_auth_context, limit=50, offset=0)

        assert len(response.transactions) == 2
        assert response.total_count == 2
        assert response.has_more is False

        # Verify first transaction (charge)
        charge = response.transactions[0]
        assert charge.transaction_id == "charge_abc123"
        assert charge.type == "charge"
        assert charge.amount_minor == -100
        assert charge.balance_after == 900

        # Verify second transaction (credit)
        credit = response.transactions[1]
        assert credit.transaction_id == "credit_xyz789"
        assert credit.type == "credit"
        assert credit.amount_minor == 1000
        assert credit.transaction_type == "purchase"

        # Verify API call parameters
        assert captured_params["limit"] == 50
        assert captured_params["offset"] == 0
        assert "oauth_provider" in captured_params
        assert "external_id" in captured_params

    @pytest.mark.asyncio
    async def test_get_transactions_with_pagination(self, mock_auth_context):
        """Test transaction listing with custom pagination parameters."""
        from unittest.mock import patch

        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None

        # Mock resource monitor with CIRISBillingProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"
        request.app.state.resource_monitor = resource_monitor

        # Capture params for verification
        captured_params = {}

        async def mock_billing_get(base_url, path, headers, params=None):
            captured_params.update(params or {})
            return {
                "transactions": [],
                "total_count": 100,
                "has_more": True,
            }

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            with patch(
                "ciris_engine.logic.adapters.api.routes.billing._billing_get",
                side_effect=mock_billing_get,
            ):
                response = await get_transactions(request, mock_auth_context, limit=10, offset=20)

        # Verify pagination parameters were passed
        assert captured_params["limit"] == 10
        assert captured_params["offset"] == 20

        # Verify response
        assert response.total_count == 100
        assert response.has_more is True

    @pytest.mark.asyncio
    async def test_get_transactions_404_account_not_found(self, mock_auth_context):
        """Test transaction listing when account not found (404) returns empty list."""
        from unittest.mock import patch

        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None

        # Mock resource monitor with CIRISBillingProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"
        request.app.state.resource_monitor = resource_monitor

        # Mock _billing_get to return empty response (simulating 404)
        async def mock_billing_get(base_url, path, headers, params=None):
            return {"transactions": [], "total_count": 0, "has_more": False}

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            with patch(
                "ciris_engine.logic.adapters.api.routes.billing._billing_get",
                side_effect=mock_billing_get,
            ):
                response = await get_transactions(request, mock_auth_context, limit=50, offset=0)

        # Should return empty list instead of raising error
        assert response.transactions == []
        assert response.total_count == 0
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_get_transactions_api_error(self, mock_auth_context):
        """Test transaction listing with billing API error (500)."""
        from unittest.mock import patch

        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None

        # Mock resource monitor with CIRISBillingProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"
        request.app.state.resource_monitor = resource_monitor

        # Mock _billing_get to raise HTTPException (simulating server error)
        async def mock_billing_get_error(*args, **kwargs):
            raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            with patch(
                "ciris_engine.logic.adapters.api.routes.billing._billing_get",
                side_effect=mock_billing_get_error,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await get_transactions(request, mock_auth_context, limit=50, offset=0)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == ERROR_BILLING_SERVICE_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_get_transactions_request_error(self, mock_auth_context):
        """Test transaction listing with network request error."""
        from unittest.mock import patch

        request = Mock()
        request.app.state = Mock()
        request.app.state.auth_service = None

        # Mock resource monitor with CIRISBillingProvider
        resource_monitor = Mock()
        resource_monitor.credit_provider = Mock()
        resource_monitor.credit_provider.__class__.__name__ = "CIRISBillingProvider"
        request.app.state.resource_monitor = resource_monitor

        # Mock _billing_get to raise HTTPException (simulating network error)
        async def mock_billing_get_error(*args, **kwargs):
            raise HTTPException(status_code=503, detail=ERROR_BILLING_SERVICE_UNAVAILABLE)

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("CIRIS_BILLING_API_KEY", "test-api-key")
            with patch(
                "ciris_engine.logic.adapters.api.routes.billing._billing_get",
                side_effect=mock_billing_get_error,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await get_transactions(request, mock_auth_context, limit=50, offset=0)

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == ERROR_BILLING_SERVICE_UNAVAILABLE


class TestSanitizeForLog:
    """Test _sanitize_for_log helper function."""

    def test_returns_empty_placeholder_for_empty_string(self):
        """Should return <empty> for empty string."""
        from ciris_engine.logic.adapters.api.routes.billing import _sanitize_for_log

        result = _sanitize_for_log("")
        assert result == "<empty>"

    def test_returns_empty_placeholder_for_none(self):
        """Should return <empty> for None."""
        from ciris_engine.logic.adapters.api.routes.billing import _sanitize_for_log

        result = _sanitize_for_log(None)
        assert result == "<empty>"

    def test_removes_control_characters(self):
        """Should remove newlines and control characters."""
        from ciris_engine.logic.adapters.api.routes.billing import _sanitize_for_log

        result = _sanitize_for_log("hello\nworld\r\ttab")
        assert result == "helloworldtab"

    def test_removes_c0_control_chars(self):
        """Should remove C0 control characters (0x00-0x1f)."""
        from ciris_engine.logic.adapters.api.routes.billing import _sanitize_for_log

        result = _sanitize_for_log("hello\x00\x01\x1fworld")
        assert result == "helloworld"

    def test_removes_c1_control_chars(self):
        """Should remove DEL and C1 control characters (0x7f-0x9f)."""
        from ciris_engine.logic.adapters.api.routes.billing import _sanitize_for_log

        result = _sanitize_for_log("hello\x7f\x80\x9fworld")
        assert result == "helloworld"

    def test_truncates_long_strings(self):
        """Should truncate strings longer than max_length."""
        from ciris_engine.logic.adapters.api.routes.billing import _sanitize_for_log

        long_string = "a" * 100
        result = _sanitize_for_log(long_string, max_length=64)
        assert len(result) == 67  # 64 + "..."
        assert result.endswith("...")

    def test_preserves_short_strings(self):
        """Should not truncate strings shorter than max_length."""
        from ciris_engine.logic.adapters.api.routes.billing import _sanitize_for_log

        result = _sanitize_for_log("short", max_length=64)
        assert result == "short"
