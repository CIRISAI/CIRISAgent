"""Tests for ingress authentication provider system.

Tests cover:
1. Provider registration and priority ordering
2. Chain of Responsibility pattern (sequential with short-circuit)
3. Multiple providers with fallback
4. HA Supervisor provider with IP verification
5. User creation on first authentication
6. Setup wizard skip detection
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from ciris_engine.logic.adapters.api.dependencies.auth import (
    _try_ingress_auth,
    clear_ingress_auth_providers,
    get_active_ingress_provider_names,
    get_ingress_auth_providers,
    has_ingress_auth_providers,
    register_ingress_auth_provider,
    should_skip_setup_wizard_user_step,
    unregister_ingress_auth_provider,
)
from ciris_engine.protocols.services.infrastructure.ingress_auth import (
    IngressAuthProviderProtocol,
    IngressUser,
)
from ciris_engine.schemas.api.auth import UserRole


# =============================================================================
# Test Fixtures - Mock Providers
# =============================================================================


class MockIngressProvider:
    """Mock ingress auth provider for testing."""

    def __init__(
        self,
        name: str,
        can_handle: bool = True,
        auth_result: Optional[IngressUser] = None,
        skip_setup: bool = False,
        first_user_admin: bool = True,
    ):
        self._name = name
        self._can_handle = can_handle
        self._auth_result = auth_result
        self._skip_setup = skip_setup
        self._first_user_admin = first_user_admin
        self.can_handle_called = False
        self.authenticate_called = False

    @property
    def provider_name(self) -> str:
        return self._name

    def can_handle_request(self, request: Request) -> bool:
        self.can_handle_called = True
        return self._can_handle

    async def authenticate_request(self, request: Request) -> Optional[IngressUser]:
        self.authenticate_called = True
        return self._auth_result

    def is_first_user_admin(self) -> bool:
        return self._first_user_admin

    def skip_setup_wizard_user_step(self) -> bool:
        return self._skip_setup

    def get_provider_metadata(self) -> Dict[str, Any]:
        return {"name": self._name, "test": True}


class ErrorProvider(MockIngressProvider):
    """Provider that raises an exception during authentication."""

    async def authenticate_request(self, request: Request) -> Optional[IngressUser]:
        self.authenticate_called = True
        raise ValueError("Simulated provider error")


@pytest.fixture(autouse=True)
def clean_providers():
    """Clear all providers before and after each test."""
    clear_ingress_auth_providers()
    yield
    clear_ingress_auth_providers()


@pytest.fixture
def mock_request() -> MagicMock:
    """Create a mock FastAPI Request."""
    request = MagicMock(spec=Request)
    request.headers = {}
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    return request


@pytest.fixture
def mock_auth_service() -> MagicMock:
    """Create a mock APIAuthService."""
    service = MagicMock()
    service.get_user = MagicMock(return_value=None)
    service.create_user = AsyncMock(return_value=MagicMock(wa_id="test-user-id"))
    return service


# =============================================================================
# Test: Provider Registration
# =============================================================================


class TestProviderRegistration:
    """Tests for provider registration and management."""

    def test_register_single_provider(self):
        """Test registering a single provider."""
        provider = MockIngressProvider("test_provider")

        register_ingress_auth_provider(provider)

        assert has_ingress_auth_providers()
        assert len(get_ingress_auth_providers()) == 1
        assert get_ingress_auth_providers()[0] is provider

    def test_register_multiple_providers_default_priority(self):
        """Test registering multiple providers with default priority."""
        provider1 = MockIngressProvider("provider1")
        provider2 = MockIngressProvider("provider2")

        register_ingress_auth_provider(provider1)
        register_ingress_auth_provider(provider2)

        providers = get_ingress_auth_providers()
        assert len(providers) == 2
        # Both have same priority, so order depends on registration
        assert provider1 in providers
        assert provider2 in providers

    def test_register_providers_with_priority(self):
        """Test that providers are ordered by priority (highest first)."""
        low_priority = MockIngressProvider("low")
        medium_priority = MockIngressProvider("medium")
        high_priority = MockIngressProvider("high")

        # Register in random order
        register_ingress_auth_provider(medium_priority, priority=100)
        register_ingress_auth_provider(low_priority, priority=50)
        register_ingress_auth_provider(high_priority, priority=200)

        providers = get_ingress_auth_providers()
        assert len(providers) == 3
        # Should be ordered: high, medium, low
        assert providers[0] is high_priority
        assert providers[1] is medium_priority
        assert providers[2] is low_priority

    def test_duplicate_registration_ignored(self):
        """Test that registering the same provider twice is ignored."""
        provider = MockIngressProvider("test")

        register_ingress_auth_provider(provider)
        register_ingress_auth_provider(provider)  # Should be ignored

        assert len(get_ingress_auth_providers()) == 1

    def test_unregister_provider(self):
        """Test unregistering a provider."""
        provider = MockIngressProvider("test")
        register_ingress_auth_provider(provider)

        unregister_ingress_auth_provider(provider)

        assert not has_ingress_auth_providers()

    def test_unregister_nonexistent_provider(self):
        """Test unregistering a provider that wasn't registered."""
        provider = MockIngressProvider("test")

        # Should not raise
        unregister_ingress_auth_provider(provider)

        assert not has_ingress_auth_providers()

    def test_clear_all_providers(self):
        """Test clearing all providers."""
        register_ingress_auth_provider(MockIngressProvider("p1"))
        register_ingress_auth_provider(MockIngressProvider("p2"))
        register_ingress_auth_provider(MockIngressProvider("p3"))

        clear_ingress_auth_providers()

        assert not has_ingress_auth_providers()

    def test_get_active_provider_names(self):
        """Test getting list of active provider names."""
        register_ingress_auth_provider(MockIngressProvider("alpha"), priority=100)
        register_ingress_auth_provider(MockIngressProvider("beta"), priority=200)

        names = get_active_ingress_provider_names()

        assert names == ["beta", "alpha"]  # Ordered by priority


