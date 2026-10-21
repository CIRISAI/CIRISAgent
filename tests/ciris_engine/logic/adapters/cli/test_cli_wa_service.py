"""Tests for CLI Wise Authority service."""

from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.adapters.cli.cli_wa_service import CLIWiseAuthorityService
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral
from ciris_engine.schemas.services.authority_core import (
    DeferralApprovalContext,
    DeferralRequest,
    DeferralResponse,
    GuidanceRequest,
    GuidanceResponse,
    WAPermission,
)
from ciris_engine.schemas.services.context import GuidanceContext


class ConcreteCLIWiseAuthorityService(CLIWiseAuthorityService):
    """Concrete subclass that implements all abstract methods for testing."""

    async def check_authorization(self, wa_id: str, action: str, resource: Optional[str] = None) -> bool:
        """Stub implementation for testing."""
        return True

    async def request_approval(self, action: str, context: DeferralApprovalContext) -> bool:
        """Stub implementation for testing."""
        return True

    async def get_guidance(self, request: GuidanceRequest) -> GuidanceResponse:
        """Stub implementation for testing."""
        return GuidanceResponse(
            reasoning="test guidance",
            wa_id="wa-2024-01-01-TEST01",
            signature="test-signature",
        )

    async def get_pending_deferrals(self, wa_id: Optional[str] = None) -> List[PendingDeferral]:
        """Stub implementation for testing."""
        return []

    async def resolve_deferral(self, deferral_id: str, response: DeferralResponse) -> bool:
        """Stub implementation for testing."""
        return True

    async def grant_permission(self, wa_id: str, permission: str, resource: Optional[str] = None) -> bool:
        """Stub implementation for testing."""
        return True

    async def revoke_permission(self, wa_id: str, permission: str, resource: Optional[str] = None) -> bool:
        """Stub implementation for testing."""
        return True

    async def list_permissions(self, wa_id: str) -> List[WAPermission]:
        """Stub implementation for testing."""
        return []


@pytest.fixture
def mock_time_service() -> MagicMock:
    """Create mock time service."""
    service = MagicMock()
    service.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return service


@pytest.fixture
def cli_wa_service(mock_time_service: MagicMock) -> ConcreteCLIWiseAuthorityService:
    """Create CLI WA service instance."""
    return ConcreteCLIWiseAuthorityService(time_service=mock_time_service)


class TestCLIWiseAuthorityServiceInit:
    """Tests for service initialization."""

    def test_init_with_time_service(self, mock_time_service: MagicMock) -> None:
        """Test initialization with provided time service."""
        service = ConcreteCLIWiseAuthorityService(time_service=mock_time_service)
        assert service.time_service == mock_time_service
        assert service.deferral_log == []

    def test_init_without_time_service(self) -> None:
        """Test initialization creates default time service."""
        service = ConcreteCLIWiseAuthorityService()
        assert service.time_service is not None
        assert service.deferral_log == []


