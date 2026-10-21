"""Tests for WA CLI display service."""

from datetime import datetime, timezone
from io import StringIO
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from rich.console import Console

from ciris_engine.logic.infrastructure.sub_services.wa_cli_display import WACLIDisplayService
from ciris_engine.schemas.services.authority_core import WACertificate, WARole


@pytest.fixture
def mock_auth_service() -> MagicMock:
    """Create mock authentication service."""
    service = MagicMock()
    service.list_was = AsyncMock()
    service.get_wa = AsyncMock()
    return service


@pytest.fixture
def sample_wa_certificates() -> list[WACertificate]:
    """Create sample WA certificates for testing."""
    root = WACertificate(
        wa_id="wa-2024-01-01-ROOT01",
        name="Root Authority",
        role=WARole.ROOT,
        pubkey="root-pubkey-123",
        jwt_kid="root-kid-123",
        scopes_json='["*"]',
        parent_wa_id=None,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    child = WACertificate(
        wa_id="wa-2024-01-02-CHLD01",
        name="Child Authority",
        role=WARole.AUTHORITY,
        pubkey="child-pubkey-123",
        jwt_kid="child-kid-123",
        scopes_json='["read", "write"]',
        parent_wa_id="wa-2024-01-01-ROOT01",
        oauth_provider="google",
        created_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    return [root, child]


@pytest.fixture
def display_service(mock_auth_service: MagicMock) -> WACLIDisplayService:
    """Create display service with mocked dependencies."""
    service = WACLIDisplayService(mock_auth_service)
    # Replace console with one that captures output
    service.console = Console(file=StringIO(), force_terminal=True)
    return service


def get_console_output(service: WACLIDisplayService) -> str:
    """Get console output from service (type-safe helper)."""
    return cast(StringIO, service.console.file).getvalue()


class TestWACLIDisplayServiceInit:
    """Tests for service initialization."""

    def test_init_with_auth_service(self, mock_auth_service: MagicMock) -> None:
        """Test initialization with auth service."""
        service = WACLIDisplayService(mock_auth_service)
        assert service.auth_service == mock_auth_service
        assert service.console is not None


class TestListWAs:
    """Tests for list_was method."""

    @pytest.mark.asyncio
    async def test_list_was_empty(self, display_service: WACLIDisplayService, mock_auth_service: MagicMock) -> None:
        """Test listing when no WAs exist."""
        mock_auth_service.list_was.return_value = []

        await display_service.list_was()

        # Check console output contains "No WAs found"
        output = get_console_output(display_service)
        assert "No WAs found" in output

    @pytest.mark.asyncio
    async def test_list_was_table_view(
        self,
        display_service: WACLIDisplayService,
        mock_auth_service: MagicMock,
        sample_wa_certificates: list[WACertificate],
    ) -> None:
        """Test listing WAs in table view."""
        mock_auth_service.list_was.return_value = sample_wa_certificates

        await display_service.list_was(tree_view=False)

        output = get_console_output(display_service)
        assert "Wise Authorities" in output
        # Rich table may truncate names, check for wa_id which is always shown
        assert "wa-2024-01-01-ROOT01" in output
        assert "wa-2024-01-02-CHLD01" in output

    @pytest.mark.asyncio
    async def test_list_was_tree_view(
        self,
        display_service: WACLIDisplayService,
        mock_auth_service: MagicMock,
        sample_wa_certificates: list[WACertificate],
    ) -> None:
        """Test listing WAs in tree view."""
        mock_auth_service.list_was.return_value = sample_wa_certificates

        await display_service.list_was(tree_view=True)

        output = get_console_output(display_service)
        assert "Root Authority" in output
        # Tree view shows hierarchy
        assert "wa-2024-01-01-ROOT01" in output

    @pytest.mark.asyncio
    async def test_list_was_handles_error(
        self, display_service: WACLIDisplayService, mock_auth_service: MagicMock
    ) -> None:
        """Test listing WAs handles errors gracefully."""
        mock_auth_service.list_was.side_effect = Exception("Database error")

        await display_service.list_was()

        output = get_console_output(display_service)
        assert "Error" in output


class TestDisplayTable:
    """Tests for _display_table method."""

    @pytest.mark.asyncio
    async def test_display_table_shows_all_columns(
        self, display_service: WACLIDisplayService, sample_wa_certificates: list[WACertificate]
    ) -> None:
        """Test table display shows all expected columns."""
        await display_service._display_table(sample_wa_certificates)

        output = get_console_output(display_service)
        # Table should contain WA info - wa_id is always shown, name may be truncated
        assert "wa-2024-01-01-ROOT01" in output
        # Check for partial name or role since Rich may truncate
        assert "Root" in output or "root" in output


class TestDisplayTree:
    """Tests for _display_tree method."""

    @pytest.mark.asyncio
    async def test_display_tree_no_roots(self, display_service: WACLIDisplayService) -> None:
        """Test tree display with no root WAs."""
        was = [
            WACertificate(
                wa_id="wa-2024-01-01-ORPHN1",
                name="Child Only",
                role=WARole.AUTHORITY,
                pubkey="key",
                jwt_kid="kid",
                scopes_json="[]",
                parent_wa_id="wa-2024-01-01-MISSIN",  # Parent doesn't exist
                created_at=datetime.now(timezone.utc),
            )
        ]

        await display_service._display_tree(was)

        output = get_console_output(display_service)
        assert "No root WAs found" in output

    @pytest.mark.asyncio
    async def test_display_tree_with_hierarchy(
        self, display_service: WACLIDisplayService, sample_wa_certificates: list[WACertificate]
    ) -> None:
        """Test tree display shows hierarchy."""
        await display_service._display_tree(sample_wa_certificates)

        output = get_console_output(display_service)
        assert "Root Authority" in output
        # Child should also appear
        assert "Child Authority" in output


class TestShowWADetails:
    """Tests for show_wa_details method."""

    @pytest.mark.asyncio
    async def test_show_wa_details_not_found(
        self, display_service: WACLIDisplayService, mock_auth_service: MagicMock
    ) -> None:
        """Test showing details for non-existent WA."""
        mock_auth_service.get_wa.return_value = None

        await display_service.show_wa_details("nonexistent-wa")

        output = get_console_output(display_service)
        assert "not found" in output.lower()

    @pytest.mark.asyncio
    async def test_show_wa_details_success(
        self,
        display_service: WACLIDisplayService,
        mock_auth_service: MagicMock,
        sample_wa_certificates: list[WACertificate],
    ) -> None:
        """Test showing details for existing WA."""
        wa = sample_wa_certificates[0]
        mock_auth_service.get_wa.return_value = wa
        mock_auth_service.list_was.return_value = sample_wa_certificates

        await display_service.show_wa_details(wa.wa_id)

        output = get_console_output(display_service)
        assert "Root Authority" in output
        assert wa.wa_id in output

    @pytest.mark.asyncio
    async def test_show_wa_details_with_children(
        self,
        display_service: WACLIDisplayService,
        mock_auth_service: MagicMock,
        sample_wa_certificates: list[WACertificate],
    ) -> None:
        """Test showing details includes children."""
        root = sample_wa_certificates[0]
        mock_auth_service.get_wa.return_value = root
        mock_auth_service.list_was.return_value = sample_wa_certificates

        await display_service.show_wa_details(root.wa_id)

        output = get_console_output(display_service)
        # Should show children section
        assert "Children" in output or "Child Authority" in output

    @pytest.mark.asyncio
    async def test_show_wa_details_handles_error(
        self, display_service: WACLIDisplayService, mock_auth_service: MagicMock
    ) -> None:
        """Test showing details handles errors gracefully."""
        mock_auth_service.get_wa.side_effect = Exception("Database error")

        await display_service.show_wa_details("wa-id")

        output = get_console_output(display_service)
        assert "Error" in output
