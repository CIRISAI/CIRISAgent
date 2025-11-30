"""
Unit tests for universal ticket system API routes.

Tests all ticket endpoints with comprehensive coverage:
- SOP listing and metadata
- Ticket CRUD operations
- Error handling
- Edge cases (metadata merging, filters, etc.)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, Request

from ciris_engine.logic.adapters.api.routes.tickets import (
    _get_agent_tickets_config,
    _get_sop_config,
    _initialize_ticket_metadata,
    _is_sop_supported,
    cancel_ticket,
    create_new_ticket,
    get_sop_metadata,
    get_ticket_by_id,
    list_all_tickets,
    list_supported_sops,
    update_existing_ticket,
)
from ciris_engine.schemas.config.tickets import TicketsConfig, TicketSOPConfig, TicketStageConfig

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request with app state."""
    request = Mock(spec=Request)
    request.app.state.db_path = None
    request.app.state.config_service = None
    return request


@pytest.fixture
def mock_config_service(sample_tickets_config):
    """Create a mock config service that returns tickets config."""
    config_service = AsyncMock()
    mock_config_node = Mock()
    mock_config_node.value = Mock()
    mock_config_node.value.dict_value = sample_tickets_config.model_dump()
    config_service.get_config = AsyncMock(return_value=mock_config_node)
    return config_service


@pytest.fixture
def mock_current_user():
    """Create a mock current user (TokenData)."""
    user = Mock()
    user.username = "test_user"
    user.email = "test@example.com"
    user.role = "ADMIN"
    user.exp = datetime.now(timezone.utc)
    return user


@pytest.fixture
def sample_sop_config():
    """Create a sample SOP configuration."""
    return TicketSOPConfig(
        sop="DSAR_ACCESS",
        ticket_type="dsar",
        required_fields=["email", "user_identifier"],
        deadline_days=30,
        priority_default=8,
        description="GDPR Article 15 - Data Subject Access Request",
        stages=[
            TicketStageConfig(
                name="identity_resolution",
                tools=["identity_resolution_tool"],
                description="Resolve user identity",
            ),
            TicketStageConfig(
                name="data_collection",
                tools=["sql_find_user_data"],
                optional=True,
                description="Collect user data",
            ),
        ],
    )


@pytest.fixture
def sample_tickets_config(sample_sop_config):
    """Create a sample tickets configuration."""
    return TicketsConfig(sops=[sample_sop_config])


