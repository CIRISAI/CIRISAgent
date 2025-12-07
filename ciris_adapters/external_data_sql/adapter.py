"""
External Data SQL Adapter for CIRIS.

Provides the BaseAdapterProtocol-compliant wrapper around SQLToolService
so it can be loaded dynamically via RuntimeAdapterManager.load_adapter().
"""

import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .service import SQLToolService

logger = logging.getLogger(__name__)


class ExternalDataSQLAdapter(Service):
    """
    External Data SQL adapter platform for CIRIS.

    Wraps SQLToolService to provide the BaseAdapterProtocol interface
    required for dynamic adapter loading via RuntimeAdapterManager.
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize External Data SQL adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Create the underlying SQL tool service
        # It reads config from environment variables set by SQLConfigurableAdapter.apply_config()
        self.sql_service = SQLToolService()

        # Track adapter state
        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info("External Data SQL adapter initialized")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        registrations = []

        # Register the SQL service as a tool service with its capabilities
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.sql_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "tool:sql",
                    "tool:sql:find_user_data",
                    "tool:sql:export_user",
                    "tool:sql:delete_user",
                    "tool:sql:anonymize_user",
                    "tool:sql:verify_deletion",
                    "tool:sql:get_stats",
                    "tool:sql:query",
                    "provider:sql",
                    "dsar:sql",
                ],
            )
        )

        return registrations

    async def start(self) -> None:
        """Start the External Data SQL adapter."""
        logger.info("Starting External Data SQL adapter")
        await self.sql_service.initialize()
        self._running = True
        logger.info("External Data SQL adapter started")

    async def stop(self) -> None:
        """Stop the External Data SQL adapter."""
        logger.info("Stopping External Data SQL adapter")
        self._running = False

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        # Stop the SQL service if it has a stop method
        if hasattr(self.sql_service, "stop"):
            await self.sql_service.stop()
        elif hasattr(self.sql_service, "shutdown"):
            await self.sql_service.shutdown()

        logger.info("External Data SQL adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        For SQL data access, we just wait for the agent task to complete
        since SQL operations are request-driven and don't need continuous polling.
        """
        logger.info("External Data SQL adapter lifecycle started")
        try:
            # Wait for the agent task to signal shutdown
            await agent_task
        except asyncio.CancelledError:
            logger.info("External Data SQL adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        config_obj = self.sql_service._config
        connector_id = config_obj.connector_id if config_obj else "sql"
        dialect = config_obj.dialect.value if config_obj and config_obj.dialect else "unknown"

        return AdapterConfig(
            adapter_type="external_data_sql",
            enabled=self._running,
            settings={
                "connector_id": connector_id,
                "dialect": dialect,
                "has_privacy_schema": bool(config_obj and config_obj.privacy_schema),
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="external_data_sql",
            adapter_type="external_data_sql",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
Adapter = ExternalDataSQLAdapter
