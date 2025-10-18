"""
Tests for ConsentService helper methods.

Focuses on testing the newly extracted helper methods for SonarCloud fixes.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from ciris_engine.logic.services.governance.consent.service import ConsentNotFoundError
from ciris_engine.schemas.consent.core import ConsentCategory, ConsentStatus, ConsentStream


class TestConsentServiceHelpers:
    """Test consent service helper methods."""

    def test_check_cached_expiry_with_valid_temporary(
        self, consent_service_with_mocks, sample_temporary_consent
    ):
        """Test _check_cached_expiry allows valid temporary consent."""
        # Setup: consent expires in future
        assert sample_temporary_consent.expires_at is not None
        assert sample_temporary_consent.expires_at > consent_service_with_mocks._time_service.now()

        # Execute & Assert: should not raise
        try:
            consent_service_with_mocks._check_cached_expiry(
                sample_temporary_consent.user_id, sample_temporary_consent
            )
        except ConsentNotFoundError:
            pytest.fail("_check_cached_expiry raised ConsentNotFoundError for valid consent")

    def test_check_cached_expiry_with_expired_temporary(
        self, consent_service_with_mocks, expired_temporary_consent
    ):
        """Test _check_cached_expiry raises for expired temporary consent."""
        # Setup: add to cache
        consent_service_with_mocks._consent_cache[expired_temporary_consent.user_id] = (
            expired_temporary_consent
        )

        # Execute & Assert: should raise and remove from cache
        with pytest.raises(ConsentNotFoundError, match="has expired"):
            consent_service_with_mocks._check_cached_expiry(
                expired_temporary_consent.user_id, expired_temporary_consent
            )

        # Verify removed from cache
        assert expired_temporary_consent.user_id not in consent_service_with_mocks._consent_cache

    def test_check_cached_expiry_with_permanent_consent(
        self, consent_service_with_mocks, sample_permanent_consent
    ):
        """Test _check_cached_expiry allows permanent consent (no expiry)."""
        # Execute & Assert: should not raise
        try:
            consent_service_with_mocks._check_cached_expiry(
                sample_permanent_consent.user_id, sample_permanent_consent
            )
        except ConsentNotFoundError:
            pytest.fail("_check_cached_expiry raised ConsentNotFoundError for permanent consent")

    def test_check_cached_expiry_with_decaying_consent(
        self, consent_service_with_mocks, sample_decaying_consent
    ):
        """Test _check_cached_expiry allows decaying consent with future expiry."""
        # Execute & Assert: should not raise
        try:
            consent_service_with_mocks._check_cached_expiry(
                sample_decaying_consent.user_id, sample_decaying_consent
            )
        except ConsentNotFoundError:
            pytest.fail("_check_cached_expiry raised ConsentNotFoundError for valid decaying consent")

    def test_reconstruct_consent_from_node_with_dict_attributes(
        self, consent_service_with_mocks, mock_time_service
    ):
        """Test _reconstruct_consent_from_node handles dict attributes."""
        # Setup
        user_id = "reconstruct_user_001"
        now = mock_time_service.now()
        node = Mock()
        node.attributes = {
            "stream": "temporary",
            "categories": ["interaction", "preference"],
            "granted_at": now.isoformat(),
            "expires_at": (now + timedelta(days=14)).isoformat(),
            "last_modified": now.isoformat(),
            "impact_score": 0.75,
            "attribution_count": 12,
        }

        # Execute
        status = consent_service_with_mocks._reconstruct_consent_from_node(user_id, node)

        # Assert
        assert status.user_id == user_id
        assert status.stream == ConsentStream.TEMPORARY
        assert ConsentCategory.INTERACTION in status.categories
        assert ConsentCategory.PREFERENCE in status.categories
        assert status.impact_score == 0.75
        assert status.attribution_count == 12

    def test_reconstruct_consent_from_node_with_pydantic_attributes(
        self, consent_service_with_mocks, mock_time_service
    ):
        """Test _reconstruct_consent_from_node handles Pydantic model attributes."""
        # Setup
        user_id = "reconstruct_user_002"
        now = mock_time_service.now()
        node = Mock()
        mock_attrs = Mock()
        mock_attrs.model_dump.return_value = {
            "stream": "partnered",
            "categories": ["preference", "research"],
            "granted_at": now.isoformat(),
            "expires_at": None,
            "last_modified": now.isoformat(),
            "impact_score": 0.95,
            "attribution_count": 100,
        }
        node.attributes = mock_attrs

        # Execute
        status = consent_service_with_mocks._reconstruct_consent_from_node(user_id, node)

        # Assert
        assert status.user_id == user_id
        assert status.stream == ConsentStream.PARTNERED
        assert status.expires_at is None  # Permanent
        mock_attrs.model_dump.assert_called_once()

    def test_reconstruct_consent_from_node_with_missing_expires_at(
        self, consent_service_with_mocks, mock_time_service
    ):
        """Test _reconstruct_consent_from_node handles missing expires_at."""
        # Setup
        user_id = "reconstruct_user_003"
        now = mock_time_service.now()
        node = Mock()
        node.attributes = {
            "stream": "partnered",
            "categories": [],
            "granted_at": now.isoformat(),
            # No expires_at field
            "last_modified": now.isoformat(),
            "impact_score": 0.5,
            "attribution_count": 5,
        }

        # Execute
        status = consent_service_with_mocks._reconstruct_consent_from_node(user_id, node)

        # Assert
        assert status.expires_at is None

    def test_reconstruct_consent_from_node_with_defaults(
        self, consent_service_with_mocks, mock_time_service
    ):
        """Test _reconstruct_consent_from_node uses defaults for missing fields."""
        # Setup
        user_id = "reconstruct_user_004"
        node = Mock()
        node.attributes = {
            "stream": "temporary",
            # Missing most fields - should use defaults
        }

        # Execute
        status = consent_service_with_mocks._reconstruct_consent_from_node(user_id, node)

        # Assert
        assert status.user_id == user_id
        assert status.stream == ConsentStream.TEMPORARY
        assert status.categories == []
        assert status.impact_score == 0.0
        assert status.attribution_count == 0

    @pytest.mark.asyncio
    async def test_load_consent_from_graph_success(
        self, consent_service_with_mocks, mock_time_service, sample_consent_node_temporary
    ):
        """Test _load_consent_from_graph loads and caches consent."""
        # Setup: mock get_graph_node to return our sample node
        with patch(
            "ciris_engine.logic.services.governance.consent.service.get_graph_node",
            return_value=sample_consent_node_temporary,
        ):
            # Execute
            status = await consent_service_with_mocks._load_consent_from_graph("temp_user_123")

            # Assert
            assert status.user_id == "temp_user_123"
            assert status.stream == ConsentStream.TEMPORARY
            # Verify cached
            assert "temp_user_123" in consent_service_with_mocks._consent_cache

    @pytest.mark.asyncio
    async def test_load_consent_from_graph_not_found(self, consent_service_with_mocks):
        """Test _load_consent_from_graph raises when node not found."""
        # Setup: mock get_graph_node to return None
        with patch(
            "ciris_engine.logic.services.governance.consent.service.get_graph_node", return_value=None
        ):
            # Execute & Assert
            with pytest.raises(ConsentNotFoundError, match="No consent found"):
                await consent_service_with_mocks._load_consent_from_graph("nonexistent_user")

    @pytest.mark.asyncio
    async def test_load_consent_from_graph_expired(
        self, consent_service_with_mocks, sample_consent_node_expired
    ):
        """Test _load_consent_from_graph raises for expired consent."""
        # Setup: mock get_graph_node to return expired node
        with patch(
            "ciris_engine.logic.services.governance.consent.service.get_graph_node",
            return_value=sample_consent_node_expired,
        ):
            # Execute & Assert
            with pytest.raises(ConsentNotFoundError, match="has expired"):
                await consent_service_with_mocks._load_consent_from_graph("expired_user_001")

    def test_extract_air_metrics_with_valid_data(self, consent_service_with_mocks):
        """Test _extract_air_metrics extracts metrics correctly."""
        # Setup
        air_metrics = {
            "total_interactions": 150,
            "reminders_sent": 3,
            "one_on_one_ratio": 0.65,
        }

        # Execute
        extracted = consent_service_with_mocks._extract_air_metrics(air_metrics)

        # Assert
        assert extracted["consent_air_total_interactions"] == 150.0
        assert extracted["consent_air_reminders_sent"] == 3.0
        assert isinstance(extracted["consent_air_total_interactions"], float)

    def test_extract_air_metrics_with_missing_fields(self, consent_service_with_mocks):
        """Test _extract_air_metrics handles missing fields."""
        # Setup
        air_metrics = {}

        # Execute
        extracted = consent_service_with_mocks._extract_air_metrics(air_metrics)

        # Assert: should use defaults
        assert extracted["consent_air_total_interactions"] == 0.0
        assert extracted["consent_air_reminders_sent"] == 0.0

    def test_extract_air_metrics_with_invalid_types(self, consent_service_with_mocks):
        """Test _extract_air_metrics handles invalid types gracefully."""
        # Setup
        air_metrics = {
            "total_interactions": "not_a_number",
            "reminders_sent": None,
        }

        # Execute
        extracted = consent_service_with_mocks._extract_air_metrics(air_metrics)

        # Assert: should default to 0.0 for invalid types
        assert extracted["consent_air_total_interactions"] == 0.0
        assert extracted["consent_air_reminders_sent"] == 0.0

    def test_extract_air_metrics_with_float_values(self, consent_service_with_mocks):
        """Test _extract_air_metrics converts float values correctly."""
        # Setup
        air_metrics = {
            "total_interactions": 150.7,
            "reminders_sent": 3.2,
        }

        # Execute
        extracted = consent_service_with_mocks._extract_air_metrics(air_metrics)

        # Assert
        assert extracted["consent_air_total_interactions"] == 150.7
        assert extracted["consent_air_reminders_sent"] == 3.2