# =============================================================================
# Test: Chain of Responsibility Pattern
# =============================================================================


class TestChainOfResponsibility:
    """Tests for the Chain of Responsibility authentication pattern."""

    @pytest.mark.asyncio
    async def test_first_handler_processes_request(self, mock_request, mock_auth_service):
        """Test that first matching provider handles the request (short-circuit)."""
        ingress_user = IngressUser(
            external_id="user123",
            provider="provider1",
            username="testuser",
        )
        provider1 = MockIngressProvider("provider1", can_handle=True, auth_result=ingress_user)
        provider2 = MockIngressProvider("provider2", can_handle=True)

        register_ingress_auth_provider(provider1, priority=200)
        register_ingress_auth_provider(provider2, priority=100)

        context = await _try_ingress_auth(mock_request, mock_auth_service)

        # Provider1 should have handled it (higher priority)
        assert provider1.can_handle_called
        assert provider1.authenticate_called
        # Provider2 should NOT have been checked (short-circuit)
        assert not provider2.can_handle_called
        assert not provider2.authenticate_called
        # Context should be created
        assert context is not None
        assert context.user_id == "provider1:user123"

    @pytest.mark.asyncio
    async def test_fallback_to_next_provider(self, mock_request, mock_auth_service):
        """Test fallback when first provider can't handle request."""
        ingress_user = IngressUser(
            external_id="user456",
            provider="provider2",
            username="fallbackuser",
        )
        provider1 = MockIngressProvider("provider1", can_handle=False)
        provider2 = MockIngressProvider("provider2", can_handle=True, auth_result=ingress_user)

        register_ingress_auth_provider(provider1, priority=200)
        register_ingress_auth_provider(provider2, priority=100)

        context = await _try_ingress_auth(mock_request, mock_auth_service)

        # Provider1 checked but couldn't handle
        assert provider1.can_handle_called
        assert not provider1.authenticate_called
        # Provider2 should have handled it
        assert provider2.can_handle_called
        assert provider2.authenticate_called
        assert context is not None
        assert context.user_id == "provider2:user456"

    @pytest.mark.asyncio
    async def test_no_provider_handles_request(self, mock_request, mock_auth_service):
        """Test when no provider can handle the request."""
        provider1 = MockIngressProvider("provider1", can_handle=False)
        provider2 = MockIngressProvider("provider2", can_handle=False)

        register_ingress_auth_provider(provider1)
        register_ingress_auth_provider(provider2)

        context = await _try_ingress_auth(mock_request, mock_auth_service)

        assert context is None
        # Both providers should have been checked
        assert provider1.can_handle_called
        assert provider2.can_handle_called

    @pytest.mark.asyncio
    async def test_provider_returns_none_continues_chain(self, mock_request, mock_auth_service):
        """Test that if a provider returns None, we continue to next provider."""
        ingress_user = IngressUser(
            external_id="user789",
            provider="provider2",
        )
        # Provider1 says it can handle but returns None (auth failed)
        provider1 = MockIngressProvider("provider1", can_handle=True, auth_result=None)
        provider2 = MockIngressProvider("provider2", can_handle=True, auth_result=ingress_user)

        register_ingress_auth_provider(provider1, priority=200)
        register_ingress_auth_provider(provider2, priority=100)

        context = await _try_ingress_auth(mock_request, mock_auth_service)

        # Provider1 tried but failed
        assert provider1.authenticate_called
        # Provider2 should have been tried next
        assert provider2.authenticate_called
        assert context is not None
        assert context.user_id == "provider2:user789"

    @pytest.mark.asyncio
    async def test_provider_error_continues_chain(self, mock_request, mock_auth_service):
        """Test that provider errors don't break the chain."""
        ingress_user = IngressUser(
            external_id="user_after_error",
            provider="good_provider",
        )
        error_provider = ErrorProvider("error_provider", can_handle=True)
        good_provider = MockIngressProvider("good_provider", can_handle=True, auth_result=ingress_user)

        register_ingress_auth_provider(error_provider, priority=200)
        register_ingress_auth_provider(good_provider, priority=100)

        context = await _try_ingress_auth(mock_request, mock_auth_service)

        # Error provider was tried (and failed)
        assert error_provider.authenticate_called
        # Good provider should have been tried next
        assert good_provider.authenticate_called
        assert context is not None

    @pytest.mark.asyncio
    async def test_no_providers_registered(self, mock_request, mock_auth_service):
        """Test when no providers are registered."""
        context = await _try_ingress_auth(mock_request, mock_auth_service)

        assert context is None


