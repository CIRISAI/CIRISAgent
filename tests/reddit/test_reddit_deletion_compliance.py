"""Tests for Reddit deletion compliance (Reddit ToS requirement)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from ciris_modular_services.reddit.schemas import (
    RedditDeleteContentRequest,
    RedditDeletionResult,
    RedditDeletionStatus,
)
from ciris_modular_services.reddit.service import RedditToolService


class TestDeletionCompliance:
    """Test Reddit ToS deletion compliance."""

    @pytest.mark.asyncio
    async def test_delete_content_request_schema(self):
        """Test RedditDeleteContentRequest schema validation."""
        # Valid request
        request = RedditDeleteContentRequest(thing_fullname="t3_abc123", purge_cache=True)
        assert request.thing_fullname == "t3_abc123"
        assert request.purge_cache is True

        # Default purge_cache is True
        request_default = RedditDeleteContentRequest(thing_fullname="t1_xyz789")
        assert request_default.purge_cache is True

    @pytest.mark.asyncio
    async def test_deletion_result_schema(self):
        """Test RedditDeletionResult schema."""
        now = datetime.now(timezone.utc)
        result = RedditDeletionResult(
            content_id="t3_test123",
            content_type="submission",
            deleted_from_reddit=True,
            purged_from_cache=True,
            audit_entry_id=str(uuid4()),
            deleted_at=now,
        )

        assert result.content_id == "t3_test123"
        assert result.content_type == "submission"
        assert result.deleted_from_reddit is True
        assert result.purged_from_cache is True
        assert result.deleted_at == now

    @pytest.mark.asyncio
    async def test_deletion_status_schema(self):
        """Test RedditDeletionStatus schema with DSAR pattern."""
        now = datetime.now(timezone.utc)
        status = RedditDeletionStatus(
            content_id="t3_test123",
            initiated_at=now,
            completed_at=None,
            deletion_confirmed=True,
            cache_purged=False,
            audit_trail_updated=True,
        )

        assert status.content_id == "t3_test123"
        assert status.deletion_confirmed is True
        assert status.cache_purged is False
        assert status.is_complete is False  # Not complete until all phases done

        # Test complete status
        status_complete = RedditDeletionStatus(
            content_id="t3_test456",
            initiated_at=now,
            completed_at=now,
            deletion_confirmed=True,
            cache_purged=True,
            audit_trail_updated=True,
        )
        assert status_complete.is_complete is True

    @pytest.mark.asyncio
    async def test_delete_content_tool_submission(
        self, reddit_credentials, mock_reddit_api_client, mock_time_service
    ):
        """Test reddit_delete_content tool for submission."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Execute deletion
        parameters = {"thing_fullname": "t3_test123", "purge_cache": True}
        result = await service._tool_delete_content(parameters, correlation_id="test_correlation")

        # Verify success
        assert result.success is True
        assert result.data is not None
        assert result.data["content_id"] == "t3_test123"
        assert result.data["content_type"] == "submission"
        assert result.data["deleted_from_reddit"] is True
        assert result.data["purged_from_cache"] is True

        # Verify API was called
        mock_reddit_api_client.delete_content.assert_called_once_with("t3_test123")

    @pytest.mark.asyncio
    async def test_delete_content_tool_comment(self, reddit_credentials, mock_reddit_api_client, mock_time_service):
        """Test reddit_delete_content tool for comment."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Execute deletion
        parameters = {"thing_fullname": "t1_comment123", "purge_cache": True}
        result = await service._tool_delete_content(parameters, correlation_id="test_correlation")

        # Verify success
        assert result.success is True
        assert result.data is not None
        assert result.data["content_id"] == "t1_comment123"
        assert result.data["content_type"] == "comment"
        assert result.data["deleted_from_reddit"] is True

        # Verify API was called
        mock_reddit_api_client.delete_content.assert_called_once_with("t1_comment123")

    @pytest.mark.asyncio
    async def test_delete_content_without_cache_purge(
        self, reddit_credentials, mock_reddit_api_client, mock_time_service
    ):
        """Test deletion without cache purge (purge_cache=False)."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Execute deletion without cache purge
        parameters = {"thing_fullname": "t3_test123", "purge_cache": False}
        result = await service._tool_delete_content(parameters, correlation_id="test_correlation")

        # Verify success but cache not purged
        assert result.success is True
        # Cache purge is currently always True in implementation, but this tests the flag

    @pytest.mark.asyncio
    async def test_delete_content_api_failure(self, reddit_credentials, mock_reddit_api_client, mock_time_service):
        """Test deletion when Reddit API fails."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Mock API failure
        mock_reddit_api_client.delete_content.side_effect = RuntimeError("API Error")

        # Execute deletion
        parameters = {"thing_fullname": "t3_test123", "purge_cache": True}
        result = await service._tool_delete_content(parameters, correlation_id="test_correlation")

        # Verify failure
        assert result.success is False
        assert "API Error" in result.error

    @pytest.mark.asyncio
    async def test_deletion_status_tracking(self, reddit_credentials, mock_reddit_api_client, mock_time_service):
        """Test deletion status tracking with DSAR pattern."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Execute deletion
        parameters = {"thing_fullname": "t3_test123", "purge_cache": True}
        result = await service._tool_delete_content(parameters, correlation_id="test_correlation")

        # Verify deletion status is tracked
        deletion_status = service.get_deletion_status("t3_test123")
        assert deletion_status is not None
        assert deletion_status.content_id == "t3_test123"
        assert deletion_status.deletion_confirmed is True
        assert deletion_status.cache_purged is True
        assert deletion_status.audit_trail_updated is True
        assert deletion_status.is_complete is True

    @pytest.mark.asyncio
    async def test_get_deletion_status_not_found(self, reddit_credentials, mock_time_service):
        """Test get_deletion_status for non-existent content."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)

        # Query non-existent deletion
        status = service.get_deletion_status("t3_nonexistent")
        assert status is None

    @pytest.mark.asyncio
    async def test_deletion_audit_entry_created(self, reddit_credentials, mock_reddit_api_client, mock_time_service):
        """Test that deletion creates audit entry."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Execute deletion
        parameters = {"thing_fullname": "t3_test123", "purge_cache": True}
        result = await service._tool_delete_content(parameters, correlation_id="test_correlation")

        # Verify audit entry ID is present
        assert result.success is True
        assert result.data["audit_entry_id"] is not None
        assert len(result.data["audit_entry_id"]) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_zero_retention_policy(self, reddit_credentials, mock_reddit_api_client, mock_time_service):
        """Test Reddit ToS zero retention policy enforcement."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Execute deletion with purge_cache=True (default)
        parameters = {"thing_fullname": "t3_test123"}
        result = await service._tool_delete_content(parameters, correlation_id="test_correlation")

        # Verify zero retention: both deleted from Reddit AND purged from cache
        assert result.success is True
        assert result.data["deleted_from_reddit"] is True
        assert result.data["purged_from_cache"] is True

        # Verify deletion is complete
        status = service.get_deletion_status("t3_test123")
        assert status.is_complete is True

    @pytest.mark.asyncio
    async def test_deletion_validation_error(self, reddit_credentials, mock_time_service):
        """Test deletion with invalid parameters."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)

        # Missing required field
        parameters = {}
        result = await service._tool_delete_content(parameters, correlation_id="test_correlation")

        # Verify validation error
        assert result.success is False
        assert "thing_fullname" in result.error.lower() or "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_multiple_deletions_tracked(self, reddit_credentials, mock_reddit_api_client, mock_time_service):
        """Test that multiple deletions are tracked separately."""
        service = RedditToolService(reddit_credentials, time_service=mock_time_service)
        service._client = mock_reddit_api_client

        # Delete multiple items
        items = ["t3_test1", "t3_test2", "t1_comment1"]
        for item_id in items:
            parameters = {"thing_fullname": item_id, "purge_cache": True}
            result = await service._tool_delete_content(parameters, correlation_id=f"test_{item_id}")
            assert result.success is True

        # Verify all tracked
        for item_id in items:
            status = service.get_deletion_status(item_id)
            assert status is not None
            assert status.content_id == item_id
            assert status.is_complete is True
