"""Tests for RegistryAwareServiceProtocol."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.services.governance.self_observation.service import SelfObservationService
from ciris_engine.logic.services.graph.audit_service.service import GraphAuditService
from ciris_engine.logic.services.graph.telemetry_service.service import GraphTelemetryService
from ciris_engine.logic.services.graph.tsdb_consolidation.service import TSDBConsolidationService
from ciris_engine.protocols.infrastructure.base import RegistryAwareServiceProtocol, ServiceRegistryProtocol


class TestRegistryAwareProtocol:
    """Test RegistryAwareServiceProtocol implementation."""

    def test_protocol_exists(self):
        """Verify RegistryAwareServiceProtocol is defined."""
        assert hasattr(RegistryAwareServiceProtocol, "attach_registry")

    def test_telemetry_service_implements_protocol(self):
        """Verify GraphTelemetryService implements RegistryAwareServiceProtocol."""
        service = GraphTelemetryService()
        assert isinstance(service, RegistryAwareServiceProtocol)
        assert hasattr(service, "attach_registry")
        assert callable(service.attach_registry)

    def test_self_observation_service_implements_protocol(self):
        """Verify SelfObservationService implements RegistryAwareServiceProtocol."""
        service = SelfObservationService(time_service=MagicMock(), observation_interval_hours=6)
        assert isinstance(service, RegistryAwareServiceProtocol)
        assert hasattr(service, "attach_registry")
        assert callable(service.attach_registry)

    def test_audit_service_implements_protocol(self):
        """Verify GraphAuditService implements RegistryAwareServiceProtocol."""
        service = GraphAuditService(time_service=MagicMock(), enable_hash_chain=False)
        assert isinstance(service, RegistryAwareServiceProtocol)
        assert hasattr(service, "attach_registry")
        assert callable(service.attach_registry)

    def test_tsdb_consolidation_implements_protocol(self):
        """Verify TSDBConsolidationService implements RegistryAwareServiceProtocol."""
        service = TSDBConsolidationService(time_service=MagicMock(), consolidation_interval_hours=24)
        assert isinstance(service, RegistryAwareServiceProtocol)
        assert hasattr(service, "attach_registry")
        assert callable(service.attach_registry)

    @pytest.mark.asyncio
    async def test_telemetry_service_attach_registry_stores_registry(self):
        """Test that attach_registry stores the registry reference."""
        service = GraphTelemetryService()
        mock_registry = MagicMock(spec=ServiceRegistryProtocol)

        await service.attach_registry(mock_registry)

        assert service._service_registry is mock_registry

    @pytest.mark.asyncio
    async def test_self_observation_service_attach_registry_stores_registry(self):
        """Test that attach_registry stores the registry reference."""
        service = SelfObservationService(time_service=MagicMock(), observation_interval_hours=6)
        mock_registry = MagicMock(spec=ServiceRegistryProtocol)

        await service.attach_registry(mock_registry)

        assert service._service_registry is mock_registry

    @pytest.mark.asyncio
    async def test_audit_service_attach_registry_stores_registry(self):
        """Test that attach_registry stores the registry reference."""
        service = GraphAuditService(time_service=MagicMock(), enable_hash_chain=False)
        mock_registry = MagicMock(spec=ServiceRegistryProtocol)

        await service.attach_registry(mock_registry)

        assert service._service_registry is mock_registry

    @pytest.mark.asyncio
    async def test_attach_registry_handles_none_gracefully(self):
        """Test that attach_registry handles None registry (for testing)."""
        service = GraphTelemetryService()

        # Should not raise
        await service.attach_registry(None)  # type: ignore

        assert service._service_registry is None

    @pytest.mark.asyncio
    async def test_attach_registry_is_async(self):
        """Verify attach_registry is properly async."""
        service = GraphTelemetryService()
        mock_registry = MagicMock(spec=ServiceRegistryProtocol)

        # Should return a coroutine
        result = service.attach_registry(mock_registry)
        assert hasattr(result, "__await__")

        # Await it
        await result


class TestProtocolDocumentation:
    """Test that protocol is well-documented."""

    def test_protocol_has_docstring(self):
        """Verify protocol has comprehensive docstring."""
        assert RegistryAwareServiceProtocol.__doc__ is not None
        assert len(RegistryAwareServiceProtocol.__doc__) > 100
        assert "constructor injection" in RegistryAwareServiceProtocol.__doc__.lower()

    def test_attach_registry_has_docstring(self):
        """Verify attach_registry method has docstring."""
        # Get the abstract method from protocol
        method = getattr(RegistryAwareServiceProtocol, "attach_registry")
        assert method.__doc__ is not None
        assert "registry" in method.__doc__.lower()


class TestProtocolIntegration:
    """Integration tests for protocol usage."""

    @pytest.mark.asyncio
    async def test_protocol_check_with_isinstance(self):
        """Test that isinstance check works as expected."""
        # Create services
        telemetry = GraphTelemetryService()
        audit = GraphAuditService(time_service=MagicMock(), enable_hash_chain=False)

        # Both should be instances of the protocol
        assert isinstance(telemetry, RegistryAwareServiceProtocol)
        assert isinstance(audit, RegistryAwareServiceProtocol)

        # Protocol check allows calling attach_registry
        mock_registry = MagicMock(spec=ServiceRegistryProtocol)

        if isinstance(telemetry, RegistryAwareServiceProtocol):
            await telemetry.attach_registry(mock_registry)

        if isinstance(audit, RegistryAwareServiceProtocol):
            await audit.attach_registry(mock_registry)

        assert telemetry._service_registry is mock_registry
        assert audit._service_registry is mock_registry

    @pytest.mark.asyncio
    async def test_service_initializer_pattern(self):
        """Test the pattern ServiceInitializer uses."""
        # Simulate ServiceInitializer pattern
        services = [
            GraphTelemetryService(),
            GraphAuditService(time_service=MagicMock(), enable_hash_chain=False),
            SelfObservationService(time_service=MagicMock(), observation_interval_hours=6),
        ]

        mock_registry = MagicMock(spec=ServiceRegistryProtocol)

        # Apply registry to all services that support it
        for service in services:
            if isinstance(service, RegistryAwareServiceProtocol):
                await service.attach_registry(mock_registry)

        # All services should have registry attached
        for service in services:
            assert service._service_registry is mock_registry
