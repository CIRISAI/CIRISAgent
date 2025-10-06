"""
Base Infrastructure Service - Extends BaseService for system-level services.
"""

from typing import Dict

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.services.metadata import ServiceMetadata


class BaseInfrastructureService(BaseService):
    """
    Base class for infrastructure services.

    Infrastructure services are critical system-level services that:
    - Provide core functionality (time, auth, resource monitoring)
    - Have high availability requirements
    - Are marked as critical in metadata

    Subclasses should override get_service_type() to return the
    appropriate ServiceType enum value.
    """

    def get_service_type(self) -> ServiceType:
        """Infrastructure services can be various types.

        Subclasses should override to return specific type like:
        - ServiceType.TIME for time services
        - ServiceType.SHUTDOWN for shutdown services
        - ServiceType.INITIALIZATION for init services
        - ServiceType.VISIBILITY for visibility services

        Default returns TIME as a common infrastructure type.
        """
        return ServiceType.TIME

    def _get_metadata(self) -> ServiceMetadata:
        """
        Get infrastructure service metadata.

        Returns ServiceMetadata for type safety, with infrastructure-specific
        attributes added.
        """
        base_metadata = super()._get_metadata()
        # Use model_copy to create a mutable copy and update it
        updated_metadata = base_metadata.model_copy(update={"category": "infrastructure", "critical": True})
        return updated_metadata

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """
        Collect infrastructure-specific metrics.

        Adds availability metric based on uptime.
        """
        metrics = super()._collect_custom_metrics()

        # Calculate availability (simplified - just based on uptime)
        uptime = self._calculate_uptime()
        if uptime > 0:
            # Simple availability: 1.0 if up for more than 60 seconds
            availability = min(1.0, uptime / 60.0)
        else:
            availability = 0.0

        metrics.update({"availability": availability})

        return metrics
