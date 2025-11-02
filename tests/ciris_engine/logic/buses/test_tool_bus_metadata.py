"""
Tests for ToolBus metadata discovery system.

Focuses on:
- get_tools_by_metadata() for data source discovery
- get_service_metadata() protocol implementation
- DSAR coordination use cases
- Data governance filtering
"""

from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.buses.tool_bus import ToolBus


class MockToolService:
    """Mock tool service with configurable metadata."""

    def __init__(self, metadata=None):
        self._metadata = metadata or {}
        self.name = "mock_tool"

    def get_service_metadata(self):
        """Return configured metadata."""
        return self._metadata

    async def execute_tool(self, tool_name, parameters):
        """Mock tool execution."""
        return {"status": "ok"}

    async def list_tools(self):
        """Mock tool listing."""
        return ["mock_tool_query"]

    async def get_tool_schema(self, tool_name):
        """Mock schema."""
        return None

    async def get_available_tools(self):
        """Mock available tools."""
        return ["mock_tool_query"]

    async def get_tool_info(self, tool_name):
        """Mock tool info."""
        return None

    async def get_all_tool_info(self):
        """Mock all tool info."""
        return []

    async def validate_parameters(self, tool_name, parameters):
        """Mock parameter validation."""
        return True

    async def get_tool_result(self, correlation_id, timeout=30.0):
        """Mock result retrieval."""
        return None


@pytest.fixture
def sql_data_source():
    """Create SQL data source tool service."""
    return MockToolService(
        metadata={
            "data_source": True,
            "data_source_type": "sql",
            "contains_pii": True,
            "gdpr_applicable": True,
            "connector_id": "production_db",
            "dialect": "postgresql",
        }
    )


@pytest.fixture
def rest_data_source():
    """Create REST API data source tool service."""
    return MockToolService(
        metadata={
            "data_source": True,
            "data_source_type": "rest",
            "contains_pii": True,
            "gdpr_applicable": True,
            "connector_id": "stripe_api",
            "api_provider": "Stripe",
        }
    )


@pytest.fixture
def utility_tool():
    """Create utility tool (not a data source)."""
    return MockToolService(
        metadata={
            "data_source": False,
            "contains_pii": False,
            "gdpr_applicable": False,
        }
    )


@pytest.fixture
def no_metadata_tool():
    """Create tool with no metadata."""
    return MockToolService(metadata={})


@pytest.fixture
def mock_service_registry():
    """Create mock service registry."""
    from unittest.mock import Mock

    from ciris_engine.schemas.runtime.enums import ServiceType

    mock_registry = Mock()
    # Initialize _services dict to return empty list for TOOL services
    # This will be overridden by the tool_bus_with_services fixture
    mock_registry._services = {ServiceType.TOOL: []}
    return mock_registry


