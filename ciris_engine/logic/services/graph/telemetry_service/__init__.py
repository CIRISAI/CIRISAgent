"""Telemetry Service Module.

This module provides telemetry collection, aggregation, and storage services
for the CIRIS agent platform.

The module is organized into the following components:
- service.py: Main GraphTelemetryService class
- aggregator.py: TelemetryAggregator for enterprise telemetry collection
- storage.py: Storage helpers for different memory types
- helpers.py: Helper functions for telemetry calculations and queries
- exceptions.py: Custom exceptions for telemetry operations
"""

from .service import GraphTelemetryService

# Re-export TelemetryAggregator for backward compatibility
from .aggregator import (
    ConsolidationCandidate,
    GracePolicy,
    MemoryType,
    TelemetryAggregator,
)

__all__ = [
    "GraphTelemetryService",
    "TelemetryAggregator",
    "MemoryType",
    "GracePolicy",
    "ConsolidationCandidate",
]