@pytest.fixture
def sample_ticket_data():
    """Create sample ticket data returned from database."""
    return {
        "ticket_id": "DSAR-20250108-ABC123",
        "sop": "DSAR_ACCESS",
        "ticket_type": "dsar",
        "status": "pending",
        "priority": 8,
        "email": "user@example.com",
        "user_identifier": "user123",
        "submitted_at": "2025-01-08T12:00:00Z",
        "deadline": "2025-02-07T12:00:00Z",
        "last_updated": "2025-01-08T12:00:00Z",
        "completed_at": None,
        "metadata": {
            "stages": {
                "identity_resolution": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "result": None,
                    "error": None,
                }
            },
            "current_stage": "identity_resolution",
            "sop_version": "1.0",
        },
        "notes": "Test ticket",
        "automated": False,
        "correlation_id": None,
        "agent_occurrence_id": "__shared__",
    }


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestHelperFunctions:
    """Test helper functions for tickets routes."""

    @pytest.mark.asyncio
    async def test_get_agent_tickets_config_no_config_service(self, mock_request):
        """Test getting tickets config when no config service exists."""
        result = await _get_agent_tickets_config(mock_request)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_agent_tickets_config_with_config_service(
        self, mock_request, mock_config_service, sample_tickets_config
    ):
        """Test getting tickets config from config service."""
        mock_request.app.state.config_service = mock_config_service

        result = await _get_agent_tickets_config(mock_request)
        assert result is not None
        assert result.enabled == sample_tickets_config.enabled
        assert len(result.sops) == len(sample_tickets_config.sops)

    @pytest.mark.asyncio
    async def test_get_sop_config_found(self, mock_request, mock_config_service, sample_sop_config):
        """Test getting SOP config when it exists."""
        mock_request.app.state.config_service = mock_config_service

        result = await _get_sop_config(mock_request, "DSAR_ACCESS")
        assert result is not None
        assert result.sop == sample_sop_config.sop

    @pytest.mark.asyncio
    async def test_get_sop_config_not_found(self, mock_request, mock_config_service):
        """Test getting SOP config when it doesn't exist."""
        mock_request.app.state.config_service = mock_config_service

        result = await _get_sop_config(mock_request, "NONEXISTENT_SOP")
        assert result is None

    @pytest.mark.asyncio
    async def test_is_sop_supported_true(self, mock_request, mock_config_service):
        """Test SOP support check when SOP is supported."""
        mock_request.app.state.config_service = mock_config_service

        result = await _is_sop_supported(mock_request, "DSAR_ACCESS")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_sop_supported_false(self, mock_request, mock_config_service):
        """Test SOP support check when SOP is not supported."""
        mock_request.app.state.config_service = mock_config_service

        result = await _is_sop_supported(mock_request, "UNSUPPORTED_SOP")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_sop_supported_no_config(self, mock_request):
        """Test SOP support check when no tickets config exists."""
        result = await _is_sop_supported(mock_request, "ANY_SOP")
        assert result is False

    def test_initialize_ticket_metadata(self, sample_sop_config):
        """Test initializing ticket metadata structure."""
        result = _initialize_ticket_metadata(sample_sop_config)

        assert "stages" in result
        assert "current_stage" in result
        assert "sop_version" in result
        assert result["current_stage"] == "identity_resolution"
        assert result["sop_version"] == "1.0"

        # Check stage structure
        assert "identity_resolution" in result["stages"]
        assert result["stages"]["identity_resolution"]["status"] == "pending"
        assert result["stages"]["identity_resolution"]["started_at"] is None
        assert result["stages"]["identity_resolution"]["completed_at"] is None
        assert result["stages"]["identity_resolution"]["result"] is None
        assert result["stages"]["identity_resolution"]["error"] is None

    def test_initialize_ticket_metadata_empty_stages(self):
        """Test initializing metadata with no stages."""
        sop_config = TicketSOPConfig(
            sop="TEST_SOP",
            ticket_type="test",
            required_fields=[],
            deadline_days=None,
            priority_default=5,
            description="Test SOP",
            stages=[],
        )

        result = _initialize_ticket_metadata(sop_config)

        assert result["stages"] == {}
        assert result["current_stage"] is None
        assert result["sop_version"] == "1.0"


# ============================================================================
# API Endpoint Tests
# ============================================================================


class TestListSupportedSOPs:
    """Test GET /tickets/sops endpoint."""

    @pytest.mark.asyncio
    async def test_list_sops_success(self, mock_request, mock_config_service, mock_current_user):
        """Test listing supported SOPs."""
        mock_request.app.state.config_service = mock_config_service

        result = await list_supported_sops(mock_request, mock_current_user)

        assert isinstance(result, list)
        assert "DSAR_ACCESS" in result

    @pytest.mark.asyncio
    async def test_list_sops_no_config_raises_500(self, mock_request, mock_current_user):
        """Test listing SOPs when tickets config is missing."""
        with pytest.raises(HTTPException) as exc_info:
            await list_supported_sops(mock_request, mock_current_user)

        assert exc_info.value.status_code == 500
        assert "Tickets configuration not available" in exc_info.value.detail


