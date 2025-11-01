"""
Example stub for InfrastructureBootstrapper

This file shows the structure of the infrastructure bootstrapper component.
It is NOT executable - just a reference for Phase 3 implementation.
"""

from dataclasses import dataclass
from typing import Any, Optional

# Stub protocol types (real implementations use actual protocols)
TimeServiceProtocol = Any
SecretsServiceProtocol = Any
MemoryServiceProtocol = Any
ConfigServiceProtocol = Any
AuthenticationServiceProtocol = Any


@dataclass
class InfrastructureBundle:
    """Protocol-typed bundle of infrastructure services.

    This bundle contains all services needed before observability/governance
    can be initialized.
    """

    # Lifecycle services
    time_service: TimeServiceProtocol
    shutdown_service: Any  # ShutdownServiceProtocol
    initialization_service: Any  # InitializationServiceProtocol

    # Infrastructure services
    resource_monitor_service: Any  # ResourceMonitorServiceProtocol

    # Core services
    secrets_service: SecretsServiceProtocol
    memory_service: MemoryServiceProtocol
    config_service: ConfigServiceProtocol
    secrets_tool_service: Any  # SecretsToolServiceProtocol

    # Security services
    auth_service: AuthenticationServiceProtocol
    wise_authority_service: Any  # WiseAuthorityServiceProtocol


