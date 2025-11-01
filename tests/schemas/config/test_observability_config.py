"""
Tests for observability service configuration models.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.schemas.config.observability_config import (
    AuditConfig,
    ObservabilityConfig,
    TelemetryConfig,
    TSDBConfig,
)


class TestTelemetryConfig:
    """Tests for TelemetryConfig model."""

    def test_minimal_config(self):
        """TelemetryConfig is minimal with no required fields."""
        config = TelemetryConfig()
        assert config is not None


class TestAuditConfig:
    """Tests for AuditConfig model."""

    def test_from_essential_config_loads_all_paths(self):
        """AuditConfig.from_essential_config() loads all paths correctly."""
        essential_config = MagicMock()
        essential_config.audit.audit_log_path = Path("audit_logs.jsonl")
        essential_config.security.signing_key_path = Path(".ciris_keys/signing.pem")

        with patch("ciris_engine.logic.config.db_paths.get_audit_db_full_path") as mock_audit_path:
            mock_audit_path.return_value = "/app/data/audit.db"

            config = AuditConfig.from_essential_config(essential_config)

        assert config.export_path == Path("audit_logs.jsonl")
        assert config.export_format == "jsonl"
        assert config.enable_hash_chain is True
        assert config.db_path == Path("/app/data/audit.db")
        assert config.key_path == Path(".ciris_keys/signing.pem")
        assert config.retention_days == 90

    def test_default_values(self):
        """AuditConfig uses sensible defaults."""
        config = AuditConfig(
            export_path=Path("audit.jsonl"), db_path=Path("/data/audit.db"), key_path=Path(".keys/signing.pem")
        )

        assert config.export_format == "jsonl"
        assert config.enable_hash_chain is True
        assert config.retention_days == 90


class TestTSDBConfig:
    """Tests for TSDBConfig model."""

    def test_from_essential_config_respects_frozen_consolidation_interval(self):
        """TSDBConfig.from_essential_config() uses frozen 6-hour consolidation interval."""
        essential_config = MagicMock()

        config = TSDBConfig.from_essential_config(essential_config)

        assert config.consolidation_interval_hours == 6  # Frozen value
        assert config.raw_retention_hours == 72

    def test_default_values(self):
        """TSDBConfig uses sensible defaults."""
        config = TSDBConfig()

        assert config.consolidation_interval_hours == 6  # Frozen
        assert config.raw_retention_hours == 72


class TestObservabilityConfig:
    """Tests for complete ObservabilityConfig."""

    def test_from_essential_config_creates_complete_config(self):
        """ObservabilityConfig.from_essential_config() creates complete configuration."""
        essential_config = MagicMock()
        essential_config.audit.audit_log_path = Path("audit.jsonl")
        essential_config.security.signing_key_path = Path(".keys/signing.pem")

        with patch("ciris_engine.logic.config.db_paths.get_audit_db_full_path") as mock_audit:
            mock_audit.return_value = "/app/data/audit.db"

            config = ObservabilityConfig.from_essential_config(essential_config)

        assert isinstance(config.telemetry, TelemetryConfig)
        assert isinstance(config.audit, AuditConfig)
        assert isinstance(config.tsdb, TSDBConfig)
        assert config.audit.db_path == Path("/app/data/audit.db")
        assert config.tsdb.consolidation_interval_hours == 6
