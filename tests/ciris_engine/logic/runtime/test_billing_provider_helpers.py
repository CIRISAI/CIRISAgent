"""
Tests for billing provider helper methods in ciris_runtime.py.

Covers the refactored methods:
- _is_using_ciris_proxy
- _get_resource_monitor_for_billing
- _create_billing_provider
- _create_billing_token_handler
- _create_llm_token_handler
- _update_llm_services_token
- _update_service_token_if_ciris_proxy
- _reinitialize_billing_provider
"""

import os
from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock, patch

import pytest

from ciris_engine.logic.runtime.ciris_runtime import CIRIS_PROXY_DOMAIN, CIRIS_PROXY_DOMAINS, CIRISRuntime


class TestCIRISProxyDomainConstant:
    """Tests for CIRIS_PROXY_DOMAIN constant."""

    def test_constant_value(self):
        """CIRIS_PROXY_DOMAIN has expected value (backwards compat)."""
        assert CIRIS_PROXY_DOMAIN == "ciris.ai"

    def test_domains_tuple_value(self):
        """CIRIS_PROXY_DOMAINS includes legacy and new infrastructure."""
        assert "ciris.ai" in CIRIS_PROXY_DOMAINS
        assert "ciris-services" in CIRIS_PROXY_DOMAINS