# =============================================================================
# Test: Setup Wizard Integration
# =============================================================================


class TestSetupWizardIntegration:
    """Tests for setup wizard skip detection."""

    def test_skip_setup_wizard_when_provider_requests_it(self):
        """Test that setup wizard is skipped when provider requests it."""
        provider = MockIngressProvider("test", skip_setup=True)
        register_ingress_auth_provider(provider)

        assert should_skip_setup_wizard_user_step()

    def test_no_skip_when_provider_doesnt_request_it(self):
        """Test that setup wizard runs when provider doesn't skip."""
        provider = MockIngressProvider("test", skip_setup=False)
        register_ingress_auth_provider(provider)

        assert not should_skip_setup_wizard_user_step()

    def test_skip_if_any_provider_requests_it(self):
        """Test that setup is skipped if ANY provider requests it."""
        provider1 = MockIngressProvider("p1", skip_setup=False)
        provider2 = MockIngressProvider("p2", skip_setup=True)
        provider3 = MockIngressProvider("p3", skip_setup=False)

        register_ingress_auth_provider(provider1)
        register_ingress_auth_provider(provider2)
        register_ingress_auth_provider(provider3)

        assert should_skip_setup_wizard_user_step()

    def test_no_skip_when_no_providers(self):
        """Test that setup runs when no providers registered."""
        assert not should_skip_setup_wizard_user_step()


# =============================================================================
# Test: User Creation from Ingress Auth
# =============================================================================


class TestUserCreation:
    """Tests for user creation during ingress authentication."""

    @pytest.mark.asyncio
    async def test_new_user_created_with_suggested_role(self, mock_request, mock_auth_service):
        """Test that new users are created with the suggested role."""
        ingress_user = IngressUser(
            external_id="newuser123",
            provider="test",
            username="New User",
            suggested_role=UserRole.ADMIN,
        )
        provider = MockIngressProvider("test", auth_result=ingress_user)
        register_ingress_auth_provider(provider)

        context = await _try_ingress_auth(mock_request, mock_auth_service)

        # User should be created
        mock_auth_service.create_user.assert_called_once()
        call_args = mock_auth_service.create_user.call_args
        assert call_args.kwargs["username"] == "New User"
        # Role should be ADMIN
        assert context.role == UserRole.ADMIN

    @pytest.mark.asyncio
    async def test_existing_user_preserves_role(self, mock_request, mock_auth_service):
        """Test that existing users keep their existing role."""
        # Setup existing user
        from ciris_engine.schemas.runtime.api import APIRole

        existing_user = MagicMock()
        existing_user.api_role = APIRole.SYSTEM_ADMIN
        mock_auth_service.get_user = MagicMock(return_value=existing_user)

        ingress_user = IngressUser(
            external_id="existinguser",
            provider="test",
            suggested_role=UserRole.OBSERVER,  # Suggested is lower
        )
        provider = MockIngressProvider("test", auth_result=ingress_user)
        register_ingress_auth_provider(provider)

        context = await _try_ingress_auth(mock_request, mock_auth_service)

        # Should not create new user
        mock_auth_service.create_user.assert_not_called()
        # Should preserve existing role
        assert context.role == UserRole.SYSTEM_ADMIN


