"""Tests for billing lazy initialization functions."""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import Request

from ciris_engine.logic.adapters.api.routes.billing import (
    _get_credit_provider,
    _try_lazy_init_billing_provider,
)


class TestGetCreditProvider:
    """Tests for _get_credit_provider function."""

    def test_returns_none_when_no_resource_monitor(self):
        """Returns None when request.app.state has no resource_monitor."""
        request = Mock(spec=Request)
        request.app = Mock()
        request.app.state = Mock(spec=[])  # Empty spec - no attributes

        result = _get_credit_provider(request)
        assert result is None

    def test_returns_none_when_no_credit_provider_attr(self):
        """Returns None when resource_monitor has no credit_provider attribute."""
        request = Mock(spec=Request)
        request.app = Mock()
        resource_monitor = Mock(spec=[])  # No credit_provider attribute
        request.app.state = Mock()
        request.app.state.resource_monitor = resource_monitor

        result = _get_credit_provider(request)
        assert result is None

    def test_returns_existing_provider(self):
        """Returns existing credit provider when available."""
        request = Mock(spec=Request)
        request.app = Mock()
        mock_provider = Mock()
        resource_monitor = Mock()
        resource_monitor.credit_provider = mock_provider
        request.app.state = Mock()
        request.app.state.resource_monitor = resource_monitor

        result = _get_credit_provider(request)
        assert result is mock_provider

    def test_tries_lazy_init_when_provider_is_none(self):
        """Attempts lazy initialization when credit_provider is None."""
        request = Mock(spec=Request)
        request.app = Mock()
        resource_monitor = Mock()
        resource_monitor.credit_provider = None
        request.app.state = Mock()
        request.app.state.resource_monitor = resource_monitor

        with patch(
            "ciris_engine.logic.adapters.api.routes.billing._try_lazy_init_billing_provider"
        ) as mock_lazy_init:
            mock_lazy_init.return_value = None
            result = _get_credit_provider(request)

            mock_lazy_init.assert_called_once_with(request, resource_monitor)
            assert result is None


class TestTryLazyInitBillingProvider:
    """Tests for _try_lazy_init_billing_provider function."""

    def test_returns_none_when_no_token(self):
        """Returns None when no CIRIS_BILLING_GOOGLE_ID_TOKEN in environment."""
        request = Mock(spec=Request)
        resource_monitor = Mock()

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CIRIS_BILLING_GOOGLE_ID_TOKEN", None)
            os.environ.pop("CIRIS_HOME", None)

            result = _try_lazy_init_billing_provider(request, resource_monitor)
            assert result is None

    def test_creates_provider_when_token_exists(self):
        """Creates billing provider when Google ID token is available."""
        request = Mock(spec=Request)
        resource_monitor = Mock()
        resource_monitor.credit_provider = None

        mock_provider = Mock()

        with patch.dict(
            os.environ,
            {
                "CIRIS_BILLING_GOOGLE_ID_TOKEN": "test-google-token-12345",
                "CIRIS_BILLING_API_URL": "https://billing.test.com",
            },
            clear=True,
        ):
            with patch(
                "ciris_engine.logic.services.infrastructure.resource_monitor.ciris_billing_provider.CIRISBillingProvider"
            ) as mock_provider_class:
                mock_provider_class.return_value = mock_provider

                result = _try_lazy_init_billing_provider(request, resource_monitor)

                mock_provider_class.assert_called_once()
                call_kwargs = mock_provider_class.call_args[1]
                assert call_kwargs["google_id_token"] == "test-google-token-12345"
                assert call_kwargs["base_url"] == "https://billing.test.com"
                assert call_kwargs["fail_open"] is False
                assert call_kwargs["cache_ttl_seconds"] == 15

                assert result is mock_provider
                assert resource_monitor.credit_provider is mock_provider

    def test_uses_default_billing_url(self):
        """Uses default billing URL when CIRIS_BILLING_API_URL not set."""
        request = Mock(spec=Request)
        resource_monitor = Mock()
        resource_monitor.credit_provider = None

        with patch.dict(
            os.environ,
            {"CIRIS_BILLING_GOOGLE_ID_TOKEN": "test-token"},
            clear=True,
        ):
            with patch(
                "ciris_engine.logic.services.infrastructure.resource_monitor.ciris_billing_provider.CIRISBillingProvider"
            ) as mock_provider_class:
                mock_provider_class.return_value = Mock()

                _try_lazy_init_billing_provider(request, resource_monitor)

                call_kwargs = mock_provider_class.call_args[1]
                assert call_kwargs["base_url"] == "https://billing1.ciris-services-1.ai"

    def test_reloads_env_from_ciris_home(self):
        """Reloads .env file from CIRIS_HOME when available."""
        request = Mock(spec=Request)
        resource_monitor = Mock()
        resource_monitor.credit_provider = None

        with patch.dict(
            os.environ,
            {
                "CIRIS_HOME": "/fake/ciris/home",
                "CIRIS_BILLING_GOOGLE_ID_TOKEN": "test-token",
            },
            clear=True,
        ):
            with patch("os.path.exists", return_value=True):
                with patch("dotenv.load_dotenv") as mock_load_dotenv:
                    with patch(
                        "ciris_engine.logic.services.infrastructure.resource_monitor.ciris_billing_provider.CIRISBillingProvider"
                    ) as mock_provider_class:
                        mock_provider_class.return_value = Mock()

                        _try_lazy_init_billing_provider(request, resource_monitor)

                        mock_load_dotenv.assert_called_once_with(
                            "/fake/ciris/home/.env", override=True
                        )

    def test_skips_env_reload_when_no_ciris_home(self):
        """Skips .env reload when CIRIS_HOME is not set."""
        request = Mock(spec=Request)
        resource_monitor = Mock()
        resource_monitor.credit_provider = None

        with patch.dict(
            os.environ,
            {"CIRIS_BILLING_GOOGLE_ID_TOKEN": "test-token"},
            clear=True,
        ):
            with patch("dotenv.load_dotenv") as mock_load_dotenv:
                with patch(
                    "ciris_engine.logic.services.infrastructure.resource_monitor.ciris_billing_provider.CIRISBillingProvider"
                ) as mock_provider_class:
                    mock_provider_class.return_value = Mock()

                    _try_lazy_init_billing_provider(request, resource_monitor)

                    mock_load_dotenv.assert_not_called()

    def test_logs_provider_creation(self):
        """Logs when billing provider is lazily created."""
        request = Mock(spec=Request)
        resource_monitor = Mock()
        resource_monitor.credit_provider = None

        with patch.dict(
            os.environ,
            {"CIRIS_BILLING_GOOGLE_ID_TOKEN": "x" * 100},  # 100 char token
            clear=True,
        ):
            with patch(
                "ciris_engine.logic.services.infrastructure.resource_monitor.ciris_billing_provider.CIRISBillingProvider"
            ) as mock_provider_class:
                mock_provider_class.return_value = Mock()

                with patch(
                    "ciris_engine.logic.adapters.api.routes.billing.logger"
                ) as mock_logger:
                    _try_lazy_init_billing_provider(request, resource_monitor)

                    # Check that info log was called (with BILLING_LAZY_INIT tag)
                    assert mock_logger.info.called
                    info_calls = [str(call) for call in mock_logger.info.call_args_list]
                    assert any("BILLING_LAZY_INIT" in call for call in info_calls)