class TestGetSOPMetadata:
    """Test GET /tickets/sops/{sop} endpoint."""

    @pytest.mark.asyncio
    async def test_get_sop_metadata_success(self, mock_request, mock_config_service, mock_current_user):
        """Test getting SOP metadata."""
        mock_request.app.state.config_service = mock_config_service

        result = await get_sop_metadata("DSAR_ACCESS", mock_request, mock_current_user)

        assert result.sop == "DSAR_ACCESS"
        assert result.ticket_type == "dsar"
        assert result.deadline_days == 30
        assert result.priority_default == 8
        assert len(result.stages) == 2
        assert result.stages[0]["name"] == "identity_resolution"

    @pytest.mark.asyncio
    async def test_get_sop_metadata_not_found(self, mock_request, mock_config_service, mock_current_user):
        """Test getting metadata for unsupported SOP."""
        mock_request.app.state.config_service = mock_config_service

        with pytest.raises(HTTPException) as exc_info:
            await get_sop_metadata("UNSUPPORTED_SOP", mock_request, mock_current_user)

        assert exc_info.value.status_code == 404
        assert "not supported" in exc_info.value.detail


class TestCreateTicket:
    """Test POST /tickets/ endpoint."""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.create_ticket")
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    async def test_create_ticket_success(
        self,
        mock_get_ticket,
        mock_create_ticket,
        mock_request,
        mock_config_service,
        sample_ticket_data,
        mock_current_user,
    ):
        """Test creating a new ticket."""
        from ciris_engine.logic.adapters.api.routes.tickets import CreateTicketRequest

        mock_request.app.state.config_service = mock_config_service

        mock_create_ticket.return_value = True
        mock_get_ticket.return_value = sample_ticket_data

        request_data = CreateTicketRequest(
            sop="DSAR_ACCESS",
            email="user@example.com",
            user_identifier="user123",
            notes="Test ticket",
        )

        result = await create_new_ticket(request_data, mock_request, mock_current_user)

        assert result.ticket_id == "DSAR-20250108-ABC123"
        assert result.sop == "DSAR_ACCESS"
        assert result.email == "user@example.com"
        assert mock_create_ticket.called
        assert mock_get_ticket.called

    @pytest.mark.asyncio
    async def test_create_ticket_unsupported_sop(self, mock_request, mock_config_service, mock_current_user):
        """Test creating ticket with unsupported SOP."""
        from ciris_engine.logic.adapters.api.routes.tickets import CreateTicketRequest

        mock_request.app.state.config_service = mock_config_service

        request_data = CreateTicketRequest(
            sop="UNSUPPORTED_SOP",
            email="user@example.com",
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_new_ticket(request_data, mock_request, mock_current_user)

        assert exc_info.value.status_code == 501
        assert "not supported" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.create_ticket")
    async def test_create_ticket_creation_failed(
        self, mock_create_ticket, mock_request, mock_config_service, mock_current_user
    ):
        """Test ticket creation failure."""
        from ciris_engine.logic.adapters.api.routes.tickets import CreateTicketRequest

        mock_request.app.state.config_service = mock_config_service

        mock_create_ticket.return_value = False

        request_data = CreateTicketRequest(
            sop="DSAR_ACCESS",
            email="user@example.com",
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_new_ticket(request_data, mock_request, mock_current_user)

        assert exc_info.value.status_code == 500
        assert "Failed to create ticket" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.create_ticket")
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    async def test_create_ticket_with_custom_priority(
        self,
        mock_get_ticket,
        mock_create_ticket,
        mock_request,
        mock_config_service,
        sample_ticket_data,
        mock_current_user,
    ):
        """Test creating ticket with custom priority."""
        from ciris_engine.logic.adapters.api.routes.tickets import CreateTicketRequest

        mock_request.app.state.config_service = mock_config_service

        mock_create_ticket.return_value = True
        ticket_data = sample_ticket_data.copy()
        ticket_data["priority"] = 10
        mock_get_ticket.return_value = ticket_data

        request_data = CreateTicketRequest(
            sop="DSAR_ACCESS",
            email="user@example.com",
            priority=10,
        )

        result = await create_new_ticket(request_data, mock_request, mock_current_user)

        assert result.priority == 10

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.create_ticket")
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    async def test_create_ticket_with_custom_metadata(
        self,
        mock_get_ticket,
        mock_create_ticket,
        mock_request,
        mock_config_service,
        sample_ticket_data,
        mock_current_user,
    ):
        """Test creating ticket with custom metadata."""
        from ciris_engine.logic.adapters.api.routes.tickets import CreateTicketRequest

        mock_request.app.state.config_service = mock_config_service

        mock_create_ticket.return_value = True
        ticket_data = sample_ticket_data.copy()
        ticket_data["metadata"]["custom_field"] = "custom_value"
        mock_get_ticket.return_value = ticket_data

        request_data = CreateTicketRequest(
            sop="DSAR_ACCESS",
            email="user@example.com",
            metadata={"custom_field": "custom_value"},
        )

        result = await create_new_ticket(request_data, mock_request, mock_current_user)

        assert "custom_field" in result.metadata
        assert result.metadata["custom_field"] == "custom_value"


class TestGetTicketByID:
    """Test GET /tickets/{ticket_id} endpoint."""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    async def test_get_ticket_success(self, mock_get_ticket, mock_request, sample_ticket_data, mock_current_user):
        """Test getting ticket by ID."""
        mock_get_ticket.return_value = sample_ticket_data

        result = await get_ticket_by_id("DSAR-20250108-ABC123", mock_request, mock_current_user)

        assert result.ticket_id == "DSAR-20250108-ABC123"
        assert result.email == "user@example.com"
        mock_get_ticket.assert_called_once_with("DSAR-20250108-ABC123", db_path=None)

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    async def test_get_ticket_not_found(self, mock_get_ticket, mock_request, mock_current_user):
        """Test getting non-existent ticket."""
        mock_get_ticket.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_ticket_by_id("NONEXISTENT-123", mock_request, mock_current_user)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail


class TestListTickets:
    """Test GET /tickets/ endpoint."""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.list_tickets")
    async def test_list_tickets_no_filters(
        self, mock_list_tickets, mock_request, sample_ticket_data, mock_current_user
    ):
        """Test listing all tickets without filters."""
        mock_list_tickets.return_value = [sample_ticket_data]

        result = await list_all_tickets(mock_request, current_user=mock_current_user)

        assert len(result) == 1
        assert result[0].ticket_id == "DSAR-20250108-ABC123"
        mock_list_tickets.assert_called_once_with(
            sop=None,
            ticket_type=None,
            status=None,
            email=None,
            limit=None,
            db_path=None,
        )

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.list_tickets")
    async def test_list_tickets_with_filters(
        self, mock_list_tickets, mock_request, sample_ticket_data, mock_current_user
    ):
        """Test listing tickets with all filters."""
        mock_list_tickets.return_value = [sample_ticket_data]

        result = await list_all_tickets(
            mock_request,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status_filter="pending",
            email="user@example.com",
            limit=10,
            current_user=mock_current_user,
        )

        assert len(result) == 1
        mock_list_tickets.assert_called_once_with(
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="pending",
            email="user@example.com",
            limit=10,
            db_path=None,
        )

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.list_tickets")
    async def test_list_tickets_empty_results(self, mock_list_tickets, mock_request, mock_current_user):
        """Test listing tickets with no results."""
        mock_list_tickets.return_value = []

        result = await list_all_tickets(mock_request, current_user=mock_current_user)

        assert result == []


class TestUpdateTicket:
    """Test PATCH /tickets/{ticket_id} endpoint."""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    @patch("ciris_engine.logic.adapters.api.routes.tickets.update_ticket_status")
    async def test_update_ticket_status_only(
        self, mock_update_status, mock_get_ticket, mock_request, sample_ticket_data, mock_current_user
    ):
        """Test updating only ticket status."""
        from ciris_engine.logic.adapters.api.routes.tickets import UpdateTicketRequest

        mock_get_ticket.side_effect = [
            sample_ticket_data,  # First call for verification
            {**sample_ticket_data, "status": "in_progress"},  # Second call after update
        ]
        mock_update_status.return_value = True

        request_data = UpdateTicketRequest(status="in_progress")

        result = await update_existing_ticket("DSAR-20250108-ABC123", request_data, mock_request, mock_current_user)

        assert result.status == "in_progress"
        mock_update_status.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    @patch("ciris_engine.logic.adapters.api.routes.tickets.update_ticket_metadata")
    async def test_update_ticket_metadata_only(
        self, mock_update_metadata, mock_get_ticket, mock_request, sample_ticket_data, mock_current_user
    ):
        """Test updating only ticket metadata."""
        from ciris_engine.logic.adapters.api.routes.tickets import UpdateTicketRequest

        updated_metadata = sample_ticket_data["metadata"].copy()
        updated_metadata["custom_field"] = "new_value"

        mock_get_ticket.side_effect = [
            sample_ticket_data,  # First call for verification
            {**sample_ticket_data, "metadata": updated_metadata},  # Second call after update
        ]
        mock_update_metadata.return_value = True

        request_data = UpdateTicketRequest(metadata={"custom_field": "new_value"})

        result = await update_existing_ticket("DSAR-20250108-ABC123", request_data, mock_request, mock_current_user)

        assert "custom_field" in result.metadata
        assert result.metadata["custom_field"] == "new_value"
        mock_update_metadata.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    @patch("ciris_engine.logic.adapters.api.routes.tickets.update_ticket_status")
    @patch("ciris_engine.logic.adapters.api.routes.tickets.update_ticket_metadata")
    async def test_update_ticket_both_status_and_metadata(
        self,
        mock_update_metadata,
        mock_update_status,
        mock_get_ticket,
        mock_request,
        sample_ticket_data,
        mock_current_user,
    ):
        """Test updating both status and metadata."""
        from ciris_engine.logic.adapters.api.routes.tickets import UpdateTicketRequest

        updated_data = sample_ticket_data.copy()
        updated_data["status"] = "in_progress"
        updated_data["metadata"]["custom_field"] = "new_value"

        mock_get_ticket.side_effect = [
            sample_ticket_data,  # First call for verification
            updated_data,  # Second call after updates
        ]
        mock_update_status.return_value = True
        mock_update_metadata.return_value = True

        request_data = UpdateTicketRequest(
            status="in_progress",
            metadata={"custom_field": "new_value"},
        )

        result = await update_existing_ticket("DSAR-20250108-ABC123", request_data, mock_request, mock_current_user)

        assert result.status == "in_progress"
        assert result.metadata["custom_field"] == "new_value"
        mock_update_status.assert_called_once()
        mock_update_metadata.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    async def test_update_ticket_not_found(self, mock_get_ticket, mock_request, mock_current_user):
        """Test updating non-existent ticket."""
        from ciris_engine.logic.adapters.api.routes.tickets import UpdateTicketRequest

        mock_get_ticket.return_value = None

        request_data = UpdateTicketRequest(status="in_progress")

        with pytest.raises(HTTPException) as exc_info:
            await update_existing_ticket("NONEXISTENT-123", request_data, mock_request, mock_current_user)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    @patch("ciris_engine.logic.adapters.api.routes.tickets.update_ticket_status")
    async def test_update_ticket_status_failed(
        self, mock_update_status, mock_get_ticket, mock_request, sample_ticket_data, mock_current_user
    ):
        """Test status update failure."""
        from ciris_engine.logic.adapters.api.routes.tickets import UpdateTicketRequest

        mock_get_ticket.return_value = sample_ticket_data
        mock_update_status.return_value = False

        request_data = UpdateTicketRequest(status="in_progress")

        with pytest.raises(HTTPException) as exc_info:
            await update_existing_ticket("DSAR-20250108-ABC123", request_data, mock_request, mock_current_user)

        assert exc_info.value.status_code == 500
        assert "Failed to update ticket status" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    @patch("ciris_engine.logic.adapters.api.routes.tickets.update_ticket_metadata")
    async def test_update_ticket_metadata_failed(
        self, mock_update_metadata, mock_get_ticket, mock_request, sample_ticket_data, mock_current_user
    ):
        """Test metadata update failure."""
        from ciris_engine.logic.adapters.api.routes.tickets import UpdateTicketRequest

        mock_get_ticket.return_value = sample_ticket_data
        mock_update_metadata.return_value = False

        request_data = UpdateTicketRequest(metadata={"custom": "value"})

        with pytest.raises(HTTPException) as exc_info:
            await update_existing_ticket("DSAR-20250108-ABC123", request_data, mock_request, mock_current_user)

        assert exc_info.value.status_code == 500
        assert "Failed to update ticket metadata" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    @patch("ciris_engine.logic.adapters.api.routes.tickets.update_ticket_metadata")
    async def test_update_ticket_deep_merge_metadata(
        self, mock_update_metadata, mock_get_ticket, mock_request, sample_ticket_data, mock_current_user
    ):
        """Test deep merging of metadata."""
        from ciris_engine.logic.adapters.api.routes.tickets import UpdateTicketRequest

        # Setup ticket with nested metadata
        ticket_with_nested_metadata = sample_ticket_data.copy()
        ticket_with_nested_metadata["metadata"] = {
            "stages": {
                "identity_resolution": {
                    "status": "pending",
                    "result": None,
                }
            },
            "custom_section": {
                "field1": "value1",
                "field2": "value2",
            },
        }

        # Expected merged result
        expected_merged_metadata = {
            "stages": {
                "identity_resolution": {
                    "status": "completed",  # Updated
                    "result": {"success": True},  # Updated
                }
            },
            "custom_section": {
                "field1": "value1",  # Unchanged
                "field2": "updated_value2",  # Updated
            },
        }

        mock_get_ticket.side_effect = [
            ticket_with_nested_metadata,  # First call
            {**ticket_with_nested_metadata, "metadata": expected_merged_metadata},  # After update
        ]
        mock_update_metadata.return_value = True

        request_data = UpdateTicketRequest(
            metadata={
                "stages": {
                    "identity_resolution": {
                        "status": "completed",
                        "result": {"success": True},
                    }
                },
                "custom_section": {
                    "field2": "updated_value2",
                },
            }
        )

        result = await update_existing_ticket("DSAR-20250108-ABC123", request_data, mock_request, mock_current_user)

        # Verify deep merge was called correctly
        assert mock_update_metadata.called
        call_args = mock_update_metadata.call_args
        merged_metadata = call_args[1]["metadata"]

        # Check that field1 wasn't removed (deep merge)
        assert merged_metadata["custom_section"]["field1"] == "value1"
        # Check that field2 was updated
        assert merged_metadata["custom_section"]["field2"] == "updated_value2"


class TestCancelTicket:
    """Test DELETE /tickets/{ticket_id} endpoint."""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    @patch("ciris_engine.logic.adapters.api.routes.tickets.delete_ticket")
    async def test_cancel_ticket_success(
        self, mock_delete_ticket, mock_get_ticket, mock_request, sample_ticket_data, mock_current_user
    ):
        """Test successfully cancelling a ticket."""
        mock_get_ticket.return_value = sample_ticket_data
        mock_delete_ticket.return_value = True

        result = await cancel_ticket("DSAR-20250108-ABC123", mock_request, mock_current_user)

        assert result.success is True
        assert "cancelled/deleted successfully" in result.message
        mock_delete_ticket.assert_called_once_with("DSAR-20250108-ABC123", db_path=None)

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    async def test_cancel_ticket_not_found(self, mock_get_ticket, mock_request, mock_current_user):
        """Test cancelling non-existent ticket."""
        mock_get_ticket.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await cancel_ticket("NONEXISTENT-123", mock_request, mock_current_user)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.tickets.get_ticket")
    @patch("ciris_engine.logic.adapters.api.routes.tickets.delete_ticket")
    async def test_cancel_ticket_deletion_failed(
        self, mock_delete_ticket, mock_get_ticket, mock_request, sample_ticket_data, mock_current_user
    ):
        """Test ticket deletion failure."""
        mock_get_ticket.return_value = sample_ticket_data
        mock_delete_ticket.return_value = False

        with pytest.raises(HTTPException) as exc_info:
            await cancel_ticket("DSAR-20250108-ABC123", mock_request, mock_current_user)

        assert exc_info.value.status_code == 500
        assert "Failed to delete ticket" in exc_info.value.detail