class TestIsUsingCirisProxy:
    """Tests for _is_using_ciris_proxy method."""

    @pytest.fixture
    def runtime(self):
        """Create a minimal runtime for testing."""
        with patch.object(CIRISRuntime, "__init__", lambda self, *args, **kwargs: None):
            rt = CIRISRuntime.__new__(CIRISRuntime)
            return rt

    def test_returns_true_when_ciris_proxy_in_url(self, runtime):
        """Returns True when OPENAI_API_BASE contains ciris.ai."""
        with patch.dict(os.environ, {"OPENAI_API_BASE": "https://llm.ciris.ai/v1"}):
            result = runtime._is_using_ciris_proxy()
            assert result is True

    def test_returns_true_for_billing_url(self, runtime):
        """Returns True when URL contains ciris.ai domain."""
        with patch.dict(os.environ, {"OPENAI_API_BASE": "https://api.ciris.ai/llm"}):
            result = runtime._is_using_ciris_proxy()
            assert result is True

    def test_returns_true_for_ciris_services_url(self, runtime):
        """Returns True when URL contains ciris-services domain."""
        with patch.dict(os.environ, {"OPENAI_API_BASE": "https://proxy1.ciris-services-1.ai/v1"}):
            result = runtime._is_using_ciris_proxy()
            assert result is True

    def test_returns_false_for_openai_url(self, runtime):
        """Returns False for standard OpenAI URL."""
        with patch.dict(os.environ, {"OPENAI_API_BASE": "https://api.openai.com/v1"}):
            result = runtime._is_using_ciris_proxy()
            assert result is False

    def test_returns_false_when_not_set(self, runtime):
        """Returns False when OPENAI_API_BASE not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure OPENAI_API_BASE is not set
            os.environ.pop("OPENAI_API_BASE", None)
            result = runtime._is_using_ciris_proxy()
            assert result is False


class TestGetResourceMonitorForBilling:
    """Tests for _get_resource_monitor_for_billing method."""

    @pytest.fixture
    def runtime(self):
        """Create a minimal runtime for testing."""
        with patch.object(CIRISRuntime, "__init__", lambda self, *args, **kwargs: None):
            rt = CIRISRuntime.__new__(CIRISRuntime)
            rt.service_initializer = None
            return rt

    def test_returns_none_when_no_service_initializer(self, runtime):
        """Returns None when service_initializer not available."""
        runtime.service_initializer = None

        result = runtime._get_resource_monitor_for_billing()

        assert result is None

    def test_returns_none_when_no_resource_monitor(self, runtime):
        """Returns None when resource_monitor_service not available."""
        runtime.service_initializer = Mock()
        runtime.service_initializer.resource_monitor_service = None

        result = runtime._get_resource_monitor_for_billing()

        assert result is None

    def test_returns_resource_monitor_when_available(self, runtime):
        """Returns resource monitor when available."""
        mock_monitor = Mock()
        runtime.service_initializer = Mock()
        runtime.service_initializer.resource_monitor_service = mock_monitor

        result = runtime._get_resource_monitor_for_billing()

        assert result is mock_monitor


class TestCreateBillingProvider:
    """Tests for _create_billing_provider method."""

    @pytest.fixture
    def runtime(self):
        """Create a minimal runtime for testing."""
        with patch.object(CIRISRuntime, "__init__", lambda self, *args, **kwargs: None):
            rt = CIRISRuntime.__new__(CIRISRuntime)
            return rt

    def test_creates_provider_with_defaults(self, runtime):
        """Creates billing provider with default configuration."""
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "ciris_engine.logic.services.infrastructure.resource_monitor.CIRISBillingProvider"
            ) as mock_provider_class:
                mock_provider = Mock()
                mock_provider_class.return_value = mock_provider

                result = runtime._create_billing_provider("test-token")

                mock_provider_class.assert_called_once()
                call_kwargs = mock_provider_class.call_args[1]
                assert call_kwargs["google_id_token"] == "test-token"
                assert call_kwargs["base_url"] == "https://billing1.ciris-services-1.ai"
                assert call_kwargs["timeout_seconds"] == 5.0
                assert call_kwargs["cache_ttl_seconds"] == 15
                assert call_kwargs["fail_open"] is False

    def test_creates_provider_with_custom_config(self, runtime):
        """Creates billing provider with custom environment configuration."""
        env_vars = {
            "CIRIS_BILLING_API_URL": "https://custom.billing.api",
            "CIRIS_BILLING_TIMEOUT_SECONDS": "10.0",
            "CIRIS_BILLING_CACHE_TTL_SECONDS": "30",
            "CIRIS_BILLING_FAIL_OPEN": "true",
        }
        with patch.dict(os.environ, env_vars):
            with patch(
                "ciris_engine.logic.services.infrastructure.resource_monitor.CIRISBillingProvider"
            ) as mock_provider_class:
                mock_provider = Mock()
                mock_provider_class.return_value = mock_provider

                result = runtime._create_billing_provider("custom-token")

                call_kwargs = mock_provider_class.call_args[1]
                assert call_kwargs["google_id_token"] == "custom-token"
                assert call_kwargs["base_url"] == "https://custom.billing.api"
                assert call_kwargs["timeout_seconds"] == 10.0
                assert call_kwargs["cache_ttl_seconds"] == 30
                assert call_kwargs["fail_open"] is True


class TestCreateBillingTokenHandler:
    """Tests for _create_billing_token_handler method."""

    @pytest.fixture
    def runtime(self):
        """Create a minimal runtime for testing."""
        with patch.object(CIRISRuntime, "__init__", lambda self, *args, **kwargs: None):
            rt = CIRISRuntime.__new__(CIRISRuntime)
            return rt

    @pytest.mark.asyncio
    async def test_handler_updates_token_when_available(self, runtime):
        """Handler updates billing provider with new token."""
        credit_provider = Mock()
        credit_provider.update_google_id_token = Mock()

        handler = runtime._create_billing_token_handler(credit_provider)

        with patch.dict(os.environ, {"CIRIS_BILLING_GOOGLE_ID_TOKEN": "new-token"}):
            await handler("token_refreshed", "billing")

        credit_provider.update_google_id_token.assert_called_once_with("new-token")

    @pytest.mark.asyncio
    async def test_handler_skips_when_no_token(self, runtime):
        """Handler does nothing when no token in environment."""
        credit_provider = Mock()
        credit_provider.update_google_id_token = Mock()

        handler = runtime._create_billing_token_handler(credit_provider)

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CIRIS_BILLING_GOOGLE_ID_TOKEN", None)
            await handler("token_refreshed", "billing")

        credit_provider.update_google_id_token.assert_not_called()


class TestCreateLLMTokenHandler:
    """Tests for _create_llm_token_handler method."""

    @pytest.fixture
    def runtime(self):
        """Create a mock runtime for testing."""
        runtime = Mock(spec=CIRISRuntime)
        runtime._update_llm_services_token = Mock()
        # Bind the actual method to the mock
        runtime._create_llm_token_handler = lambda: CIRISRuntime._create_llm_token_handler(runtime)
        return runtime

    @pytest.mark.asyncio
    async def test_handler_calls_update_llm_services(self, runtime):
        """Handler calls update_llm_services_token with new token."""
        handler = runtime._create_llm_token_handler()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "new-api-key"}):
            with patch("ciris_engine.logic.runtime.billing_helpers.update_llm_services_token") as mock_update:
                await handler("token_refreshed", "llm")
                mock_update.assert_called_once_with(runtime, "new-api-key")

    @pytest.mark.asyncio
    async def test_handler_skips_when_no_token(self, runtime):
        """Handler does nothing when no OPENAI_API_KEY."""
        handler = runtime._create_llm_token_handler()

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENAI_API_KEY", None)
            await handler("token_refreshed", "llm")

        runtime._update_llm_services_token.assert_not_called()


class TestUpdateLLMServicesToken:
    """Tests for _update_llm_services_token method."""

    @pytest.fixture
    def runtime(self):
        """Create a mock runtime for testing."""
        runtime = Mock(spec=CIRISRuntime)
        runtime.service_registry = None
        runtime.llm_service = None
        # Bind actual methods
        runtime._update_llm_services_token = lambda token: CIRISRuntime._update_llm_services_token(runtime, token)
        runtime._update_service_token_if_ciris_proxy = (
            lambda svc, token, is_primary=False: CIRISRuntime._update_service_token_if_ciris_proxy(
                runtime, svc, token, is_primary
            )
        )
        return runtime

    def test_updates_registry_services(self, runtime):
        """Updates all LLM services from registry."""
        service1 = Mock()
        service1.openai_config = Mock()
        service1.openai_config.base_url = "https://llm.ciris.ai/v1"
        service1.update_api_key = Mock()

        service2 = Mock()
        service2.openai_config = Mock()
        service2.openai_config.base_url = "https://api.openai.com/v1"
        service2.update_api_key = Mock()

        runtime.service_registry = Mock()
        runtime.service_registry.get_services_by_type = Mock(return_value=[service1, service2])

        runtime._update_llm_services_token("new-token")

        # Only service1 (ciris.ai) should be updated
        service1.update_api_key.assert_called_once_with("new-token")
        service2.update_api_key.assert_not_called()

    def test_updates_primary_llm_service(self, runtime):
        """Updates primary llm_service if it uses CIRIS proxy."""
        runtime.service_registry = None

        runtime.llm_service = Mock()
        runtime.llm_service.openai_config = Mock()
        runtime.llm_service.openai_config.base_url = "https://llm.ciris.ai/v1"
        runtime.llm_service.update_api_key = Mock()

        runtime._update_llm_services_token("new-token")

        runtime.llm_service.update_api_key.assert_called_once_with("new-token")

    def test_skips_when_no_services(self, runtime):
        """Does nothing when no services available."""
        runtime.service_registry = None
        runtime.llm_service = None

        # Should not raise
        runtime._update_llm_services_token("new-token")


class TestUpdateServiceTokenIfCirisProxy:
    """Tests for _update_service_token_if_ciris_proxy method."""

    @pytest.fixture
    def runtime(self):
        """Create a minimal runtime for testing."""
        with patch.object(CIRISRuntime, "__init__", lambda self, *args, **kwargs: None):
            rt = CIRISRuntime.__new__(CIRISRuntime)
            return rt

    def test_updates_service_with_ciris_proxy(self, runtime):
        """Updates service that uses CIRIS proxy."""
        service = Mock()
        service.openai_config = Mock()
        service.openai_config.base_url = "https://llm.ciris.ai/v1"
        service.update_api_key = Mock()

        runtime._update_service_token_if_ciris_proxy(service, "new-token")

        service.update_api_key.assert_called_once_with("new-token")

    def test_skips_service_without_ciris_proxy(self, runtime):
        """Skips service that doesn't use CIRIS proxy."""
        service = Mock()
        service.openai_config = Mock()
        service.openai_config.base_url = "https://api.openai.com/v1"
        service.update_api_key = Mock()

        runtime._update_service_token_if_ciris_proxy(service, "new-token")

        service.update_api_key.assert_not_called()

    def test_skips_service_without_openai_config(self, runtime):
        """Skips service without openai_config attribute."""
        service = Mock(spec=[])  # No openai_config

        # Should not raise
        runtime._update_service_token_if_ciris_proxy(service, "new-token")

    def test_skips_service_without_update_method(self, runtime):
        """Skips service without update_api_key method."""
        service = Mock()
        service.openai_config = Mock()
        service.openai_config.base_url = "https://llm.ciris.ai/v1"
        # No update_api_key method
        del service.update_api_key

        # Should not raise
        runtime._update_service_token_if_ciris_proxy(service, "new-token")

    def test_handles_none_base_url(self, runtime):
        """Handles None base_url gracefully."""
        service = Mock()
        service.openai_config = Mock()
        service.openai_config.base_url = None
        service.update_api_key = Mock()

        # Should not raise
        runtime._update_service_token_if_ciris_proxy(service, "new-token")
        service.update_api_key.assert_not_called()