class TestCLIWiseAuthorityServiceLifecycle:
    """Tests for service lifecycle methods."""

    @pytest.mark.asyncio
    async def test_start(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test start method completes without error."""
        await cli_wa_service.start()  # Should not raise

    @pytest.mark.asyncio
    async def test_stop(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test stop method completes without error."""
        await cli_wa_service.stop()  # Should not raise


class TestFetchGuidance:
    """Tests for fetch_guidance method."""

    @pytest.mark.asyncio
    async def test_fetch_guidance_returns_input(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test fetch_guidance returns user input."""
        context = GuidanceContext(
            thought_id="thought-123",
            task_id="task-123",
            question="Should I proceed?",
            ethical_considerations=["privacy", "consent"],
        )

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_input:
            mock_input.return_value = "Yes, proceed carefully"
            result = await cli_wa_service.fetch_guidance(context)

        assert result == "Yes, proceed carefully"

    @pytest.mark.asyncio
    async def test_fetch_guidance_skip_returns_none(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test fetch_guidance returns None when user types 'skip'."""
        context = GuidanceContext(thought_id="thought-123", task_id="task-123", question="Should I proceed?")

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_input:
            mock_input.return_value = "skip"
            result = await cli_wa_service.fetch_guidance(context)

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_guidance_skip_case_insensitive(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test fetch_guidance handles 'SKIP' case insensitively."""
        context = GuidanceContext(thought_id="thought-123", task_id="task-123", question="Should I proceed?")

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_input:
            mock_input.return_value = "SKIP"
            result = await cli_wa_service.fetch_guidance(context)

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_guidance_handles_exception(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test fetch_guidance returns None on exception."""
        context = GuidanceContext(thought_id="thought-123", task_id="task-123", question="Should I proceed?")

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_input:
            mock_input.side_effect = EOFError("Input error")
            result = await cli_wa_service.fetch_guidance(context)

        assert result is None


class TestSendDeferral:
    """Tests for send_deferral method."""

    @pytest.mark.asyncio
    async def test_send_deferral_returns_id(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test send_deferral returns a deferral ID."""
        deferral = DeferralRequest(
            thought_id="thought-123",
            task_id="task-456",
            reason="Need more information",
            defer_until=datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
        )

        with patch("ciris_engine.logic.adapters.cli.cli_wa_service.persistence") as mock_persistence:
            result = await cli_wa_service.send_deferral(deferral)

        assert result is not None
        assert len(result) == 36  # UUID format
        mock_persistence.add_correlation.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_deferral_logs_entry(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test send_deferral adds entry to deferral log."""
        deferral = DeferralRequest(
            thought_id="thought-123",
            task_id="task-456",
            reason="Need more information",
            defer_until=datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
            context={"task_description": "Test task"},
        )

        with patch("ciris_engine.logic.adapters.cli.cli_wa_service.persistence"):
            await cli_wa_service.send_deferral(deferral)

        assert len(cli_wa_service.deferral_log) == 1
        entry = cli_wa_service.deferral_log[0]
        assert entry["thought_id"] == "thought-123"
        assert entry["task_id"] == "task-456"
        assert entry["reason"] == "Need more information"

    @pytest.mark.asyncio
    async def test_send_deferral_with_defer_until(
        self, cli_wa_service: ConcreteCLIWiseAuthorityService, mock_time_service: MagicMock
    ) -> None:
        """Test send_deferral handles defer_until field."""
        defer_until = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        deferral = DeferralRequest(
            thought_id="thought-123",
            task_id="task-456",
            reason="Scheduled deferral",
            defer_until=defer_until,
        )

        with patch("ciris_engine.logic.adapters.cli.cli_wa_service.persistence"):
            await cli_wa_service.send_deferral(deferral)

        entry = cli_wa_service.deferral_log[0]
        assert entry["defer_until"] == defer_until.isoformat()


class TestServiceMetadata:
    """Tests for service metadata methods."""

    @pytest.mark.asyncio
    async def test_is_healthy(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test is_healthy returns True."""
        result = await cli_wa_service.is_healthy()
        assert result is True

    def test_get_service_type(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test get_service_type returns ADAPTER."""
        result = cli_wa_service.get_service_type()
        assert result == ServiceType.ADAPTER

    def test_get_capabilities(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test get_capabilities returns correct capabilities."""
        caps = cli_wa_service.get_capabilities()
        assert caps.service_name == "CLIWiseAuthorityService"
        assert "fetch_guidance" in caps.actions
        assert "defer_decision" in caps.actions
        assert caps.version == "1.0.0"

    def test_get_status(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test get_status returns correct status."""
        status = cli_wa_service.get_status()
        assert status.service_name == "CLIWiseAuthorityService"
        assert status.service_type == "adapter"
        assert status.is_healthy is True
        assert status.metrics["deferrals_logged"] == 0

    @pytest.mark.asyncio
    async def test_get_status_reflects_deferrals(self, cli_wa_service: ConcreteCLIWiseAuthorityService) -> None:
        """Test get_status reflects deferral count."""
        deferral = DeferralRequest(
            thought_id="thought-123",
            task_id="task-456",
            reason="Test",
            defer_until=datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
        )

        with patch("ciris_engine.logic.adapters.cli.cli_wa_service.persistence"):
            await cli_wa_service.send_deferral(deferral)
            await cli_wa_service.send_deferral(deferral)

        status = cli_wa_service.get_status()
        assert status.metrics["deferrals_logged"] == 2
