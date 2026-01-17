"""Tests for service_property_mixin.py module."""

import pytest
from unittest.mock import MagicMock, PropertyMock


class TestServicePropertyMixin:
    """Tests for the ServicePropertyMixin class."""

    def test_mixin_provides_service_properties(self) -> None:
        """Test that mixin provides service properties via service_initializer."""
        from ciris_engine.logic.runtime.service_property_mixin import ServicePropertyMixin

        class TestClass(ServicePropertyMixin):
            """Test class using the mixin."""

            def __init__(self) -> None:
                self.service_initializer = MagicMock()

        obj = TestClass()
        obj.service_initializer.memory_service = MagicMock()
        obj.service_initializer.llm_service = MagicMock()

        # Verify properties delegate to service_initializer
        assert obj.memory_service is obj.service_initializer.memory_service
        assert obj.llm_service is obj.service_initializer.llm_service

    def test_mixin_returns_none_when_no_initializer(self) -> None:
        """Test that mixin returns None when service_initializer is None."""
        from ciris_engine.logic.runtime.service_property_mixin import ServicePropertyMixin

        class TestClass(ServicePropertyMixin):
            """Test class using the mixin."""

            def __init__(self) -> None:
                self.service_initializer = None

        obj = TestClass()

        # Verify properties return None when initializer is missing
        assert obj.memory_service is None
        assert obj.llm_service is None
        assert obj.telemetry_service is None

    def test_all_service_properties_exist(self) -> None:
        """Test that all expected service properties are defined."""
        from ciris_engine.logic.runtime.service_property_mixin import ServicePropertyMixin

        expected_properties = [
            "service_registry",
            "bus_manager",
            "memory_service",
            "resource_monitor",
            "secrets_service",
            "wa_auth_system",
            "telemetry_service",
            "llm_service",
            "audit_service",
            "adaptive_filter_service",
            "config_manager",
            "secrets_tool_service",
            "time_service",
            "config_service",
            "task_scheduler",
            "authentication_service",
            "incident_management_service",
            "runtime_control_service",
            "maintenance_service",
            "database_maintenance_service",
            "shutdown_service",
            "initialization_service",
            "tsdb_consolidation_service",
            "self_observation_service",
            "visibility_service",
            "consent_service",
        ]

        for prop_name in expected_properties:
            assert hasattr(ServicePropertyMixin, prop_name), f"Missing property: {prop_name}"

    def test_database_maintenance_service_alias(self) -> None:
        """Test that database_maintenance_service is an alias for maintenance_service."""
        from ciris_engine.logic.runtime.service_property_mixin import ServicePropertyMixin

        class TestClass(ServicePropertyMixin):
            """Test class using the mixin."""

            def __init__(self) -> None:
                self.service_initializer = MagicMock()

        obj = TestClass()
        mock_service = MagicMock()
        obj.service_initializer.maintenance_service = mock_service

        # Both should return the same service
        assert obj.maintenance_service is mock_service
        assert obj.database_maintenance_service is mock_service