class TestReinitializeBillingProvider:
    """Tests for _reinitialize_billing_provider method."""

    @pytest.fixture
    def runtime(self):
        """Create a mock runtime for testing."""
        runtime = Mock(spec=CIRISRuntime)
        runtime.service_initializer = None
        runtime.service_registry = None
        runtime.llm_service = None
        # Bind actual _reinitialize_billing_provider
        runtime._reinitialize_billing_provider = lambda: CIRISRuntime._reinitialize_billing_provider(runtime)
        return runtime

    @pytest.mark.asyncio
    async def test_returns_early_when_no_resource_monitor(self, runtime):
        """Returns early when resource monitor not available."""
        with patch(
            "ciris_engine.logic.runtime.billing_helpers.get_resource_monitor_for_billing", return_value=None
        ) as mock_get:
            await runtime._reinitialize_billing_provider()

            # Should return without error
            mock_get.assert_called_once_with(runtime)

    @pytest.mark.asyncio
    async def test_returns_early_when_not_android(self, runtime):
        """Returns early when not running on Android."""
        mock_monitor = Mock()
        mock_monitor.credit_provider = None
        runtime._get_resource_monitor_for_billing = Mock(return_value=mock_monitor)
        runtime._is_using_ciris_proxy = Mock(return_value=True)

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANDROID_DATA", None)
            await runtime._reinitialize_billing_provider()

        # Should not configure billing
        assert mock_monitor.credit_provider is None

    @pytest.mark.asyncio
    async def test_returns_early_when_not_using_proxy(self, runtime):
        """Returns early when not using CIRIS proxy."""
        mock_monitor = Mock()
        mock_monitor.credit_provider = None
        runtime._get_resource_monitor_for_billing = Mock(return_value=mock_monitor)
        runtime._is_using_ciris_proxy = Mock(return_value=False)

        with patch.dict(os.environ, {"ANDROID_DATA": "/data"}):
            await runtime._reinitialize_billing_provider()

        # Should not configure billing
        assert mock_monitor.credit_provider is None

    @pytest.mark.asyncio
    async def test_returns_early_when_no_google_token(self, runtime):
        """Returns early when no Google ID token available."""
        mock_monitor = Mock()
        mock_monitor.signal_bus = Mock()
        mock_monitor.signal_bus.register = Mock()
        runtime._get_resource_monitor_for_billing = Mock(return_value=mock_monitor)
        runtime._is_using_ciris_proxy = Mock(return_value=True)

        env_vars = {"ANDROID_DATA": "/data", "OPENAI_API_BASE": "https://llm.ciris.ai"}
        with patch.dict(os.environ, env_vars, clear=True):
            os.environ.pop("CIRIS_BILLING_GOOGLE_ID_TOKEN", None)
            await runtime._reinitialize_billing_provider()

        # Signal bus should not have been used
        mock_monitor.signal_bus.register.assert_not_called()

    @pytest.mark.asyncio
    async def test_configures_billing_when_all_conditions_met(self, runtime):
        """Configures billing provider when all conditions are met."""
        mock_monitor = Mock()
        mock_monitor.signal_bus = Mock()
        mock_monitor.signal_bus.register = Mock()

        mock_provider = Mock()

        env_vars = {
            "ANDROID_DATA": "/data",
            "OPENAI_API_BASE": "https://llm.ciris.ai",
            "CIRIS_BILLING_GOOGLE_ID_TOKEN": "test-token",
        }
        with patch.dict(os.environ, env_vars):
            with patch(
                "ciris_engine.logic.runtime.billing_helpers.get_resource_monitor_for_billing", return_value=mock_monitor
            ):
                with patch("ciris_engine.logic.runtime.billing_helpers.is_using_ciris_proxy", return_value=True):
                    with patch(
                        "ciris_engine.logic.runtime.billing_helpers.create_billing_provider", return_value=mock_provider
                    ):
                        with patch(
                            "ciris_engine.logic.runtime.billing_helpers.create_billing_token_handler",
                            return_value=AsyncMock(),
                        ):
                            with patch(
                                "ciris_engine.logic.runtime.billing_helpers.create_llm_token_handler",
                                return_value=AsyncMock(),
                            ):
                                await runtime._reinitialize_billing_provider()

        # Should have configured billing
        assert mock_monitor.credit_provider is mock_provider
        assert mock_monitor.signal_bus.register.call_count == 2