# =============================================================================
# Test: HA Ingress Provider Specifically
# =============================================================================


class TestHAIngressProvider:
    """Tests for the Home Assistant ingress auth provider."""

    @pytest.fixture
    def ha_request(self) -> MagicMock:
        """Create a mock request with HA ingress headers."""
        request = MagicMock(spec=Request)
        request.headers = {
            "X-Remote-User-Id": "ha-user-abc123",
            "X-Remote-User-Name": "homeowner",
            "X-Remote-User-Display-Name": "Home Owner",
            "X-Ingress-Path": "/api/hassio_ingress/abc123",
        }
        request.client = MagicMock()
        request.client.host = "172.30.32.2"  # HA Supervisor IP
        return request

    def test_ha_provider_detects_supervisor_mode(self):
        """Test HA provider only activates with SUPERVISOR_TOKEN."""
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            from ciris_adapters.home_assistant.ingress_auth import HAIngressAuthProvider

            provider = HAIngressAuthProvider()
            assert provider._supervisor_mode

    def test_ha_provider_inactive_without_supervisor_token(self):
        """Test HA provider is inactive without SUPERVISOR_TOKEN."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove SUPERVISOR_TOKEN if present
            os.environ.pop("SUPERVISOR_TOKEN", None)

            from ciris_adapters.home_assistant.ingress_auth import HAIngressAuthProvider

            provider = HAIngressAuthProvider()
            assert not provider._supervisor_mode

    def test_ha_provider_rejects_untrusted_ip(self, ha_request):
        """Test HA provider rejects requests from untrusted IPs."""
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            from ciris_adapters.home_assistant.ingress_auth import HAIngressAuthProvider

            provider = HAIngressAuthProvider()
            # Change to untrusted IP
            ha_request.client.host = "192.168.1.100"

            can_handle = provider.can_handle_request(ha_request)

            assert not can_handle

    def test_ha_provider_accepts_supervisor_ip(self, ha_request):
        """Test HA provider accepts requests from Supervisor IP."""
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            from ciris_adapters.home_assistant.ingress_auth import HAIngressAuthProvider

            provider = HAIngressAuthProvider()
            # Supervisor IP is already set in fixture
            assert ha_request.client.host == "172.30.32.2"

            can_handle = provider.can_handle_request(ha_request)

            assert can_handle

    def test_ha_provider_accepts_localhost(self, ha_request):
        """Test HA provider accepts localhost for testing."""
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            from ciris_adapters.home_assistant.ingress_auth import HAIngressAuthProvider

            provider = HAIngressAuthProvider()
            ha_request.client.host = "127.0.0.1"

            can_handle = provider.can_handle_request(ha_request)

            assert can_handle

    @pytest.mark.asyncio
    async def test_ha_provider_extracts_user_info(self, ha_request):
        """Test HA provider extracts correct user info from headers."""
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            from ciris_adapters.home_assistant.ingress_auth import HAIngressAuthProvider

            provider = HAIngressAuthProvider()

            ingress_user = await provider.authenticate_request(ha_request)

            assert ingress_user is not None
            assert ingress_user.external_id == "ha-user-abc123"
            assert ingress_user.provider == "home_assistant"
            assert ingress_user.username == "homeowner"
            assert ingress_user.display_name == "Home Owner"

    @pytest.mark.asyncio
    async def test_ha_provider_first_user_is_admin(self, ha_request):
        """Test first HA user gets SYSTEM_ADMIN role."""
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            from ciris_adapters.home_assistant.ingress_auth import HAIngressAuthProvider

            provider = HAIngressAuthProvider()

            ingress_user = await provider.authenticate_request(ha_request)

            assert ingress_user.suggested_role == UserRole.SYSTEM_ADMIN

    @pytest.mark.asyncio
    async def test_ha_provider_subsequent_users_default_role(self, ha_request):
        """Test subsequent HA users get default role (no suggested role)."""
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            from ciris_adapters.home_assistant.ingress_auth import HAIngressAuthProvider

            provider = HAIngressAuthProvider()

            # First user
            await provider.authenticate_request(ha_request)

            # Second user
            ha_request.headers["X-Remote-User-Id"] = "ha-user-second"
            ingress_user2 = await provider.authenticate_request(ha_request)

            # Second user should not have suggested admin role
            assert ingress_user2.suggested_role is None

    def test_ha_provider_skips_setup_wizard(self):
        """Test HA provider wants to skip setup wizard user step."""
        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}):
            from ciris_adapters.home_assistant.ingress_auth import HAIngressAuthProvider

            provider = HAIngressAuthProvider()

            assert provider.skip_setup_wizard_user_step()
