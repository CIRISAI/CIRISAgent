"""
Tests for PartnershipManager helper methods.

Focuses on testing the newly extracted helper methods for SonarCloud fixes.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock

from ciris_engine.logic.services.governance.consent.partnership import PartnershipManager
from ciris_engine.schemas.consent.core import (
    ConsentCategory,
    ConsentRequest,
    ConsentStatus,
    ConsentStream,
)


class TestPartnershipManagerHelpers:
    """Test partnership manager helper methods."""

    def test_create_pending_status_with_previous_status(
        self, partnership_manager, sample_permanent_consent
    ):
        """Test _create_pending_status preserves previous consent details."""
        # Execute
        pending = partnership_manager._create_pending_status(
            sample_permanent_consent.user_id, sample_permanent_consent
        )

        # Assert
        assert pending.user_id == sample_permanent_consent.user_id
        assert pending.stream == sample_permanent_consent.stream
        assert pending.categories == sample_permanent_consent.categories
        assert pending.granted_at == sample_permanent_consent.granted_at
        assert pending.expires_at == sample_permanent_consent.expires_at
        assert pending.impact_score == sample_permanent_consent.impact_score
        assert pending.attribution_count == sample_permanent_consent.attribution_count

    def test_create_pending_status_without_previous_status(self, partnership_manager, mock_time_service):
        """Test _create_pending_status creates defaults when no previous status."""
        # Execute
        user_id = "new_user_001"
        pending = partnership_manager._create_pending_status(user_id, None)

        # Assert
        assert pending.user_id == user_id
        assert pending.stream == ConsentStream.TEMPORARY  # Default stream
        assert pending.categories == []  # Default empty categories
        assert pending.impact_score == 0.0  # Default score
        assert pending.attribution_count == 0  # Default count
        # Should create temporary with 14-day expiry
        assert pending.expires_at is not None
        expected_expiry = mock_time_service.now() + timedelta(days=14)
        assert abs((pending.expires_at - expected_expiry).total_seconds()) < 1

    def test_create_pending_status_updates_last_modified(self, partnership_manager, mock_time_service):
        """Test _create_pending_status updates last_modified to current time."""
        # Setup: create old consent
        old_consent = ConsentStatus(
            user_id="old_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=mock_time_service.now() - timedelta(days=30),
            expires_at=mock_time_service.now() + timedelta(days=14),
            last_modified=mock_time_service.now() - timedelta(days=30),
            impact_score=0.5,
            attribution_count=10,
        )

        # Execute
        pending = partnership_manager._create_pending_status(old_consent.user_id, old_consent)

        # Assert
        assert pending.last_modified == mock_time_service.now()
        assert pending.last_modified != old_consent.last_modified

    def test_store_pending_partnership(
        self, partnership_manager, mock_time_service, sample_partnership_request
    ):
        """Test _store_pending_partnership stores correct data structure."""
        # Setup
        task_id = "task_123"
        channel_id = "channel_456"
        request = ConsentRequest(
            user_id=sample_partnership_request.user_id,
            stream=ConsentStream.PARTNERED,
            categories=sample_partnership_request.categories,
            reason=sample_partnership_request.reason,
        )

        # Execute
        partnership_manager._store_pending_partnership(request.user_id, task_id, request, channel_id)

        # Assert
        assert request.user_id in partnership_manager._pending_partnerships
        pending = partnership_manager._pending_partnerships[request.user_id]

        assert pending["task_id"] == task_id
        assert pending["channel_id"] == channel_id
        assert pending["created_at"] == mock_time_service.now().isoformat()
        assert "request" in pending
        assert isinstance(pending["request"], dict)

    def test_store_pending_partnership_with_no_channel(
        self, partnership_manager, sample_partnership_request
    ):
        """Test _store_pending_partnership handles missing channel_id."""
        # Setup
        request = ConsentRequest(
            user_id=sample_partnership_request.user_id,
            stream=ConsentStream.PARTNERED,
            categories=sample_partnership_request.categories,
            reason=sample_partnership_request.reason,
        )

        # Execute with None channel
        partnership_manager._store_pending_partnership(request.user_id, "task_001", request, None)

        # Assert
        pending = partnership_manager._pending_partnerships[request.user_id]
        assert pending["channel_id"] == "unknown"  # Default fallback

    def test_create_partnership_task_creates_handler(self, partnership_manager):
        """Test _create_partnership_task creates PartnershipRequestHandler."""
        # Setup
        user_id = "task_user_001"
        categories = [ConsentCategory.PREFERENCE, ConsentCategory.RESEARCH]
        reason = "Want to collaborate"
        channel_id = "channel_789"

        # Execute with mocked database interaction
        from unittest.mock import patch

        with patch('ciris_engine.logic.utils.consent.partnership_utils.persistence.add_task'):
            task = partnership_manager._create_partnership_task(user_id, categories, reason, channel_id)

            # Assert
            assert task is not None
            assert hasattr(task, "task_id")

    def test_create_partnership_task_requires_time_service(self):
        """Test _create_partnership_task raises error without time service."""
        # Setup: manager with no time service
        manager = PartnershipManager(time_service=None)

        # Execute & Assert
        with pytest.raises(ValueError, match="TimeService required"):
            manager._create_partnership_task(
                "user_001", [ConsentCategory.PREFERENCE], "reason", "channel"
            )

    def test_get_request_counts(self, partnership_manager):
        """Test get_request_counts returns correct tuple."""
        # Setup: simulate some partnership activity
        partnership_manager._partnership_requests = 10
        partnership_manager._partnership_approvals = 7
        partnership_manager._partnership_rejections = 2

        # Execute
        requests, approvals, rejections = partnership_manager.get_request_counts()

        # Assert
        assert requests == 10
        assert approvals == 7
        assert rejections == 2

    def test_get_pending_count(self, partnership_manager, pending_partnership_data):
        """Test get_pending_count returns correct count."""
        # Setup
        partnership_manager._pending_partnerships = pending_partnership_data

        # Execute
        count = partnership_manager.get_pending_count()

        # Assert
        assert count == len(pending_partnership_data)

    def test_get_pending_count_empty(self, partnership_manager):
        """Test get_pending_count returns 0 when no pending partnerships."""
        # Execute
        count = partnership_manager.get_pending_count()

        # Assert
        assert count == 0

    def test_finalize_partnership_approval(self, partnership_manager, pending_partnership_data):
        """Test finalize_partnership_approval processes approval correctly."""
        # Setup
        partnership_manager._pending_partnerships = pending_partnership_data.copy()
        user_id = "partnership_user_001"
        task_id = "task_001"

        # Execute
        result = partnership_manager.finalize_partnership_approval(user_id, task_id)

        # Assert
        assert result is not None
        assert result["user_id"] == user_id
        assert result["task_id"] == task_id
        assert "categories" in result
        assert "approved_at" in result

        # Verify removed from pending
        assert user_id not in partnership_manager._pending_partnerships

        # Verify approval tracked
        assert partnership_manager._partnership_approvals == 1

    def test_finalize_partnership_approval_nonexistent_user(self, partnership_manager):
        """Test finalize_partnership_approval returns None for nonexistent user."""
        # Execute
        result = partnership_manager.finalize_partnership_approval("nonexistent_user", "task_001")

        # Assert
        assert result is None
        assert partnership_manager._partnership_approvals == 0

    def test_finalize_partnership_approval_task_mismatch(
        self, partnership_manager, pending_partnership_data
    ):
        """Test finalize_partnership_approval returns None for task ID mismatch."""
        # Setup
        partnership_manager._pending_partnerships = pending_partnership_data.copy()
        user_id = "partnership_user_001"
        wrong_task_id = "wrong_task_999"

        # Execute
        result = partnership_manager.finalize_partnership_approval(user_id, wrong_task_id)

        # Assert
        assert result is None
        # User should still be in pending
        assert user_id in partnership_manager._pending_partnerships

    def test_list_pending_partnerships_aging_status(
        self, partnership_manager, mock_time_service, pending_partnership_data
    ):
        """Test list_pending_partnerships calculates aging status correctly."""
        # Setup: modify pending partnership to be old
        now = mock_time_service.now()
        old_partnership = {
            "partnership_user_002": {
                "task_id": "task_002",
                "request": {
                    "user_id": "partnership_user_002",
                    "categories": ["partnership"],
                    "reason": "Old request",
                    "channel_id": "channel_789",
                },
                "created_at": (now - timedelta(days=15)).isoformat(),  # 15 days old = critical
                "channel_id": "channel_789",
            }
        }
        partnership_manager._pending_partnerships = old_partnership

        # Execute
        pending_list = partnership_manager.list_pending_partnerships()

        # Assert
        assert len(pending_list) == 1
        assert pending_list[0]["aging_status"] == "critical"
        assert pending_list[0]["age_hours"] > 336  # > 14 days

    def test_list_pending_partnerships_sorted_by_age(
        self, partnership_manager, mock_time_service
    ):
        """Test list_pending_partnerships sorts by age (oldest first)."""
        # Setup: create partnerships with different ages
        now = mock_time_service.now()
        partnership_manager._pending_partnerships = {
            "user_new": {
                "task_id": "task_new",
                "request": {"user_id": "user_new", "categories": [], "reason": "", "channel_id": "ch1"},
                "created_at": (now - timedelta(hours=1)).isoformat(),
                "channel_id": "ch1",
            },
            "user_old": {
                "task_id": "task_old",
                "request": {"user_id": "user_old", "categories": [], "reason": "", "channel_id": "ch2"},
                "created_at": (now - timedelta(days=10)).isoformat(),
                "channel_id": "ch2",
            },
            "user_mid": {
                "task_id": "task_mid",
                "request": {"user_id": "user_mid", "categories": [], "reason": "", "channel_id": "ch3"},
                "created_at": (now - timedelta(days=3)).isoformat(),
                "channel_id": "ch3",
            },
        }

        # Execute
        pending_list = partnership_manager.list_pending_partnerships()

        # Assert
        assert len(pending_list) == 3
        # Should be sorted oldest first
        assert pending_list[0]["user_id"] == "user_old"
        assert pending_list[1]["user_id"] == "user_mid"
        assert pending_list[2]["user_id"] == "user_new"

    def test_cleanup_aged_requests(self, partnership_manager, mock_time_service):
        """Test cleanup_aged_requests removes requests older than threshold."""
        # Setup
        now = mock_time_service.now()
        partnership_manager._pending_partnerships = {
            "user_old": {
                "task_id": "task_old",
                "request": {"user_id": "user_old", "categories": [], "reason": "", "channel_id": "ch"},
                "created_at": (now - timedelta(days=35)).isoformat(),  # > 30 days
                "channel_id": "ch",
            },
            "user_recent": {
                "task_id": "task_recent",
                "request": {"user_id": "user_recent", "categories": [], "reason": "", "channel_id": "ch"},
                "created_at": (now - timedelta(days=5)).isoformat(),  # < 30 days
                "channel_id": "ch",
            },
        }

        # Execute
        removed_count = partnership_manager.cleanup_aged_requests(max_age_days=30)

        # Assert
        assert removed_count == 1
        assert "user_old" not in partnership_manager._pending_partnerships
        assert "user_recent" in partnership_manager._pending_partnerships
        assert partnership_manager._partnership_rejections == 1

    def test_cleanup_aged_requests_records_history(self, partnership_manager, mock_time_service):
        """Test cleanup_aged_requests records outcomes in history."""
        # Setup
        now = mock_time_service.now()
        user_id = "user_to_expire"
        partnership_manager._pending_partnerships = {
            user_id: {
                "task_id": "task_expire",
                "request": {"user_id": user_id, "categories": [], "reason": "", "channel_id": "ch"},
                "created_at": (now - timedelta(days=40)).isoformat(),
                "channel_id": "ch",
            }
        }

        # Execute
        partnership_manager.cleanup_aged_requests(max_age_days=30)

        # Assert
        assert user_id in partnership_manager._partnership_history
        outcomes = partnership_manager._partnership_history[user_id]
        assert len(outcomes) == 1
        assert outcomes[0].user_id == user_id
        assert "Auto-rejected" in outcomes[0].reason
