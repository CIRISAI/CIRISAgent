"""
Tests for DSARAutomationService helper methods.

Focuses on testing the newly extracted helper methods for SonarCloud fixes.
"""

from unittest.mock import MagicMock, Mock

import pytest

from ciris_engine.logic.services.governance.consent.dsar_automation import DSARAutomationService
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


class TestDSARAutomationHelpers:
    """Test DSAR automation helper methods."""

    def test_extract_attributes_with_dict(self, dsar_automation_service):
        """Test _extract_attributes handles dict attributes."""
        # Setup: node with dict attributes
        node = Mock()
        node.attributes = {
            "channel_id": "channel_123",
            "participants": {"user_001": {"message_count": 10}},
        }

        # Execute
        attrs = dsar_automation_service._extract_attributes(node)

        # Assert
        assert isinstance(attrs, dict)
        assert attrs["channel_id"] == "channel_123"
        assert "participants" in attrs

    def test_extract_attributes_with_pydantic_model(self, dsar_automation_service):
        """Test _extract_attributes handles Pydantic model attributes."""
        # Setup: node with Pydantic model attributes
        node = Mock()
        mock_model = Mock()
        mock_model.model_dump.return_value = {
            "channel_id": "channel_456",
            "participants": {"user_002": {"message_count": 20}},
        }
        node.attributes = mock_model

        # Execute
        attrs = dsar_automation_service._extract_attributes(node)

        # Assert
        assert isinstance(attrs, dict)
        assert attrs["channel_id"] == "channel_456"
        mock_model.model_dump.assert_called_once()

    def test_get_channel_id_with_valid_channel(self, dsar_automation_service):
        """Test _get_channel_id extracts channel ID correctly."""
        # Setup
        attrs = {"channel_id": "channel_789"}

        # Execute
        channel_id = dsar_automation_service._get_channel_id(attrs)

        # Assert
        assert channel_id == "channel_789"

    def test_get_channel_id_with_missing_channel(self, dsar_automation_service):
        """Test _get_channel_id returns 'unknown' when channel_id missing."""
        # Setup
        attrs = {}

        # Execute
        channel_id = dsar_automation_service._get_channel_id(attrs)

        # Assert
        assert channel_id == "unknown"

    def test_get_channel_id_with_none_channel(self, dsar_automation_service):
        """Test _get_channel_id handles None channel_id."""
        # Setup
        attrs = {"channel_id": None}

        # Execute
        channel_id = dsar_automation_service._get_channel_id(attrs)

        # Assert
        assert channel_id == "unknown"

    def test_get_channel_id_with_numeric_channel(self, dsar_automation_service):
        """Test _get_channel_id converts numeric channel ID to string."""
        # Setup
        attrs = {"channel_id": 12345}

        # Execute
        channel_id = dsar_automation_service._get_channel_id(attrs)

        # Assert
        assert channel_id == "12345"
        assert isinstance(channel_id, str)

    def test_get_current_count_with_existing_channel(self, dsar_automation_service):
        """Test _get_current_count retrieves existing count."""
        # Setup
        summary = {"channel_123": 50}

        # Execute
        count = dsar_automation_service._get_current_count(summary, "channel_123")

        # Assert
        assert count == 50

    def test_get_current_count_with_missing_channel(self, dsar_automation_service):
        """Test _get_current_count returns 0 for missing channel."""
        # Setup
        summary = {}

        # Execute
        count = dsar_automation_service._get_current_count(summary, "channel_999")

        # Assert
        assert count == 0

    def test_get_current_count_with_float_value(self, dsar_automation_service):
        """Test _get_current_count converts float to int."""
        # Setup
        summary = {"channel_123": 50.7}

        # Execute
        count = dsar_automation_service._get_current_count(summary, "channel_123")

        # Assert
        assert count == 50
        assert isinstance(count, int)

    def test_get_current_count_with_invalid_type(self, dsar_automation_service):
        """Test _get_current_count handles non-numeric values."""
        # Setup
        summary = {"channel_123": "not_a_number"}

        # Execute
        count = dsar_automation_service._get_current_count(summary, "channel_123")

        # Assert
        assert count == 0

    def test_process_participant_matching_user(self, dsar_automation_service):
        """Test _process_participant processes matching user correctly."""
        # Setup
        user_id = "user_001"
        participant_id = "user_001"
        participant_data = {"message_count": 25}
        attrs = {"channel_id": "channel_123"}
        summary = {"channel_123": 10}

        # Execute
        count = dsar_automation_service._process_participant(participant_id, participant_data, user_id, attrs, summary)

        # Assert
        assert count == 25
        assert summary["channel_123"] == 35  # 10 + 25

    def test_process_participant_non_matching_user(self, dsar_automation_service):
        """Test _process_participant ignores non-matching user."""
        # Setup
        user_id = "user_001"
        participant_id = "user_002"  # Different user
        participant_data = {"message_count": 25}
        attrs = {"channel_id": "channel_123"}
        summary = {"channel_123": 10}

        # Execute
        count = dsar_automation_service._process_participant(participant_id, participant_data, user_id, attrs, summary)

        # Assert
        assert count == 0
        assert summary["channel_123"] == 10  # Unchanged

    def test_process_participant_invalid_participant_data(self, dsar_automation_service):
        """Test _process_participant handles non-dict participant data."""
        # Setup
        user_id = "user_001"
        participant_id = "user_001"
        participant_data = "invalid"  # Not a dict
        attrs = {"channel_id": "channel_123"}
        summary = {}

        # Execute
        count = dsar_automation_service._process_participant(participant_id, participant_data, user_id, attrs, summary)

        # Assert
        assert count == 0
        assert len(summary) == 0

    def test_process_conversation_summary_with_valid_node(
        self, dsar_automation_service, sample_conversation_summary_node
    ):
        """Test _process_conversation_summary processes valid node."""
        # Setup
        user_id = "temp_user_123"
        summary = {}

        # Execute
        total = dsar_automation_service._process_conversation_summary(
            sample_conversation_summary_node, user_id, summary
        )

        # Assert
        assert total == 25  # From fixture: user has 25 messages
        assert "channel_123" in summary
        assert summary["channel_123"] == 25

    def test_process_conversation_summary_with_no_attributes(self, dsar_automation_service):
        """Test _process_conversation_summary handles node without attributes."""
        # Setup
        node = Mock()
        node.attributes = None
        summary = {}

        # Execute
        total = dsar_automation_service._process_conversation_summary(node, "user_001", summary)

        # Assert
        assert total == 0
        assert len(summary) == 0

    def test_process_conversation_summary_with_invalid_participants(self, dsar_automation_service):
        """Test _process_conversation_summary handles non-dict participants."""
        # Setup
        node = Mock()
        node.attributes = {"participants": "not_a_dict"}
        summary = {}

        # Execute
        total = dsar_automation_service._process_conversation_summary(node, "user_001", summary)

        # Assert
        assert total == 0

    def test_process_conversation_summary_with_multiple_participants(self, dsar_automation_service, mock_time_service):
        """Test _process_conversation_summary handles multiple participants correctly."""
        # Setup
        node = Mock()
        node.attributes = {
            "channel_id": "channel_multi",
            "participants": {
                "user_target": {"message_count": 30},
                "user_other1": {"message_count": 20},
                "user_other2": {"message_count": 15},
            },
        }
        user_id = "user_target"
        summary = {}

        # Execute
        total = dsar_automation_service._process_conversation_summary(node, user_id, summary)

        # Assert
        assert total == 30  # Only counts target user's messages
        assert summary["channel_multi"] == 30

    def test_process_conversation_summary_accumulates_across_channels(
        self, dsar_automation_service, sample_conversation_summary_nodes_multiple
    ):
        """Test _process_conversation_summary accumulates counts across multiple nodes."""
        # Setup
        user_id = "temp_user_123"
        summary = {}

        # Execute: process all three nodes
        total = 0
        for node in sample_conversation_summary_nodes_multiple:
            total += dsar_automation_service._process_conversation_summary(node, user_id, summary)

        # Assert
        # Node 1: channel_123 = 25
        # Node 2: channel_456 = 10
        # Node 3: channel_123 = 5 (adds to existing)
        assert total == 40  # 25 + 10 + 5
        assert summary["channel_123"] == 30  # 25 + 5
        assert summary["channel_456"] == 10

    def test_get_data_categories_partnered(self, dsar_automation_service, sample_permanent_consent):
        """Test _get_data_categories returns correct categories for PARTNERED stream."""
        # Setup: modify to partnered stream
        sample_permanent_consent.stream = "partnered"

        # Execute
        categories = dsar_automation_service._get_data_categories(sample_permanent_consent)

        # Assert
        assert "user_identifier" in categories
        assert "consent_status" in categories
        assert "behavioral_patterns" in categories
        assert "preferences" in categories
        assert "contribution_data" in categories

    def test_get_data_categories_temporary(self, dsar_automation_service, sample_temporary_consent):
        """Test _get_data_categories returns correct categories for TEMPORARY stream."""
        # Setup
        sample_temporary_consent.stream = "temporary"

        # Execute
        categories = dsar_automation_service._get_data_categories(sample_temporary_consent)

        # Assert
        assert "user_identifier" in categories
        assert "consent_status" in categories
        assert "session_data" in categories
        assert "basic_interactions" in categories

    def test_get_retention_periods_temporary(self, dsar_automation_service, sample_temporary_consent):
        """Test _get_retention_periods returns correct periods for TEMPORARY stream."""
        # Setup
        sample_temporary_consent.stream = "temporary"

        # Execute
        periods = dsar_automation_service._get_retention_periods(sample_temporary_consent)

        # Assert
        assert "14 days" in periods["consent_status"]
        assert "14 days" in periods["interaction_data"]
        assert "indefinite" in periods["audit_trail"]

    def test_get_retention_periods_partnered(self, dsar_automation_service, sample_permanent_consent):
        """Test _get_retention_periods returns correct periods for PARTNERED stream."""
        # Setup
        sample_permanent_consent.stream = "partnered"

        # Execute
        periods = dsar_automation_service._get_retention_periods(sample_permanent_consent)

        # Assert
        assert "indefinite" in periods["consent_status"]
        assert "indefinite" in periods["behavioral_patterns"]

    def test_get_processing_purposes_partnered(self, dsar_automation_service, sample_permanent_consent):
        """Test _get_processing_purposes returns correct purposes for PARTNERED stream."""
        # Setup
        sample_permanent_consent.stream = "partnered"

        # Execute
        purposes = dsar_automation_service._get_processing_purposes(sample_permanent_consent)

        # Assert
        assert "consent_management" in purposes
        assert "personalization" in purposes
        assert "service_improvement" in purposes
        assert "relationship_development" in purposes

    def test_get_processing_purposes_temporary(self, dsar_automation_service, sample_temporary_consent):
        """Test _get_processing_purposes returns correct purposes for TEMPORARY stream."""
        # Setup
        sample_temporary_consent.stream = "temporary"

        # Execute
        purposes = dsar_automation_service._get_processing_purposes(sample_temporary_consent)

        # Assert
        assert "consent_management" in purposes
        assert "service_delivery" in purposes
        assert "session_continuity" in purposes
