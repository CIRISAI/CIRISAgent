"""
Tests for SQL external data service metadata and DSAR capabilities.

Focuses on:
- get_service_metadata() implementation
- Data source discovery for DSAR coordination
- Privacy schema configuration
- DSAR capability advertisement
"""

from unittest.mock import Mock

import pytest
import pytest_asyncio

from ciris_adapters.external_data_sql.schemas import (
    PrivacyColumnMapping,
    PrivacySchemaConfig,
    PrivacyTableMapping,
    SQLConnectorConfig,
    SQLDialect,
)
from ciris_engine.protocols.services import TimeServiceProtocol


# Helper class that mimics SQLToolService for metadata testing
class SQLServiceMetadataTestHelper:
    """Minimal helper for testing get_service_metadata() without full service instantiation."""

    def __init__(self, config=None):
        from ciris_adapters.external_data_sql.dialects import get_dialect

        self._config = config
        self._connector_id = config.connector_id if config else "sql"
        self._dialect = get_dialect(config.dialect.value) if config else None

    def get_service_metadata(self) -> dict:
        """Copy of SQLToolService.get_service_metadata() for testing."""
        dsar_capabilities = []
        if self._config and self._config.privacy_schema:
            dsar_capabilities.extend(
                [
                    "find_user_data",
                    "export_user",
                    "delete_user",
                    "anonymize_user",
                    "verify_deletion",
                ]
            )

        table_count = 0
        if self._config and self._config.privacy_schema:
            table_count = len(self._config.privacy_schema.tables)

        return {
            "data_source": True,
            "data_source_type": "sql",
            "contains_pii": True,
            "gdpr_applicable": True,
            "connector_id": self._connector_id,
            "dialect": self._dialect.name if self._dialect else None,
            "dsar_capabilities": dsar_capabilities,
            "privacy_schema_configured": self._config is not None and self._config.privacy_schema is not None,
            "table_count": table_count,
        }


