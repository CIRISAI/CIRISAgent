"""
Unit tests for tool balance and purchase API endpoints.

Tests the /api/tools/* endpoints for:
- Tool balance checking (web_search credits, etc.)
- Tool credit purchases via Google Play
- Available tools listing by platform
"""

import pytest
from fastapi import status
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


class TestToolBalanceEndpoints:
    """Test tool balance checking endpoints."""

    def test_get_tool_balance_without_auth_returns_401(self, client):
        """Test that balance endpoint without auth returns 401."""
        response = client.get("/v1/api/tools/balance/web_search")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_tool_balance_without_google_token_returns_401(self, client, auth_headers):
        """Test that balance endpoint without Google token returns 401."""
        response = client.get("/v1/api/tools/balance/web_search", headers=auth_headers)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Google Sign-In required" in response.json()["detail"]

    @patch("ciris_engine.logic.adapters.api.routes.tools._get_google_id_token")
    @patch("ciris_engine.logic.adapters.api.routes.tools._make_billing_request")
    def test_get_tool_balance_success(self, mock_billing, mock_token, client, auth_headers):
        """Test successful tool balance retrieval."""
        mock_token.return_value = "test_google_token"

        # Mock successful billing response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "product_type": "web_search",
            "free_remaining": 5,
            "paid_credits": 10,
            "total_available": 15,
            "price_minor": 10,
            "total_uses": 25,
        }
        mock_billing.return_value = mock_response

        response = client.get("/v1/api/tools/balance/web_search", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["product_type"] == "web_search"
        assert data["free_remaining"] == 5
        assert data["paid_credits"] == 10
        assert data["total_available"] == 15

    @patch("ciris_engine.logic.adapters.api.routes.tools._get_google_id_token")
    @patch("ciris_engine.logic.adapters.api.routes.tools._make_billing_request")
    def test_get_tool_balance_billing_auth_error(self, mock_billing, mock_token, client, auth_headers):
        """Test tool balance with billing auth error."""
        mock_token.return_value = "test_google_token"

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_billing.return_value = mock_response

        response = client.get("/v1/api/tools/balance/web_search", headers=auth_headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication failed" in response.json()["detail"]

    @patch("ciris_engine.logic.adapters.api.routes.tools._get_google_id_token")
    @patch("ciris_engine.logic.adapters.api.routes.tools._make_billing_request")
    def test_get_tool_balance_not_found(self, mock_billing, mock_token, client, auth_headers):
        """Test tool balance for non-existent tool."""
        mock_token.return_value = "test_google_token"

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_billing.return_value = mock_response

        response = client.get("/v1/api/tools/balance/unknown_tool", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Tool not found" in response.json()["detail"]


class TestAllToolBalancesEndpoint:
    """Test getting all tool balances."""

    def test_get_all_balances_without_auth_returns_401(self, client):
        """Test that all balances endpoint without auth returns 401."""
        response = client.get("/v1/api/tools/balance")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("ciris_engine.logic.adapters.api.routes.tools._get_google_id_token")
    @patch("ciris_engine.logic.adapters.api.routes.tools._make_billing_request")
    def test_get_all_balances_success(self, mock_billing, mock_token, client, auth_headers):
        """Test successful retrieval of all tool balances."""
        mock_token.return_value = "test_google_token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "balances": [
                {
                    "product_type": "web_search",
                    "free_remaining": 3,
                    "paid_credits": 10,
                    "total_available": 13,
                    "price_minor": 10,
                    "total_uses": 7,
                },
            ]
        }
        mock_billing.return_value = mock_response

        response = client.get("/v1/api/tools/balance", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["balances"]) == 1
        assert data["balances"][0]["product_type"] == "web_search"


class TestToolCreditCheckEndpoint:
    """Test quick credit check endpoint."""

    def test_check_credit_without_auth_returns_401(self, client):
        """Test that credit check without auth returns 401."""
        response = client.get("/v1/api/tools/check/web_search")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("ciris_engine.logic.adapters.api.routes.tools._get_google_id_token")
    @patch("ciris_engine.logic.adapters.api.routes.tools._make_billing_request")
    def test_check_credit_has_credit(self, mock_billing, mock_token, client, auth_headers):
        """Test credit check when user has credit."""
        mock_token.return_value = "test_google_token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "has_credit": True,
            "product_type": "web_search",
            "free_remaining": 3,
            "paid_credits": 5,
            "total_available": 8,
        }
        mock_billing.return_value = mock_response

        response = client.get("/v1/api/tools/check/web_search", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["has_credit"] is True
        assert data["total_available"] == 8

    @patch("ciris_engine.logic.adapters.api.routes.tools._get_google_id_token")
    @patch("ciris_engine.logic.adapters.api.routes.tools._make_billing_request")
    def test_check_credit_no_credit(self, mock_billing, mock_token, client, auth_headers):
        """Test credit check when user has no credit."""
        mock_token.return_value = "test_google_token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "has_credit": False,
            "product_type": "web_search",
            "free_remaining": 0,
            "paid_credits": 0,
            "total_available": 0,
        }
        mock_billing.return_value = mock_response

        response = client.get("/v1/api/tools/check/web_search", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["has_credit"] is False
        assert data["total_available"] == 0


class TestAvailableToolsEndpoint:
    """Test available tools listing endpoint."""

    def test_available_tools_without_auth_returns_401(self, client):
        """Test that available tools without auth returns 401."""
        response = client.get("/v1/api/tools/available")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("ciris_engine.logic.utils.platform_detection.detect_platform_capabilities")
    def test_available_tools_returns_tools_list(self, mock_caps, client, auth_headers):
        """Test available tools returns list of tools."""
        # Mock platform capabilities
        mock_caps_instance = MagicMock()
        mock_caps_instance.platform = "linux"
        mock_caps_instance.google_native_auth_available = False
        mock_caps_instance.satisfies.return_value = False
        mock_caps.return_value = mock_caps_instance

        response = client.get("/v1/api/tools/available", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "tools" in data
        assert "platform" in data
        assert "has_google_auth" in data
        assert data["platform"] == "linux"
        assert data["has_google_auth"] is False

    @patch("ciris_engine.logic.utils.platform_detection.detect_platform_capabilities")
    def test_available_tools_android_with_play_services(self, mock_caps, client, auth_headers):
        """Test available tools on Android with Play Services."""
        mock_caps_instance = MagicMock()
        mock_caps_instance.platform = "android"
        mock_caps_instance.google_native_auth_available = True
        mock_caps_instance.satisfies.return_value = True
        mock_caps.return_value = mock_caps_instance

        response = client.get("/v1/api/tools/available", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["platform"] == "android"
        assert data["has_google_auth"] is True
        # web_search should be available on Android with Play Services
        web_search_tool = next((t for t in data["tools"] if t["name"] == "web_search"), None)
        assert web_search_tool is not None
        assert web_search_tool["available"] is True


class TestToolPurchaseEndpoint:
    """Test tool credit purchase verification endpoint."""

    def test_purchase_without_auth_returns_401(self, client):
        """Test that purchase endpoint without auth returns 401."""
        response = client.post(
            "/v1/api/tools/purchase",
            json={
                "product_id": "web_search_10",
                "purchase_token": "test_token",
                "tool_name": "web_search",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_purchase_without_google_token_returns_401(self, client, auth_headers):
        """Test that purchase without Google token returns 401."""
        response = client.post(
            "/v1/api/tools/purchase",
            headers=auth_headers,
            json={
                "product_id": "web_search_10",
                "purchase_token": "test_token",
                "tool_name": "web_search",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Google Sign-In required" in response.json()["detail"]

    @patch("ciris_engine.logic.adapters.api.routes.tools._get_google_id_token")
    @patch("ciris_engine.logic.adapters.api.routes.tools._make_billing_request")
    def test_purchase_success(self, mock_billing, mock_token, client, auth_headers):
        """Test successful purchase verification."""
        mock_token.return_value = "test_google_token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "product_type": "web_search",
            "credits_added": 10,
            "new_balance": 15,
            "message": "Purchase verified and credits added",
        }
        mock_billing.return_value = mock_response

        response = client.post(
            "/v1/api/tools/purchase",
            headers=auth_headers,
            json={
                "product_id": "web_search_10",
                "purchase_token": "test_token",
                "tool_name": "web_search",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["credits_added"] == 10
        assert data["new_balance"] == 15

    @patch("ciris_engine.logic.adapters.api.routes.tools._get_google_id_token")
    @patch("ciris_engine.logic.adapters.api.routes.tools._make_billing_request")
    def test_purchase_invalid_token(self, mock_billing, mock_token, client, auth_headers):
        """Test purchase with invalid purchase token."""
        mock_token.return_value = "test_google_token"

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Invalid purchase token"}
        mock_billing.return_value = mock_response

        response = client.post(
            "/v1/api/tools/purchase",
            headers=auth_headers,
            json={
                "product_id": "web_search_10",
                "purchase_token": "invalid_token",
                "tool_name": "web_search",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid purchase" in response.json()["detail"]

    @patch("ciris_engine.logic.adapters.api.routes.tools._get_google_id_token")
    @patch("ciris_engine.logic.adapters.api.routes.tools._make_billing_request")
    def test_purchase_already_processed(self, mock_billing, mock_token, client, auth_headers):
        """Test purchase that was already processed."""
        mock_token.return_value = "test_google_token"

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.json.return_value = {"detail": "Purchase already processed"}
        mock_billing.return_value = mock_response

        response = client.post(
            "/v1/api/tools/purchase",
            headers=auth_headers,
            json={
                "product_id": "web_search_10",
                "purchase_token": "already_used_token",
                "tool_name": "web_search",
            },
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert "already processed" in response.json()["detail"]


class TestBillingServiceFallback:
    """Test fallback to secondary billing server."""

    @patch("ciris_engine.logic.adapters.api.routes.tools._get_google_id_token")
    @patch("ciris_engine.logic.adapters.api.routes.tools._make_billing_request")
    def test_fallback_on_primary_failure(self, mock_billing, mock_token, client, auth_headers):
        """Test fallback to secondary server on primary failure."""
        mock_token.return_value = "test_google_token"

        # First call raises error (primary), second call succeeds (fallback)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "product_type": "web_search",
            "free_remaining": 3,
            "paid_credits": 0,
            "total_available": 3,
            "price_minor": 10,
            "total_uses": 0,
        }

        # Primary fails, fallback succeeds
        mock_billing.side_effect = [httpx.RequestError("Connection failed"), mock_response]

        response = client.get("/v1/api/tools/balance/web_search", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["product_type"] == "web_search"

        # Verify fallback was called
        assert mock_billing.call_count == 2
        # Second call should have use_fallback=True
        second_call_kwargs = mock_billing.call_args_list[1][1]
        assert second_call_kwargs.get("use_fallback") is True

    @patch("ciris_engine.logic.adapters.api.routes.tools._get_google_id_token")
    @patch("ciris_engine.logic.adapters.api.routes.tools._make_billing_request")
    def test_service_unavailable_when_both_fail(self, mock_billing, mock_token, client, auth_headers):
        """Test 503 when both primary and fallback fail."""
        mock_token.return_value = "test_google_token"

        # Both calls fail
        mock_billing.side_effect = httpx.RequestError("Connection failed")

        response = client.get("/v1/api/tools/balance/web_search", headers=auth_headers)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "Billing service unavailable" in response.json()["detail"]


class TestHelperFunctions:
    """Test helper functions in tools module."""

    def test_get_billing_url_default(self):
        """Test default billing URL."""
        from ciris_engine.logic.adapters.api.routes.tools import _get_billing_url, DEFAULT_BILLING_URL

        with patch.dict("os.environ", {}, clear=True):
            # When no env var, should return default
            url = _get_billing_url()
            assert url == DEFAULT_BILLING_URL

    def test_get_billing_url_from_env(self):
        """Test billing URL from environment."""
        from ciris_engine.logic.adapters.api.routes.tools import _get_billing_url

        with patch.dict("os.environ", {"CIRIS_BILLING_API_URL": "https://custom.billing.url"}):
            url = _get_billing_url()
            assert url == "https://custom.billing.url"

    def test_get_google_id_token_from_header(self):
        """Test getting Google ID token from request header."""
        from ciris_engine.logic.adapters.api.routes.tools import _get_google_id_token

        mock_request = MagicMock()
        mock_request.headers = {"X-Google-ID-Token": "header_token"}

        with patch.dict("os.environ", {}, clear=True):
            token = _get_google_id_token(mock_request)
            assert token == "header_token"

    def test_get_google_id_token_from_env(self):
        """Test getting Google ID token from environment."""
        from ciris_engine.logic.adapters.api.routes.tools import _get_google_id_token

        mock_request = MagicMock()
        mock_request.headers = {}

        with patch.dict("os.environ", {"CIRIS_BILLING_GOOGLE_ID_TOKEN": "env_token"}):
            token = _get_google_id_token(mock_request)
            assert token == "env_token"

    def test_get_google_id_token_fallback_env(self):
        """Test getting Google ID token from fallback environment variable."""
        from ciris_engine.logic.adapters.api.routes.tools import _get_google_id_token

        mock_request = MagicMock()
        mock_request.headers = {}

        with patch.dict("os.environ", {"GOOGLE_ID_TOKEN": "fallback_token"}, clear=True):
            token = _get_google_id_token(mock_request)
            assert token == "fallback_token"

    def test_get_google_id_token_none_when_missing(self):
        """Test that None is returned when no token available."""
        from ciris_engine.logic.adapters.api.routes.tools import _get_google_id_token

        mock_request = MagicMock()
        mock_request.headers = {}

        with patch.dict("os.environ", {}, clear=True):
            token = _get_google_id_token(mock_request)
            assert token is None


class TestToolsRouterRegistration:
    """Test that tools router is properly registered."""

    def test_tools_router_prefix(self):
        """Test tools router has correct prefix."""
        from ciris_engine.logic.adapters.api.routes.tools import router

        assert router.prefix == "/api/tools"

    def test_tools_router_tags(self):
        """Test tools router has correct tags."""
        from ciris_engine.logic.adapters.api.routes.tools import router

        assert "tools" in router.tags


class TestPydanticSchemas:
    """Test Pydantic response schemas."""

    def test_tool_balance_response_schema(self):
        """Test ToolBalanceResponse schema."""
        from ciris_engine.logic.adapters.api.routes.tools import ToolBalanceResponse

        response = ToolBalanceResponse(
            product_type="web_search",
            free_remaining=5,
            paid_credits=10,
            total_available=15,
            price_minor=10,
            total_uses=25,
        )

        assert response.product_type == "web_search"
        assert response.free_remaining == 5
        assert response.paid_credits == 10
        assert response.total_available == 15

    def test_tool_purchase_request_schema(self):
        """Test ToolPurchaseRequest schema."""
        from ciris_engine.logic.adapters.api.routes.tools import ToolPurchaseRequest

        request = ToolPurchaseRequest(
            product_id="web_search_10",
            purchase_token="test_token",
            tool_name="web_search",
        )

        assert request.product_id == "web_search_10"
        assert request.purchase_token == "test_token"
        assert request.tool_name == "web_search"

    def test_tool_purchase_response_schema(self):
        """Test ToolPurchaseResponse schema."""
        from ciris_engine.logic.adapters.api.routes.tools import ToolPurchaseResponse

        response = ToolPurchaseResponse(
            success=True,
            product_type="web_search",
            credits_added=10,
            new_balance=15,
            message="Purchase verified",
        )

        assert response.success is True
        assert response.credits_added == 10
        assert response.new_balance == 15

    def test_tool_info_response_schema(self):
        """Test ToolInfoResponse schema."""
        from ciris_engine.logic.adapters.api.routes.tools import ToolInfoResponse

        response = ToolInfoResponse(
            name="web_search",
            description="Search the web",
            cost=1.0,
            available=True,
            platform_requirements=["android_play_integrity"],
        )

        assert response.name == "web_search"
        assert response.available is True
        assert "android_play_integrity" in response.platform_requirements
