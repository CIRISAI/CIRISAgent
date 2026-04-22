"""
CIRIS Hosted Tools Adapter.

Provides access to CIRIS-hosted tools (web search, etc.) via the CIRIS proxy.
These tools require platform-level security guarantees (proof of possession).

Platform Requirements:
- Android: Google Play Integrity + Native Google Sign-In
- iOS: App Attest + Native Apple Sign-In (future)
- Web: DPoP token binding (future)
"""

import asyncio
import logging
from typing import Any, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.platform import PlatformRequirement
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .services import CIRISHostedToolService

logger = logging.getLogger(__name__)


class CIRISHostedToolsAdapter(Service):
    """
    CIRIS Hosted Tools adapter for platform-bound tool access.

    This adapter provides tools that require device attestation and
    proof of possession to prevent API abuse. The tools call out to
    the CIRIS proxy which handles:
    - API key management (secrets never exposed to client)
    - Per-user rate limiting and billing
    - Device attestation verification

    Currently supported platforms:
    - Android (Google Play Integrity + Native Google Sign-In)

    Future platforms:
    - iOS (App Attest + Native Apple Sign-In)
    - Web (DPoP token binding)
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize CIRIS Hosted Tools adapter.

        Args:
            runtime: CIRIS runtime instance
            context: Optional runtime context
            **kwargs: Additional configuration (may include adapter_config)
        """
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Extract config from kwargs
        adapter_config = kwargs.get("adapter_config", {})

        # Create the tool service
        self.tool_service = CIRISHostedToolService(config=adapter_config)

        # Track adapter state
        self._running = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

        logger.info("CIRIS Hosted Tools adapter initialized")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter.

        Returns:
            List of service registrations with platform requirements
        """
        registrations = []

        # Register TOOL service with platform requirements
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "tool:web_search",
                    "tool:ciris_hosted",
                ],
                # Entire service requires Android with Play Integrity
                platform_requirements=[
                    PlatformRequirement.ANDROID_PLAY_INTEGRITY,
                    PlatformRequirement.GOOGLE_NATIVE_AUTH,
                ],
                platform_requirements_rationale=(
                    "CIRIS hosted tools require device attestation to prevent API abuse. "
                    "These tools are only available on Android with Google Play Services. "
                    "Future support planned for iOS (App Attest) and Web (DPoP)."
                ),
            )
        )

        return registrations

    async def start(self) -> None:
        """Start the CIRIS Hosted Tools adapter."""
        logger.info("Starting CIRIS Hosted Tools adapter")
        await self.tool_service.start()
        self._running = True
        logger.info("CIRIS Hosted Tools adapter started")

    async def stop(self) -> None:
        """Stop the CIRIS Hosted Tools adapter."""
        logger.info("Stopping CIRIS Hosted Tools adapter")
        self._running = False

        # Cancel lifecycle task if running
        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        await self.tool_service.stop()
        logger.info("CIRIS Hosted Tools adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        For CIRIS hosted tools, we just wait for the agent task to complete
        since tools are request-response (no continuous polling needed).

        Args:
            agent_task: The main agent task (signals shutdown when complete)
        """
        logger.info("CIRIS Hosted Tools adapter lifecycle started")
        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info("CIRIS Hosted Tools adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        return AdapterConfig(
            adapter_type="ciris_hosted_tools",
            enabled=self._running,
            settings={
                "proxy_url": self.tool_service._proxy_url,
                "tool_calls": self.tool_service._call_count,
                "errors": self.tool_service._error_count,
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="ciris_hosted_tools",
            adapter_type="ciris_hosted_tools",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for load_adapter() compatibility
Adapter = CIRISHostedToolsAdapter
