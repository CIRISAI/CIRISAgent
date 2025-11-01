"""
Example stub for ServiceOrchestrator

This file shows the structure of the service orchestrator component.
It is NOT executable - just a reference for Phase 6 implementation.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class InitializedServices:
    """Complete set of initialized services.

    This is what the orchestrator returns - everything needed to run CIRIS.
    """

    infrastructure: "InfrastructureBundle"  # type: ignore
    observability: "ObservabilityBundle"  # type: ignore
    governance: "GovernanceBundle"  # type: ignore
    llm_service: Optional[Any]  # LLMServiceProtocol
    service_registry: Any  # ServiceRegistry
    bus_manager: Any  # BusManager


class ServiceOrchestrator:
    """Orchestrates service initialization across all composers.

    SINGLE RESPONSIBILITY: Coordinate initialization phases and dependency flow.

    This is the main entry point for typed initialization. It uses the composers
    to do actual work, and coordinates the overall flow.
    """

    def __init__(
        self,
        config: "InitializationConfig",  # type: ignore
        essential_config: "EssentialConfig",  # type: ignore
    ) -> None:
        """Initialize orchestrator.

        Args:
            config: Complete typed initialization configuration
            essential_config: Original essential config (needed for some legacy paths)
        """
        self.config = config
        self.essential_config = essential_config

        # Metrics tracking (compatible with v1.4.3)
        self._metrics_start_time: Optional[float] = None
        self._metrics_end_time: Optional[float] = None
        self._services_started: int = 0
        self._errors: int = 0

    async def initialize_all(self) -> InitializedServices:
        """Initialize all services using typed configuration.

        Initialization flow:
        1. Bootstrap infrastructure (InfrastructureBootstrapper)
        2. Create ServiceRegistry
        3. Register infrastructure services
        4. Create BusManager
        5. Initialize LLM services (if not skipped)
        6. Compose observability (ObservabilityComposer)
        7. Compose governance (GovernanceComposer)
        8. Wire all services into registry
        9. Migrate essential config to graph

        Returns:
            Complete set of initialized services

        Raises:
            RuntimeError: If any initialization phase fails
        """
        self._metrics_start_time = time.time()

        try:
            # Phase 1: Infrastructure
            infra_bootstrapper = self._create_infrastructure_bootstrapper()
            infrastructure = await infra_bootstrapper.bootstrap()
            self._services_started += 10  # 10 infrastructure services

            # Phase 2: Registry and buses
            service_registry = self._create_service_registry()
            self._register_infrastructure_services(infrastructure, service_registry)
            bus_manager = self._create_bus_manager(
                service_registry,
                infrastructure.time_service,
                telemetry_service=None,  # Set after observability composition
                audit_service=None,  # Set after observability composition
            )

            # Phase 3: LLM (optional)
            llm_service = await self._initialize_llm_services(infrastructure.time_service, service_registry)
            if llm_service:
                self._services_started += 1  # Or 2 if secondary also initialized

            # Phase 4: Observability
            observability_composer = self._create_observability_composer(infrastructure, service_registry, bus_manager)
            observability = await observability_composer.compose()
            self._services_started += 5  # 5 observability services

            # Update bus_manager with telemetry/audit
            bus_manager.telemetry_service = observability.telemetry_service
            bus_manager.audit_service = observability.audit_service
            bus_manager.llm.telemetry_service = observability.telemetry_service

            # Phase 5: Governance
            governance_composer = self._create_governance_composer(
                infrastructure, llm_service, service_registry, bus_manager
            )
            governance = await governance_composer.compose()
            self._services_started += 6  # 6 governance services

            # Phase 6: Final wiring
            self._register_all_services(infrastructure, observability, governance, service_registry)

            # Phase 7: Config migration
            await self._migrate_config_to_graph(infrastructure.config_service)

            self._metrics_end_time = time.time()

            return InitializedServices(
                infrastructure=infrastructure,
                observability=observability,
                governance=governance,
                llm_service=llm_service,
                service_registry=service_registry,
                bus_manager=bus_manager,
            )

        except Exception as e:
            self._errors += 1
            self._metrics_end_time = time.time()
            raise RuntimeError(f"Service initialization failed: {e}") from e

    def _create_infrastructure_bootstrapper(self) -> "InfrastructureBootstrapper":  # type: ignore
        """Create infrastructure bootstrapper with typed config."""
        from ciris_engine.logic.initialization.infrastructure_bootstrapper import InfrastructureBootstrapper

        return InfrastructureBootstrapper(
            infrastructure_config=self.config.infrastructure,
            memory_config=self.config.memory,
        )

    def _create_service_registry(self) -> Any:
        """Create service registry."""
        from ciris_engine.logic.registries.base import get_global_registry

        return get_global_registry()

    def _create_bus_manager(self, *args, **kwargs) -> Any:
        """Create bus manager."""
        from ciris_engine.logic.buses import BusManager

        return BusManager(*args, **kwargs)

    async def _initialize_llm_services(
        self,
        time_service: Any,
        service_registry: Any,
    ) -> Optional[Any]:
        """Initialize LLM services based on configuration.

        Returns None if skip_initialization=True (mock mode).
        """
        if self.config.llm.skip_initialization:
            return None

        if not self.config.llm.primary:
            return None

        # Create primary LLM
        from ciris_engine.logic.registries.base import Priority
        from ciris_engine.logic.services.runtime.llm_service import (
            OpenAICompatibleClient,
            OpenAIConfig,
        )
        from ciris_engine.schemas.runtime.enums import ServiceType
        from ciris_engine.schemas.services.capabilities import LLMCapabilities

        llm_config = OpenAIConfig(
            base_url=self.config.llm.primary.base_url,
            model_name=self.config.llm.primary.model_name,
            api_key=self.config.llm.primary.api_key,
            instructor_mode=self.config.llm.primary.instructor_mode.value,
            timeout_seconds=self.config.llm.primary.timeout_seconds,
            max_retries=self.config.llm.primary.max_retries,
        )

        primary_llm = OpenAICompatibleClient(
            config=llm_config,
            telemetry_service=None,  # Set after telemetry initialization
            time_service=time_service,
        )
        await primary_llm.start()

        # Register primary
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=primary_llm,
            priority=Priority.HIGH,
            capabilities=[LLMCapabilities.CALL_LLM_STRUCTURED],
            metadata={"provider": "openai", "model": llm_config.model_name},
        )

        # Create secondary if configured
        if self.config.llm.secondary:
            # ... similar to primary ...
            pass

        return primary_llm

    def _create_observability_composer(self, *args, **kwargs) -> Any:
        """Create observability composer."""
        from ciris_engine.logic.initialization.observability_composer import ObservabilityComposer

        return ObservabilityComposer(observability_config=self.config.observability, *args, **kwargs)

    def _create_governance_composer(self, *args, **kwargs) -> Any:
        """Create governance composer."""
        from ciris_engine.logic.initialization.governance_composer import GovernanceComposer

        return GovernanceComposer(governance_config=self.config.governance, *args, **kwargs)

    def _register_infrastructure_services(self, infrastructure, registry) -> None:
        """Register infrastructure services in registry."""
        # Implementation registers all infrastructure services
        pass

    def _register_all_services(self, infrastructure, observability, governance, registry) -> None:
        """Register all services in registry."""
        # Implementation registers all services
        pass

    async def _migrate_config_to_graph(self, config_service) -> None:
        """Migrate essential config to graph storage."""
        # Implementation migrates config
        pass

    def get_metrics(self) -> Dict[str, float]:
        """Get initialization metrics compatible with v1.4.3 format.

        Returns:
            Dict with keys:
            - initializer_services_started
            - initializer_startup_time_ms
            - initializer_errors
            - initializer_dependencies_resolved
        """
        startup_time_ms = 0.0
        if self._metrics_start_time and self._metrics_end_time:
            startup_time_ms = (self._metrics_end_time - self._metrics_start_time) * 1000.0

        return {
            "initializer_services_started": float(self._services_started),
            "initializer_startup_time_ms": startup_time_ms,
            "initializer_errors": float(self._errors),
            "initializer_dependencies_resolved": float(self._services_started),
        }


# Example usage:
if __name__ == "__main__":
    import asyncio

    async def main():
        # Load config (normally from ConfigurationAdapter)
        # ... create init_config ...

        # Create orchestrator
        orchestrator = ServiceOrchestrator(
            config=init_config,
            essential_config=essential_config,
        )

        # Initialize everything
        services = await orchestrator.initialize_all()

        print(f"Infrastructure services: 10")
        print(f"Observability services: 5")
        print(f"Governance services: 6")
        print(f"Total: {orchestrator._services_started}")

        # Get metrics
        metrics = orchestrator.get_metrics()
        print(f"Startup time: {metrics['initializer_startup_time_ms']:.2f}ms")

    asyncio.run(main())