class InfrastructureBootstrapper:
    """Bootstraps core infrastructure services.

    SINGLE RESPONSIBILITY: Create and start infrastructure services in dependency order.

    Key Principles:
    - No environment access (uses typed config)
    - No config loading (accepts typed config)
    - Only service construction and starting
    - Returns protocol-typed bundle
    """

    def __init__(
        self,
        infrastructure_config: "InfrastructureConfig",  # type: ignore
        memory_config: "MemoryConfig",  # type: ignore
    ) -> None:
        """Initialize with typed configuration.

        Args:
            infrastructure_config: Infrastructure service settings
            memory_config: Memory and secrets configuration
        """
        self.infrastructure_config = infrastructure_config
        self.memory_config = memory_config

    async def bootstrap(self) -> InfrastructureBundle:
        """Bootstrap all infrastructure services.

        Initialization order (critical dependencies):
        1. TimeService (no dependencies)
        2. ShutdownService (no dependencies)
        3. InitializationService (depends on TimeService)
        4. ResourceMonitorService (depends on TimeService)
        5. SecretsService (depends on TimeService)
        6. MemoryService (depends on TimeService, SecretsService)
        7. ConfigService (depends on MemoryService, TimeService)
        8. SecretsToolService (depends on SecretsService, TimeService)
        9. AuthenticationService (depends on TimeService)
        10. WiseAuthorityService (depends on TimeService, AuthService)

        Returns:
            Bundle of all infrastructure services (protocol-typed)

        Raises:
            RuntimeError: If any service fails to initialize
        """
        # Create services in dependency order
        time_service = await self._create_time_service()
        shutdown_service = await self._create_shutdown_service()
        initialization_service = await self._create_initialization_service(time_service)
        resource_monitor = await self._create_resource_monitor(time_service)
        secrets_service = await self._create_secrets_service(time_service)
        memory_service = await self._create_memory_service(time_service, secrets_service)
        config_service = await self._create_config_service(memory_service, time_service)
        secrets_tool = await self._create_secrets_tool_service(secrets_service, time_service)
        auth_service = await self._create_auth_service(time_service)
        wise_authority = await self._create_wise_authority_service(time_service, auth_service)

        return InfrastructureBundle(
            time_service=time_service,
            shutdown_service=shutdown_service,
            initialization_service=initialization_service,
            resource_monitor_service=resource_monitor,
            secrets_service=secrets_service,
            memory_service=memory_service,
            config_service=config_service,
            secrets_tool_service=secrets_tool,
            auth_service=auth_service,
            wise_authority_service=wise_authority,
        )

    async def _create_time_service(self) -> TimeServiceProtocol:
        """Create and start TimeService.

        No dependencies.
        """
        from ciris_engine.logic.services.lifecycle.time import TimeService

        service = TimeService()
        await service.start()
        return service

    async def _create_shutdown_service(self) -> Any:
        """Create and start ShutdownService.

        No dependencies.
        """
        from ciris_engine.logic.services.lifecycle.shutdown import ShutdownService

        service = ShutdownService()
        await service.start()
        return service

    async def _create_initialization_service(self, time_service: TimeServiceProtocol) -> Any:
        """Create and start InitializationService.

        Depends on: TimeService
        """
        from ciris_engine.logic.services.lifecycle.initialization import InitializationService

        service = InitializationService(time_service)
        await service.start()
        return service

    async def _create_resource_monitor(self, time_service: TimeServiceProtocol) -> Any:
        """Create and start ResourceMonitorService with configured credit provider.

        Depends on: TimeService
        Uses config: infrastructure_config.resource_monitor
        """
        from ciris_engine.logic.persistence import get_sqlite_db_full_path
        from ciris_engine.logic.services.infrastructure.resource_monitor import (
            CIRISBillingProvider,
            ResourceMonitorService,
            SimpleCreditProvider,
        )
        from ciris_engine.schemas.services.resources_core import ResourceBudget

        # Create default resource budget
        budget = ResourceBudget()

        # Create credit provider based on config
        rm_config = self.infrastructure_config.resource_monitor
        if rm_config.credit_provider.value == "billing":
            billing_cfg = rm_config.billing
            credit_provider = CIRISBillingProvider(
                api_key=billing_cfg.api_key,
                base_url=billing_cfg.base_url,
                timeout_seconds=billing_cfg.timeout_seconds,
                cache_ttl_seconds=billing_cfg.cache_ttl_seconds,
                fail_open=billing_cfg.fail_open,
            )
        else:
            simple_cfg = rm_config.simple
            credit_provider = SimpleCreditProvider(free_uses=simple_cfg.free_uses)

        # Create service
        service = ResourceMonitorService(
            budget=budget,
            db_path=self.memory_config.memory_db_path,  # Uses main DB
            time_service=time_service,
            credit_provider=credit_provider,
        )
        await service.start()
        return service

    async def _create_secrets_service(self, time_service: TimeServiceProtocol) -> SecretsServiceProtocol:
        """Create and start SecretsService.

        Depends on: TimeService
        Uses config: memory_config.secrets_key_path, memory_config.secrets_db_path

        Handles master key loading/generation.
        """
        import os
        import secrets as python_secrets
        from pathlib import Path

        import aiofiles

        from ciris_engine.logic.secrets.service import SecretsService

        # Load or generate master key
        keys_dir = Path(self.memory_config.secrets_key_path)
        keys_dir.mkdir(parents=True, exist_ok=True)

        master_key_path = keys_dir / "secrets_master.key"
        if master_key_path.exists():
            async with aiofiles.open(master_key_path, "rb") as f:
                master_key = await f.read()
        else:
            master_key = python_secrets.token_bytes(32)
            async with aiofiles.open(master_key_path, "wb") as f:
                await f.write(master_key)
            os.chmod(master_key_path, 0o600)

        # Create service
        service = SecretsService(
            db_path=self.memory_config.secrets_db_path, time_service=time_service, master_key=master_key
        )
        await service.start()
        return service

    async def _create_memory_service(
        self, time_service: TimeServiceProtocol, secrets_service: SecretsServiceProtocol
    ) -> MemoryServiceProtocol:
        """Create and start LocalGraphMemoryService.

        Depends on: TimeService, SecretsService
        Uses config: memory_config.memory_db_path
        """
        from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService

        service = LocalGraphMemoryService(
            db_path=self.memory_config.memory_db_path, time_service=time_service, secrets_service=secrets_service
        )
        await service.start()
        return service

    # ... _create_config_service(), _create_secrets_tool_service(), etc.
    # Similar pattern for all remaining services


# Example usage:
if __name__ == "__main__":
    import asyncio

    async def main():
        # Create typed configs (normally from ConfigurationAdapter)
        # ... create infrastructure_config and memory_config ...

        # Bootstrap infrastructure
        bootstrapper = InfrastructureBootstrapper(
            infrastructure_config=infrastructure_config,
            memory_config=memory_config,
        )

        bundle = await bootstrapper.bootstrap()

        print(f"Time service: {bundle.time_service}")
        print(f"Memory service: {bundle.memory_service}")
        print(f"Total services: 10")

    asyncio.run(main())
