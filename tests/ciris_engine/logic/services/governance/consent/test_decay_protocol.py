"""
Tests for DecayProtocolManager helper methods.

Focuses on testing the newly extracted helper methods for SonarCloud fixes.
"""

import pytest
from datetime import datetime, timedelta, timezone

from ciris_engine.logic.services.governance.consent.decay import DecayProtocolManager
from ciris_engine.schemas.consent.core import ConsentDecayStatus


class TestDecayProtocolHelpers:
    """Test decay protocol helper methods."""

    def test_determine_decay_phase_severing_identity(self, decay_protocol_manager, sample_decay_status):
        """Test _determine_decay_phase returns 'severing_identity' for initial decay."""
        # Setup: decay with nothing complete
        sample_decay_status.identity_severed = False
        sample_decay_status.patterns_anonymized = False

        # Execute
        phase = decay_protocol_manager._determine_decay_phase(sample_decay_status)

        # Assert
        assert phase == "severing_identity"

    def test_determine_decay_phase_anonymizing_patterns(
        self, decay_protocol_manager, sample_decay_identity_severed
    ):
        """Test _determine_decay_phase returns 'anonymizing_patterns' when identity severed."""
        # Execute
        phase = decay_protocol_manager._determine_decay_phase(sample_decay_identity_severed)

        # Assert
        assert phase == "anonymizing_patterns"

    def test_determine_decay_phase_complete(self, decay_protocol_manager, sample_decay_completed):
        """Test _determine_decay_phase returns 'complete' when patterns anonymized."""
        # Execute
        phase = decay_protocol_manager._determine_decay_phase(sample_decay_completed)

        # Assert
        assert phase == "complete"

    def test_determine_decay_phase_integration_in_get_decay_progress(
        self, decay_protocol_manager, sample_decay_status
    ):
        """Test _determine_decay_phase is correctly used in get_decay_progress."""
        # Setup: add decay to active decays
        decay_protocol_manager._active_decays[sample_decay_status.user_id] = sample_decay_status

        # Execute
        progress = decay_protocol_manager.get_decay_progress(sample_decay_status.user_id)

        # Assert
        assert progress is not None
        assert progress["current_phase"] == "severing_identity"
        assert progress["identity_severed"] is False
        assert progress["patterns_anonymized"] is False

    def test_get_decay_progress_with_identity_severed(
        self, decay_protocol_manager, sample_decay_identity_severed
    ):
        """Test get_decay_progress returns correct phase after identity severance."""
        # Setup
        decay_protocol_manager._active_decays[sample_decay_identity_severed.user_id] = (
            sample_decay_identity_severed
        )

        # Execute
        progress = decay_protocol_manager.get_decay_progress(sample_decay_identity_severed.user_id)

        # Assert
        assert progress is not None
        assert progress["current_phase"] == "anonymizing_patterns"
        assert progress["identity_severed"] is True
        assert progress["patterns_anonymized"] is False

    def test_get_decay_progress_with_completed_decay(self, decay_protocol_manager, sample_decay_completed):
        """Test get_decay_progress returns correct phase for completed decay."""
        # Setup
        decay_protocol_manager._active_decays[sample_decay_completed.user_id] = sample_decay_completed

        # Execute
        progress = decay_protocol_manager.get_decay_progress(sample_decay_completed.user_id)

        # Assert
        assert progress is not None
        assert progress["current_phase"] == "complete"
        assert progress["identity_severed"] is True
        assert progress["patterns_anonymized"] is True

    def test_get_decay_progress_nonexistent_user(self, decay_protocol_manager):
        """Test get_decay_progress returns None for user with no decay."""
        # Execute
        progress = decay_protocol_manager.get_decay_progress("nonexistent_user")

        # Assert
        assert progress is None

    def test_get_decay_progress_completion_percentage(
        self, decay_protocol_manager, mock_time_service, sample_decay_status
    ):
        """Test get_decay_progress calculates completion percentage correctly."""
        # Setup: simulate 30 days elapsed
        now = mock_time_service.now()
        sample_decay_status.decay_started = now - timedelta(days=30)
        sample_decay_status.decay_complete_at = now + timedelta(days=60)
        decay_protocol_manager._active_decays[sample_decay_status.user_id] = sample_decay_status

        # Execute
        progress = decay_protocol_manager.get_decay_progress(sample_decay_status.user_id)

        # Assert
        assert progress is not None
        assert progress["days_elapsed"] == 30
        assert progress["days_remaining"] == 60
        # 30/90 = 33.33%
        assert abs(progress["completion_percentage"] - 33.33) < 0.1

    def test_get_decay_progress_max_completion_percentage(
        self, decay_protocol_manager, mock_time_service, sample_decay_status
    ):
        """Test get_decay_progress caps completion percentage at 100%."""
        # Setup: simulate 100 days elapsed (past 90)
        now = mock_time_service.now()
        sample_decay_status.decay_started = now - timedelta(days=100)
        sample_decay_status.decay_complete_at = now - timedelta(days=10)
        decay_protocol_manager._active_decays[sample_decay_status.user_id] = sample_decay_status

        # Execute
        progress = decay_protocol_manager.get_decay_progress(sample_decay_status.user_id)

        # Assert
        assert progress is not None
        assert progress["completion_percentage"] == 100.0
        assert progress["days_remaining"] == 0  # Capped at 0

    def test_get_decay_milestones(self, decay_protocol_manager, sample_decay_status):
        """Test get_decay_milestones returns correct milestone dates."""
        # Setup
        decay_protocol_manager._active_decays[sample_decay_status.user_id] = sample_decay_status

        # Execute
        milestones = decay_protocol_manager.get_decay_milestones(sample_decay_status.user_id)

        # Assert
        assert milestones is not None
        assert "initiated" in milestones
        assert "one_third_complete" in milestones
        assert "two_thirds_complete" in milestones
        assert "completion" in milestones

        # Verify date formatting
        initiated_date = datetime.strptime(milestones["initiated"], "%Y-%m-%d")
        completion_date = datetime.strptime(milestones["completion"], "%Y-%m-%d")
        assert (completion_date - initiated_date).days == 90

    def test_get_decay_milestones_nonexistent_user(self, decay_protocol_manager):
        """Test get_decay_milestones returns None for nonexistent user."""
        # Execute
        milestones = decay_protocol_manager.get_decay_milestones("nonexistent_user")

        # Assert
        assert milestones is None

    def test_check_decay_status(self, decay_protocol_manager, sample_decay_status):
        """Test check_decay_status returns correct decay status."""
        # Setup
        decay_protocol_manager._active_decays[sample_decay_status.user_id] = sample_decay_status

        # Execute
        status = decay_protocol_manager.check_decay_status(sample_decay_status.user_id)

        # Assert
        assert status is not None
        assert status.user_id == sample_decay_status.user_id
        assert status.identity_severed == sample_decay_status.identity_severed

    def test_check_decay_status_nonexistent_user(self, decay_protocol_manager):
        """Test check_decay_status returns None for nonexistent user."""
        # Execute
        status = decay_protocol_manager.check_decay_status("nonexistent_user")

        # Assert
        assert status is None

    def test_get_active_decays(
        self, decay_protocol_manager, sample_decay_status, sample_decay_identity_severed
    ):
        """Test get_active_decays returns all active decays."""
        # Setup
        decay_protocol_manager._active_decays[sample_decay_status.user_id] = sample_decay_status
        decay_protocol_manager._active_decays[sample_decay_identity_severed.user_id] = (
            sample_decay_identity_severed
        )

        # Execute
        active_decays = decay_protocol_manager.get_active_decays()

        # Assert
        assert len(active_decays) == 2
        assert sample_decay_status.user_id in active_decays
        assert sample_decay_identity_severed.user_id in active_decays

    def test_get_active_decays_returns_copy(self, decay_protocol_manager, sample_decay_status):
        """Test get_active_decays returns a copy, not a reference."""
        # Setup
        decay_protocol_manager._active_decays[sample_decay_status.user_id] = sample_decay_status

        # Execute
        active_decays = decay_protocol_manager.get_active_decays()

        # Modify the copy
        active_decays.clear()

        # Assert: original is unchanged
        assert len(decay_protocol_manager._active_decays) == 1
