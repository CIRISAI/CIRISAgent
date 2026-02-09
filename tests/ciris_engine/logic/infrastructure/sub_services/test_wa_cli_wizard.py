"""Tests for WA CLI wizard service."""

from datetime import datetime, timezone
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from ciris_engine.logic.infrastructure.sub_services.wa_cli_wizard import WACLIWizardService
from ciris_engine.schemas.infrastructure.wa_cli_wizard import OAuthConfigResult, WizardResult
from ciris_engine.schemas.services.authority_core import WACertificate, WARole


@pytest.fixture
def mock_auth_service() -> MagicMock:
    """Create mock authentication service."""
    service = MagicMock()
    service.list_was = AsyncMock(return_value=[])
    service._store_wa_certificate = AsyncMock()
    return service


@pytest.fixture
def mock_bootstrap_service() -> MagicMock:
    """Create mock bootstrap service."""
    service = MagicMock()
    service.bootstrap_new_root = AsyncMock()
    service.generate_mint_request = MagicMock()
    return service


@pytest.fixture
def mock_oauth_service() -> MagicMock:
    """Create mock OAuth service."""
    service = MagicMock()
    service.oauth_setup = AsyncMock()
    return service


@pytest.fixture
def mock_display_service() -> MagicMock:
    """Create mock display service."""
    return MagicMock()


@pytest.fixture
def wizard_service(
    mock_auth_service: MagicMock,
    mock_bootstrap_service: MagicMock,
    mock_oauth_service: MagicMock,
    mock_display_service: MagicMock,
) -> WACLIWizardService:
    """Create wizard service with mocked dependencies."""
    service = WACLIWizardService(
        auth_service=mock_auth_service,
        bootstrap_service=mock_bootstrap_service,
        oauth_service=mock_oauth_service,
        display_service=mock_display_service,
    )
    # Replace console with one that captures output
    service.console = Console(file=StringIO(), force_terminal=True)
    return service


class TestWACLIWizardServiceInit:
    """Tests for service initialization."""

    def test_init_with_services(
        self,
        mock_auth_service: MagicMock,
        mock_bootstrap_service: MagicMock,
        mock_oauth_service: MagicMock,
        mock_display_service: MagicMock,
    ) -> None:
        """Test initialization with all services."""
        service = WACLIWizardService(
            auth_service=mock_auth_service,
            bootstrap_service=mock_bootstrap_service,
            oauth_service=mock_oauth_service,
            display_service=mock_display_service,
        )
        assert service.auth_service == mock_auth_service
        assert service.bootstrap_service == mock_bootstrap_service
        assert service.oauth_service == mock_oauth_service
        assert service.display_service == mock_display_service


class TestOnboardWizard:
    """Tests for onboard_wizard method."""

    @pytest.mark.asyncio
    async def test_onboard_wizard_no_root_stay_observer(
        self, wizard_service: WACLIWizardService, mock_auth_service: MagicMock
    ) -> None:
        """Test onboard wizard when no root exists and user stays observer."""
        mock_auth_service.list_was.return_value = []

        with patch("ciris_engine.logic.infrastructure.sub_services.wa_cli_wizard.IntPrompt") as mock_prompt:
            mock_prompt.ask.return_value = 3  # Stay as observer

            result = await wizard_service.onboard_wizard()

        assert result.status == "observer"

    @pytest.mark.asyncio
    async def test_onboard_wizard_root_exists_stay_observer(
        self, wizard_service: WACLIWizardService, mock_auth_service: MagicMock
    ) -> None:
        """Test onboard wizard when root exists and user stays observer."""
        root_wa = WACertificate(
            wa_id="wa-2024-01-01-ROOT01",
            name="Root",
            role=WARole.ROOT,
            pubkey="key",
            jwt_kid="kid",
            scopes_json="[]",
            created_at=datetime.now(timezone.utc),
        )
        mock_auth_service.list_was.return_value = [root_wa]

        with patch("ciris_engine.logic.infrastructure.sub_services.wa_cli_wizard.IntPrompt") as mock_prompt:
            mock_prompt.ask.return_value = 2  # Stay as observer

            result = await wizard_service.onboard_wizard()

        assert result.status == "observer"


