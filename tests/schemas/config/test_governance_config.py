"""
Tests for governance service configuration models.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.schemas.config.governance_config import (
    AdaptiveFilterConfig,
    ConsentConfig,
    GovernanceConfig,
    SelfObservationConfig,
    VisibilityConfig,
)


class TestAdaptiveFilterConfig:
    """Tests for AdaptiveFilterConfig model."""

    def test_minimal_config(self):
        """AdaptiveFilterConfig is minimal with no required fields."""
        config = AdaptiveFilterConfig()
        assert config is not None


class TestSelfObservationConfig:
    """Tests for SelfObservationConfig model."""

    def test_default_values(self):
        """SelfObservationConfig uses sensible defaults."""
        config = SelfObservationConfig()

        assert config.variance_threshold == 0.15
        assert config.observation_interval_hours == 24

    def test_validates_threshold_range(self):
        """SelfObservationConfig validates variance_threshold is 0.0-1.0."""
        # Valid thresholds
        SelfObservationConfig(variance_threshold=0.0)
        SelfObservationConfig(variance_threshold=0.5)
        SelfObservationConfig(variance_threshold=1.0)

        # Invalid thresholds - Pydantic's built-in validation
        with pytest.raises(Exception):  # ValidationError from pydantic
            SelfObservationConfig(variance_threshold=-0.1)

        with pytest.raises(Exception):  # ValidationError from pydantic
            SelfObservationConfig(variance_threshold=1.1)


class TestVisibilityConfig:
    """Tests for VisibilityConfig model."""

    def test_from_essential_config_loads_db_path(self):
        """VisibilityConfig.from_essential_config() loads db path correctly."""
        essential_config = MagicMock()

        with patch("ciris_engine.logic.config.db_paths.get_sqlite_db_full_path") as mock_path:
            mock_path.return_value = "/app/data/ciris_engine.db"

            config = VisibilityConfig.from_essential_config(essential_config)

        mock_path.assert_called_once_with(essential_config)
        assert config.db_path == Path("/app/data/ciris_engine.db")


class TestConsentConfig:
    """Tests for ConsentConfig model."""

    def test_from_essential_config_loads_db_path(self):
        """ConsentConfig.from_essential_config() loads db path correctly."""
        essential_config = MagicMock()

        with patch("ciris_engine.logic.config.db_paths.get_sqlite_db_full_path") as mock_path:
            mock_path.return_value = "/app/data/ciris_engine.db"

            config = ConsentConfig.from_essential_config(essential_config)

        mock_path.assert_called_once_with(essential_config)
        assert config.db_path == Path("/app/data/ciris_engine.db")


class TestGovernanceConfig:
    """Tests for complete GovernanceConfig."""

    def test_from_essential_config_creates_complete_config(self):
        """GovernanceConfig.from_essential_config() creates complete configuration."""
        essential_config = MagicMock()

        with patch("ciris_engine.logic.config.db_paths.get_sqlite_db_full_path") as mock_db:
            mock_db.return_value = "/app/data/ciris_engine.db"

            config = GovernanceConfig.from_essential_config(essential_config)

        assert isinstance(config.adaptive_filter, AdaptiveFilterConfig)
        assert isinstance(config.self_observation, SelfObservationConfig)
        assert isinstance(config.visibility, VisibilityConfig)
        assert isinstance(config.consent, ConsentConfig)
        # Both share the same database
        assert config.visibility.db_path == Path("/app/data/ciris_engine.db")
        assert config.consent.db_path == Path("/app/data/ciris_engine.db")