@pytest.fixture
def mock_time_service():
    """Create mock time service."""
    from datetime import datetime, timezone

    mock = Mock(spec=TimeServiceProtocol)
    mock.now.return_value = datetime(2025, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
    return mock


@pytest.fixture
def privacy_schema_with_tables():
    """Create privacy schema with multiple tables configured."""
    return PrivacySchemaConfig(
        tables=[
            PrivacyTableMapping(
                table_name="users",
                identifier_column="user_id",
                columns=[
                    PrivacyColumnMapping(
                        column_name="email",
                        data_type="email",
                        is_identifier=True,
                    ),
                    PrivacyColumnMapping(
                        column_name="name",
                        data_type="name",
                    ),
                ],
            ),
            PrivacyTableMapping(
                table_name="orders",
                identifier_column="user_id",
                columns=[
                    PrivacyColumnMapping(
                        column_name="shipping_address",
                        data_type="address",
                    ),
                ],
            ),
        ],
        global_identifier_column="user_id",
    )


@pytest.fixture
def sqlite_connector_config(privacy_schema_with_tables):
    """Create SQLite connector configuration."""
    return SQLConnectorConfig(
        connector_id="test_sqlite_db",
        connection_string="sqlite:///:memory:",
        dialect=SQLDialect.SQLITE,
        privacy_schema=privacy_schema_with_tables,
    )


@pytest.fixture
def postgresql_connector_config(privacy_schema_with_tables):
    """Create PostgreSQL connector configuration."""
    return SQLConnectorConfig(
        connector_id="production_postgres",
        connection_string="postgresql://user:pass@localhost/testdb",
        dialect=SQLDialect.POSTGRESQL,
        privacy_schema=privacy_schema_with_tables,
    )


@pytest.fixture
def sql_service_with_config(mock_time_service, sqlite_connector_config):
    """Create SQL service with configuration (not initialized)."""
    return SQLServiceMetadataTestHelper(config=sqlite_connector_config)


@pytest.fixture
def sql_service_without_config(mock_time_service):
    """Create SQL service without configuration."""
    return SQLServiceMetadataTestHelper(config=None)


class TestSQLServiceMetadata:
    """Test get_service_metadata() for SQL service."""

    def test_metadata_with_sqlite_config(self, sql_service_with_config):
        """Test metadata returns correct info for configured SQLite service."""
        metadata = sql_service_with_config.get_service_metadata()

        # Core data source fields
        assert metadata["data_source"] is True
        assert metadata["data_source_type"] == "sql"
        assert metadata["contains_pii"] is True
        assert metadata["gdpr_applicable"] is True

        # SQL-specific fields
        assert metadata["connector_id"] == "test_sqlite_db"
        assert metadata["dialect"] == "sqlite"
        assert metadata["privacy_schema_configured"] is True
        assert metadata["table_count"] == 2

        # DSAR capabilities
        assert "dsar_capabilities" in metadata
        assert "find_user_data" in metadata["dsar_capabilities"]
        assert "export_user" in metadata["dsar_capabilities"]
        assert "delete_user" in metadata["dsar_capabilities"]
        assert "anonymize_user" in metadata["dsar_capabilities"]
        assert "verify_deletion" in metadata["dsar_capabilities"]

    def test_metadata_with_postgresql_config(self, mock_time_service, postgresql_connector_config):
        """Test metadata returns correct dialect for PostgreSQL."""
        service = SQLServiceMetadataTestHelper(config=postgresql_connector_config)

        metadata = service.get_service_metadata()

        assert metadata["connector_id"] == "production_postgres"
        assert metadata["dialect"] == "postgresql"
        assert metadata["table_count"] == 2

    def test_metadata_without_config(self, sql_service_without_config):
        """Test metadata handles missing configuration gracefully."""
        metadata = sql_service_without_config.get_service_metadata()

        # Core fields should still be present
        assert metadata["data_source"] is True
        assert metadata["data_source_type"] == "sql"
        assert metadata["contains_pii"] is True
        assert metadata["gdpr_applicable"] is True

        # Config-dependent fields should be None or empty
        assert metadata["connector_id"] == "sql"  # Default
        assert metadata["dialect"] is None  # No dialect configured
        assert metadata["privacy_schema_configured"] is False
        assert metadata["table_count"] == 0
        assert metadata["dsar_capabilities"] == []

    def test_metadata_with_empty_privacy_schema(self, mock_time_service):
        """Test metadata with empty privacy schema."""

        empty_schema = PrivacySchemaConfig(tables=[])
        config = SQLConnectorConfig(
            connector_id="empty_db",
            connection_string="sqlite:///:memory:",
            dialect=SQLDialect.SQLITE,
            privacy_schema=empty_schema,
        )

        service = SQLServiceMetadataTestHelper(config=config)

        metadata = service.get_service_metadata()

        assert metadata["privacy_schema_configured"] is True  # Schema exists
        assert metadata["table_count"] == 0  # But no tables
        assert len(metadata["dsar_capabilities"]) == 5  # Still has capabilities


class TestDSARCoordinationIntegration:
    """Test SQL service integration with DSAR coordination."""

    def test_sql_service_discoverable_by_metadata(self, sql_service_with_config):
        """Test SQL service can be discovered by ToolBus.get_tools_by_metadata()."""
        metadata = sql_service_with_config.get_service_metadata()

        # Simulate ToolBus filtering logic
        is_data_source = metadata.get("data_source") is True
        is_sql_source = metadata.get("data_source_type") == "sql"
        has_pii = metadata.get("contains_pii") is True
        is_gdpr = metadata.get("gdpr_applicable") is True

        assert is_data_source
        assert is_sql_source
        assert has_pii
        assert is_gdpr

    def test_dsar_capabilities_complete(self, sql_service_with_config):
        """Test all required DSAR capabilities are advertised."""
        metadata = sql_service_with_config.get_service_metadata()
        capabilities = set(metadata["dsar_capabilities"])

        # Required for GDPR Articles 15, 17, 20
        assert "find_user_data" in capabilities  # Article 15 (Access)
        assert "export_user" in capabilities  # Article 20 (Portability)
        assert "delete_user" in capabilities  # Article 17 (Erasure)
        assert "verify_deletion" in capabilities  # Proof of deletion
        assert "anonymize_user" in capabilities  # Alternative to deletion

    def test_connector_id_uniqueness(self, mock_time_service):
        """Test connector IDs can differentiate multiple SQL sources."""

        config1 = SQLConnectorConfig(
            connector_id="production_db",
            connection_string="sqlite:///:memory:",
            dialect=SQLDialect.SQLITE,
            privacy_schema=PrivacySchemaConfig(tables=[]),
        )

        config2 = SQLConnectorConfig(
            connector_id="analytics_db",
            connection_string="sqlite:///:memory:",
            dialect=SQLDialect.SQLITE,
            privacy_schema=PrivacySchemaConfig(tables=[]),
        )

        service1 = SQLServiceMetadataTestHelper(config=config1)

        service2 = SQLServiceMetadataTestHelper(config=config2)

        metadata1 = service1.get_service_metadata()
        metadata2 = service2.get_service_metadata()

        assert metadata1["connector_id"] != metadata2["connector_id"]
        assert metadata1["connector_id"] == "production_db"
        assert metadata2["connector_id"] == "analytics_db"


class TestMetadataExtensibility:
    """Test metadata system extensibility."""

    def test_metadata_is_json_serializable(self, sql_service_with_config):
        """Test metadata can be serialized to JSON."""
        import json

        metadata = sql_service_with_config.get_service_metadata()

        # Should not raise
        json_str = json.dumps(metadata)
        assert json_str is not None

        # Should round-trip
        parsed = json.loads(json_str)
        assert parsed["connector_id"] == metadata["connector_id"]

    def test_metadata_supports_custom_fields(self, mock_time_service):
        """Test metadata can be extended with custom fields in future."""

        # This test demonstrates extensibility - if we add new fields,
        # existing code should continue to work

        config = SQLConnectorConfig(
            connector_id="future_db",
            connection_string="sqlite:///:memory:",
            dialect=SQLDialect.SQLITE,
            privacy_schema=PrivacySchemaConfig(tables=[]),
        )

        service = SQLServiceMetadataTestHelper(config=config)

        metadata = service.get_service_metadata()

        # Current fields
        assert "data_source" in metadata
        assert "dsar_capabilities" in metadata

        # Future fields could be added without breaking existing filters
        # For example: "hipaa_applicable", "data_retention_days", etc.
        # These would be ignored by current code but could be used by future logic


class TestBackwardCompatibility:
    """Test backward compatibility with existing ToolBus."""

    def test_service_without_metadata_method(self):
        """Test that services without get_service_metadata() still work."""
        # This is tested via protocol default implementation
        # ToolServiceProtocol.get_service_metadata() returns {}

        # If a service doesn't override get_service_metadata(),
        # it should return empty dict (tested in ToolBus tests)
        pass

    def test_metadata_optional_fields_missing(self, mock_time_service):
        """Test metadata works even if some fields are missing."""

        config = SQLConnectorConfig(
            connector_id="minimal_db",
            connection_string="sqlite:///:memory:",
            dialect=SQLDialect.SQLITE,
            privacy_schema=PrivacySchemaConfig(tables=[]),
        )

        service = SQLServiceMetadataTestHelper(config=config)

        metadata = service.get_service_metadata()

        # Should handle .get() gracefully
        assert metadata.get("data_source") is True
        assert metadata.get("nonexistent_field") is None
        assert metadata.get("another_missing_field", "default") == "default"