class TestCreateRootWA:
    """Tests for _create_root_wa method."""

    @pytest.mark.asyncio
    async def test_create_root_wa_success(
        self, wizard_service: WACLIWizardService, mock_bootstrap_service: MagicMock
    ) -> None:
        """Test successful root WA creation."""
        mock_bootstrap_service.bootstrap_new_root.return_value = {
            "status": "success",
            "wa_id": "wa-2024-01-01-NEWRT1",
            "key_file": "/path/to/key",
        }

        with (
            patch("ciris_engine.logic.infrastructure.sub_services.wa_cli_wizard.Prompt") as mock_prompt,
            patch("ciris_engine.logic.infrastructure.sub_services.wa_cli_wizard.Confirm") as mock_confirm,
        ):
            mock_prompt.ask.return_value = "test_root"
            mock_confirm.ask.side_effect = [True, False]  # password yes, shamir no

            result = await wizard_service._create_root_wa()

        assert result.status == "success"
        assert result.wa_id == "wa-2024-01-01-NEWRT1"
        mock_bootstrap_service.bootstrap_new_root.assert_called_once()


class TestImportRootCert:
    """Tests for _import_root_cert method."""

    @pytest.mark.asyncio
    async def test_import_root_cert_invalid_role(
        self, wizard_service: WACLIWizardService, mock_auth_service: MagicMock
    ) -> None:
        """Test import fails for non-root certificate."""
        with (
            patch("ciris_engine.logic.infrastructure.sub_services.wa_cli_wizard.Prompt") as mock_prompt,
            patch("pathlib.Path.read_text") as mock_read,
        ):
            mock_prompt.ask.return_value = "/path/to/cert.json"
            mock_read.return_value = '{"role": "authority", "wa_id": "test"}'

            result = await wizard_service._import_root_cert()

        assert result.status == "error"
        assert result.error is not None
        assert "not a root" in result.error.lower()


class TestJoinWATree:
    """Tests for _join_wa_tree method."""

    def test_join_wa_tree_success(self, wizard_service: WACLIWizardService, mock_bootstrap_service: MagicMock) -> None:
        """Test successful join request generation."""
        mock_bootstrap_service.generate_mint_request.return_value = {
            "status": "success",
            "request_id": "req-123",
            "requested_role": "observer",
            "requester_name": "Test Name",
            "request_code": "ABC123",
        }

        with patch("ciris_engine.logic.infrastructure.sub_services.wa_cli_wizard.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["Test Name", "observer"]

            result = wizard_service._join_wa_tree()

        assert result.status == "success"
        mock_bootstrap_service.generate_mint_request.assert_called_once()


class TestConfigureOAuth:
    """Tests for _configure_oauth method."""

    @pytest.mark.asyncio
    async def test_configure_oauth_success(
        self, wizard_service: WACLIWizardService, mock_oauth_service: MagicMock
    ) -> None:
        """Test successful OAuth configuration."""
        mock_oauth_service.oauth_setup.return_value = OAuthConfigResult(
            status="success",
            provider="google",
        )

        with patch("ciris_engine.logic.infrastructure.sub_services.wa_cli_wizard.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["google", "client-id", "client-secret"]

            result = await wizard_service._configure_oauth()

        assert result.status == "success"
        assert result.provider == "google"
        mock_oauth_service.oauth_setup.assert_called_once()

    @pytest.mark.asyncio
    async def test_configure_oauth_custom_provider(
        self, wizard_service: WACLIWizardService, mock_oauth_service: MagicMock
    ) -> None:
        """Test OAuth configuration with custom provider."""
        mock_oauth_service.oauth_setup.return_value = OAuthConfigResult(
            status="success",
            provider="custom_provider",
        )

        with patch("ciris_engine.logic.infrastructure.sub_services.wa_cli_wizard.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["custom", "custom_provider", "client-id", "client-secret"]

            result = await wizard_service._configure_oauth()

        assert result.status == "success"
        mock_oauth_service.oauth_setup.assert_called_once()
