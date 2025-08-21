#!/usr/bin/env python3
"""Debug script to investigate TimeService telemetry collection."""

import asyncio
import json
import sys
from datetime import datetime

# Add the project root to path
sys.path.insert(0, "/home/emoore/CIRISAgent")

from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.runtime.service_initializer import ServiceInitializer
from ciris_engine.logic.services.graph.telemetry_service import TelemetryAggregator
from ciris_engine.logic.services.lifecycle.time import TimeService


async def main():
    """Debug TimeService telemetry collection."""

    print("=== TimeService Telemetry Debug ===\n")

    # Create and start TimeService
    time_service = TimeService()
    print(f"1. Created TimeService: {time_service}")
    print(f"   Initial _start_time: {time_service._start_time}")
    print(f"   Initial _started: {time_service._started}")

    # Start the service
    await time_service.start()
    print(f"\n2. After start():")
    print(f"   _start_time: {time_service._start_time}")
    print(f"   _started: {time_service._started}")

    # Check get_status
    status = time_service.get_status()
    print(f"\n3. get_status() result:")
    print(f"   Healthy: {status.is_healthy}")
    print(f"   Uptime: {status.uptime_seconds}")
    print(f"   Service name: {status.service_name}")

    # Check get_metrics
    metrics = await time_service.get_metrics()
    print(f"\n4. get_metrics() result:")
    for key, value in sorted(metrics.items()):
        print(f"   {key}: {value}")

    # Check _collect_metrics
    base_metrics = time_service._collect_metrics()
    print(f"\n5. _collect_metrics() result:")
    for key, value in sorted(base_metrics.items()):
        print(f"   {key}: {value}")

    # Create ServiceInitializer to test integration
    print("\n=== ServiceInitializer Integration ===\n")
    initializer = ServiceInitializer()

    # Initialize infrastructure services
    await initializer.initialize_infrastructure_services()
    print(f"6. ServiceInitializer.time_service: {initializer.time_service}")
    print(f"   _started: {initializer.time_service._started if initializer.time_service else 'N/A'}")
    print(f"   _start_time: {initializer.time_service._start_time if initializer.time_service else 'N/A'}")

    # Create service registry
    registry = ServiceRegistry()

    # Register TimeService
    from ciris_engine.schemas.runtime.enums import Priority, ServiceType

    registry.register_service(
        service_type=ServiceType.TIME,
        provider=initializer.time_service,
        priority=Priority.CRITICAL,
        capabilities=["now", "format_timestamp", "parse_timestamp"],
        metadata={"timezone": "UTC"},
    )

    print(f"\n7. Registered TimeService in ServiceRegistry")

    # Check if we can get it back
    time_services = registry.get_services_by_type(ServiceType.TIME)
    print(f"   get_services_by_type(ServiceType.TIME): {len(time_services)} services")
    if time_services:
        print(f"   First service: {time_services[0].__class__.__name__}")
        print(f"   First service _started: {time_services[0]._started}")

    # Create a mock runtime
    class MockRuntime:
        def __init__(self):
            self.service_initializer = initializer

        @property
        def time_service(self):
            return self.service_initializer.time_service if self.service_initializer else None

    runtime = MockRuntime()
    print(f"\n8. Created MockRuntime with time_service property")
    print(f"   runtime.time_service: {runtime.time_service}")

    # Create TelemetryAggregator
    aggregator = TelemetryAggregator(service_registry=registry, time_service=initializer.time_service, runtime=runtime)
    print(f"\n9. Created TelemetryAggregator")

    # Try to collect from TimeService
    print(f"\n10. Attempting to collect from 'time' service...")
    result = await aggregator.collect_service("time")
    print(f"    Result type: {type(result)}")
    print(f"    Result: {result}")
    if hasattr(result, "model_dump"):
        print(f"    Result dict: {json.dumps(result.model_dump(), indent=2)}")

    # Check _get_service_from_runtime
    print(f"\n11. Testing _get_service_from_runtime('time')...")
    service_from_runtime = aggregator._get_service_from_runtime("time")
    print(f"    Result: {service_from_runtime}")
    print(f"    Type: {type(service_from_runtime).__name__ if service_from_runtime else 'None'}")
    if service_from_runtime:
        print(f"    _started: {service_from_runtime._started}")

    # Check _get_service_from_registry
    print(f"\n12. Testing _get_service_from_registry('time')...")
    service_from_registry = aggregator._get_service_from_registry("time")
    print(f"    Result: {service_from_registry}")
    print(f"    Type: {type(service_from_registry).__name__ if service_from_registry else 'None'}")
    if service_from_registry:
        print(f"    _started: {service_from_registry._started}")


if __name__ == "__main__":
    asyncio.run(main())