@pytest.fixture
def mock_time_service():
    """Create mock time service."""
    from datetime import datetime, timezone
    from unittest.mock import Mock

    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

    mock = Mock(spec=TimeServiceProtocol)
    mock.now.return_value = datetime(2025, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
    return mock


@pytest.fixture
def tool_bus_with_services(
    sql_data_source, rest_data_source, utility_tool, no_metadata_tool, mock_service_registry, mock_time_service
):
    """Create ToolBus with various tool services."""
    from unittest.mock import Mock

    from ciris_engine.schemas.runtime.enums import ServiceType

    bus = ToolBus(mock_service_registry, mock_time_service)

    # Create provider wrappers with .instance attribute
    # to match ServiceRegistry structure
    providers = []
    for service in [sql_data_source, rest_data_source, utility_tool, no_metadata_tool]:
        provider = Mock()
        provider.instance = service
        providers.append(provider)

    # Set up service registry with proper structure
    mock_service_registry._services = {ServiceType.TOOL: providers}

    return bus


class TestGetToolsByMetadata:
    """Test get_tools_by_metadata() filtering."""

    def test_get_all_data_sources(self, tool_bus_with_services, sql_data_source, rest_data_source):
        """Test getting all data sources."""
        # Execute
        data_sources = tool_bus_with_services.get_tools_by_metadata({"data_source": True})

        # Verify only data sources returned
        assert len(data_sources) == 2
        assert sql_data_source in data_sources
        assert rest_data_source in data_sources

    def test_get_sql_data_sources_only(self, tool_bus_with_services, sql_data_source):
        """Test getting only SQL data sources."""
        # Execute
        sql_sources = tool_bus_with_services.get_tools_by_metadata(
            {
                "data_source": True,
                "data_source_type": "sql",
            }
        )

        # Verify only SQL source returned
        assert len(sql_sources) == 1
        assert sql_sources[0] == sql_data_source
        assert sql_sources[0].get_service_metadata()["dialect"] == "postgresql"

    def test_get_rest_data_sources_only(self, tool_bus_with_services, rest_data_source):
        """Test getting only REST data sources."""
        # Execute
        rest_sources = tool_bus_with_services.get_tools_by_metadata(
            {
                "data_source": True,
                "data_source_type": "rest",
            }
        )

        # Verify only REST source returned
        assert len(rest_sources) == 1
        assert rest_sources[0] == rest_data_source
        assert rest_sources[0].get_service_metadata()["api_provider"] == "Stripe"

    def test_get_gdpr_applicable_sources(self, tool_bus_with_services):
        """Test getting GDPR-applicable sources."""
        # Execute
        gdpr_sources = tool_bus_with_services.get_tools_by_metadata({"gdpr_applicable": True})

        # Verify both data sources returned
        assert len(gdpr_sources) == 2

    def test_get_pii_containing_sources(self, tool_bus_with_services):
        """Test getting PII-containing sources."""
        # Execute
        pii_sources = tool_bus_with_services.get_tools_by_metadata({"contains_pii": True})

        # Verify both data sources returned
        assert len(pii_sources) == 2

    def test_get_non_data_sources(self, tool_bus_with_services, utility_tool, no_metadata_tool):
        """Test getting non-data sources."""
        # Execute
        non_sources = tool_bus_with_services.get_tools_by_metadata({"data_source": False})

        # Verify utility tool returned
        assert len(non_sources) == 1
        assert utility_tool in non_sources

    def test_no_matches(self, tool_bus_with_services):
        """Test query with no matches."""
        # Execute
        results = tool_bus_with_services.get_tools_by_metadata(
            {
                "data_source": True,
                "data_source_type": "hl7",  # No HL7 sources
            }
        )

        # Verify empty result
        assert len(results) == 0

    def test_multiple_criteria(self, tool_bus_with_services, sql_data_source):
        """Test filtering with multiple criteria."""
        # Execute
        results = tool_bus_with_services.get_tools_by_metadata(
            {
                "data_source": True,
                "data_source_type": "sql",
                "gdpr_applicable": True,
                "contains_pii": True,
            }
        )

        # Verify SQL source matches all criteria
        assert len(results) == 1
        assert results[0] == sql_data_source

    def test_empty_filter(self, tool_bus_with_services):
        """Test empty filter returns all tools."""
        # Execute
        results = tool_bus_with_services.get_tools_by_metadata({})

        # Verify all tools returned
        assert len(results) == 4


class TestGetServiceMetadata:
    """Test get_service_metadata() protocol implementation."""

    def test_sql_service_metadata(self, sql_data_source):
        """Test SQL service returns correct metadata."""
        metadata = sql_data_source.get_service_metadata()

        assert metadata["data_source"] is True
        assert metadata["data_source_type"] == "sql"
        assert metadata["contains_pii"] is True
        assert metadata["gdpr_applicable"] is True
        assert metadata["connector_id"] == "production_db"
        assert metadata["dialect"] == "postgresql"

    def test_rest_service_metadata(self, rest_data_source):
        """Test REST service returns correct metadata."""
        metadata = rest_data_source.get_service_metadata()

        assert metadata["data_source"] is True
        assert metadata["data_source_type"] == "rest"
        assert metadata["contains_pii"] is True
        assert metadata["gdpr_applicable"] is True
        assert metadata["connector_id"] == "stripe_api"
        assert metadata["api_provider"] == "Stripe"

    def test_utility_service_metadata(self, utility_tool):
        """Test utility service returns non-data-source metadata."""
        metadata = utility_tool.get_service_metadata()

        assert metadata["data_source"] is False
        assert metadata["contains_pii"] is False
        assert metadata["gdpr_applicable"] is False

    def test_default_empty_metadata(self, no_metadata_tool):
        """Test default implementation returns empty dict."""
        metadata = no_metadata_tool.get_service_metadata()

        assert metadata == {}


class TestDSARCoordinationUseCases:
    """Test DSAR coordination use cases."""

    def test_discover_all_data_sources_for_dsar(self, tool_bus_with_services):
        """Test discovering all data sources for DSAR request."""
        # This is what DSAROrchestrator would do
        data_sources = tool_bus_with_services.get_tools_by_metadata({"data_source": True})

        # Verify can iterate over sources
        connector_ids = [service.get_service_metadata()["connector_id"] for service in data_sources]

        assert "production_db" in connector_ids
        assert "stripe_api" in connector_ids
        assert len(connector_ids) == 2

    def test_discover_sql_sources_for_user_export(self, tool_bus_with_services):
        """Test discovering SQL sources for user data export."""
        # DSAROrchestrator needs SQL sources
        sql_sources = tool_bus_with_services.get_tools_by_metadata(
            {
                "data_source": True,
                "data_source_type": "sql",
            }
        )

        # Verify SQL sources found
        assert len(sql_sources) == 1

        # Verify can extract connector info
        for service in sql_sources:
            metadata = service.get_service_metadata()
            assert metadata["data_source_type"] == "sql"
            assert "connector_id" in metadata
            assert "dialect" in metadata

    def test_discover_gdpr_sources_for_deletion(self, tool_bus_with_services):
        """Test discovering GDPR-applicable sources for deletion."""
        # GDPR deletion must cover all GDPR sources
        gdpr_sources = tool_bus_with_services.get_tools_by_metadata({"gdpr_applicable": True})

        # Verify GDPR sources found
        assert len(gdpr_sources) == 2

        # Verify all are data sources
        for service in gdpr_sources:
            metadata = service.get_service_metadata()
            assert metadata["data_source"] is True
            assert metadata["gdpr_applicable"] is True


class TestDataGovernanceUseCases:
    """Test data governance use cases."""

    def test_identify_pii_sources(self, tool_bus_with_services):
        """Test identifying sources containing PII."""
        # WiseAuthority needs to know which tools access PII
        pii_sources = tool_bus_with_services.get_tools_by_metadata({"contains_pii": True})

        # Verify PII sources identified
        assert len(pii_sources) == 2

        # Verify can apply stricter approval
        for service in pii_sources:
            metadata = service.get_service_metadata()
            assert metadata["contains_pii"] is True
            # WiseAuthority would require elevated approval here

    def test_filter_by_connector_type(self, tool_bus_with_services):
        """Test filtering by specific connector type."""
        # Find all SQL connectors
        sql_connectors = tool_bus_with_services.get_tools_by_metadata(
            {
                "data_source_type": "sql",
            }
        )

        assert len(sql_connectors) == 1
        assert sql_connectors[0].get_service_metadata()["connector_id"] == "production_db"

        # Find all REST connectors
        rest_connectors = tool_bus_with_services.get_tools_by_metadata(
            {
                "data_source_type": "rest",
            }
        )

        assert len(rest_connectors) == 1
        assert rest_connectors[0].get_service_metadata()["connector_id"] == "stripe_api"


class TestBackwardCompatibility:
    """Test backward compatibility with existing ToolBus."""

    def test_existing_tools_unaffected(self, mock_service_registry, mock_time_service):
        """Test tools without metadata still work."""
        from unittest.mock import Mock

        from ciris_engine.schemas.runtime.enums import ServiceType

        # Create ToolBus
        bus = ToolBus(mock_service_registry, mock_time_service)

        # Add tool without metadata
        no_metadata_tool = MockToolService(metadata={})

        # Create provider wrapper
        provider = Mock()
        provider.instance = no_metadata_tool

        # Set up service registry
        mock_service_registry._services = {ServiceType.TOOL: [provider]}

        # Should still work
        results = bus.get_tools_by_metadata({"data_source": True})
        assert len(results) == 0  # No match, but no error

    def test_metadata_optional(self, mock_service_registry, mock_time_service):
        """Test get_service_metadata() is optional."""
        from unittest.mock import Mock

        from ciris_engine.schemas.runtime.enums import ServiceType

        # Create ToolBus
        bus = ToolBus(mock_service_registry, mock_time_service)

        # Add tool that returns empty metadata
        tool = MockToolService(metadata={})

        # Create provider wrapper
        provider = Mock()
        provider.instance = tool

        # Set up service registry
        mock_service_registry._services = {ServiceType.TOOL: [provider]}

        # Should handle gracefully
        results = bus.get_tools_by_metadata({"data_source": True})
        assert len(results) == 0


class TestMetadataExtensibility:
    """Test metadata system is extensible."""

    def test_custom_metadata_fields(self, mock_service_registry, mock_time_service):
        """Test adding custom metadata fields."""
        from unittest.mock import Mock

        from ciris_engine.schemas.runtime.enums import ServiceType

        # Create tool with custom fields
        custom_tool = MockToolService(
            metadata={
                "data_source": True,
                "data_source_type": "custom",
                "custom_field_1": "value1",
                "custom_field_2": 42,
                "custom_field_3": ["list", "of", "values"],
            }
        )

        # Create bus
        bus = ToolBus(mock_service_registry, mock_time_service)

        # Create provider wrapper
        provider = Mock()
        provider.instance = custom_tool

        # Set up service registry
        mock_service_registry._services = {ServiceType.TOOL: [provider]}

        # Should be able to filter by custom fields
        results = bus.get_tools_by_metadata({"custom_field_1": "value1"})
        assert len(results) == 1

        results = bus.get_tools_by_metadata({"custom_field_2": 42})
        assert len(results) == 1

    def test_future_metadata_fields(self, mock_service_registry, mock_time_service):
        """Test adding future metadata fields doesn't break existing code."""
        from unittest.mock import Mock

        from ciris_engine.schemas.runtime.enums import ServiceType

        # Create tool with future fields
        future_tool = MockToolService(
            metadata={
                "data_source": True,
                "data_source_type": "hl7",
                "contains_pii": True,
                "gdpr_applicable": True,
                # Future fields
                "hipaa_applicable": True,
                "data_retention_days": 2555,
                "encryption_at_rest": True,
                "geographic_location": "EU",
            }
        )

        # Create bus
        bus = ToolBus(mock_service_registry, mock_time_service)

        # Create provider wrapper
        provider = Mock()
        provider.instance = future_tool

        # Set up service registry
        mock_service_registry._services = {ServiceType.TOOL: [provider]}

        # Should still work with existing filters
        results = bus.get_tools_by_metadata({"data_source": True})
        assert len(results) == 1

        # Should work with new filters
        results = bus.get_tools_by_metadata({"hipaa_applicable": True})
        assert len(results) == 1
