"""CIRISVerify adapter implementation.

This adapter provides hardware-rooted license verification as a service.
It does NOT modify WiseBus prohibitions directly - that is the responsibility
of licensed consumer modules (CIRISMedical, CIRISLegal, CIRISFinancial).

Architecture:
    CIRISVerify (this adapter) → Provides verification service
    ↓
    Licensed modules (CIRISMedical etc.) → Consume verification
    ↓
    WiseBus.PROHIBITED_CAPABILITIES → Modified by licensed modules

The verification service provides:
- License status verification with hardware attestation
- Capability checking against license grants
- Mandatory disclosure text for user-facing responses
- Agent tier detection based on license level
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional

from ciris_verify import CapabilityCheckResult, DisclosureSeverity, LicenseStatusResponse, MandatoryDisclosure

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .service import CIRISVerifyService, VerificationConfig


@dataclass
class AdapterMetadata:
    """Metadata describing an adapter's identity and capabilities."""

    name: str
    version: str
    capabilities: List[str] = field(default_factory=list)


logger = logging.getLogger(__name__)


class CIRISVerifyAdapter(Service):
    """Adapter for CIRISVerify license verification.

    This adapter:
    1. Provides license verification services
    2. Integrates with WiseBus for capability enforcement
    3. Manages mandatory disclosure display
    4. Caches verification results for performance

    CIRISVerify handles its own fallback to software-only signing
    when hardware security is unavailable (community mode).

    Configuration (via config dict):
        binary_path: Optional path to CIRISVerify binary
        cache_ttl_seconds: Cache duration (default: 300)
        timeout_seconds: Verification timeout (default: 10.0)
        require_hardware: Require hardware HSM (default: false)
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize the CIRISVerify adapter.

        Args:
            runtime: The CIRIS runtime instance.
            context: Optional adapter startup context.
            **kwargs: Additional configuration including adapter_config.
        """
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context
        self._config = kwargs.get("adapter_config") or {}
        self._service: Optional[CIRISVerifyService] = None
        self._started = False
        self._lifecycle_task: Optional[asyncio.Task[None]] = None

    @property
    def name(self) -> str:
        """Adapter name."""
        return "ciris_verify"

    @property
    def version(self) -> str:
        """Adapter version."""
        return "0.1.0"

    def get_metadata(self) -> AdapterMetadata:
        """Get adapter metadata for introspection by consumers."""
        return AdapterMetadata(
            name=self.name,
            version=self.version,
            capabilities=[
                "license:verify",
                "license:check_capability",
                "license:get_disclosure",
                "license:get_tier",
            ],
        )

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services to register with the service registry.

        Returns:
            List of service registrations.
        """
        if not self._service:
            return []

        return [
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,  # License verification is a tool service
                provider=self._service,
                priority=Priority.HIGH,  # License checks are critical
                capabilities=[
                    "license:verify",
                    "license:check_capability",
                    "license:get_disclosure",
                    "license:get_tier",
                ],
            ),
        ]

    async def start(self) -> None:
        """Start the adapter and initialize services."""
        if self._started:
            return

        logger.info("Starting CIRISVerify adapter")

        # Build service config
        service_config = VerificationConfig(
            binary_path=self._config.get("binary_path"),
            cache_ttl_seconds=self._config.get("cache_ttl_seconds", 300),
            timeout_seconds=self._config.get("timeout_seconds", 10.0),
            require_hardware=self._config.get("require_hardware", False),
        )

        self._service = CIRISVerifyService(service_config)

        if await self._service.initialize():
            self._started = True
            logger.info("CIRISVerify adapter started successfully")

            # Check if we're in first-run mode - skip license check (no license exists yet)
            from ciris_engine.logic.setup.first_run import is_first_run

            if is_first_run():
                logger.info("First-run mode: Skipping initial license check (license will be obtained via Portal)")
            else:
                # Log initial license status
                status = await self._service.get_license_status()
                if status:
                    logger.info("License status: %s", status.status)
                    if status.allows_licensed_operation():
                        logger.info("Running in LICENSED mode")
                    else:
                        logger.info("Running in COMMUNITY mode")
        else:
            logger.warning("CIRISVerify initialization failed - operating in community mode")
            self._started = True  # Still mark as started, just in degraded mode

    async def stop(self) -> None:
        """Stop the adapter and cleanup resources."""
        if not self._started:
            return

        logger.info("Stopping CIRISVerify adapter")

        if self._lifecycle_task and not self._lifecycle_task.done():
            self._lifecycle_task.cancel()
            try:
                await self._lifecycle_task
            except asyncio.CancelledError:
                pass

        if self._service:
            await self._service.shutdown()
            self._service = None

        self._started = False
        logger.info("CIRISVerify adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        The CIRISVerify adapter periodically refreshes license status.

        Args:
            agent_task: The main agent task (for coordination).
        """
        logger.info("CIRISVerify adapter lifecycle started")
        try:
            while self._started:
                await asyncio.sleep(self._config.get("cache_ttl_seconds", 300) / 2)

                if self._service:
                    # Refresh license status
                    await self._service.get_license_status(force_refresh=True)

        except asyncio.CancelledError:
            logger.info("CIRISVerify adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        return AdapterConfig(
            adapter_type="ciris_verify",
            enabled=self._started,
            settings={
                "cache_ttl_seconds": self._config.get("cache_ttl_seconds", 300),
                "timeout_seconds": self._config.get("timeout_seconds", 10.0),
                "require_hardware": self._config.get("require_hardware", False),
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="ciris_verify",
            adapter_type="ciris_verify",
            is_running=self._started,
            loaded_at=None,
            error=None,
        )

    # =========================================================================
    # Public API for Licensed Module Consumers
    # =========================================================================
    #
    # These methods are designed to be called by licensed modules
    # (CIRISMedical, CIRISLegal, CIRISFinancial) to verify license status
    # before modifying WiseBus.PROHIBITED_CAPABILITIES.
    #
    # Pattern for consumers:
    #
    #   from ciris_adapters.ciris_verify import CIRISVerifyAdapter
    #
    #   verify_adapter = get_adapter("ciris_verify")
    #   status = await verify_adapter.get_license_status()
    #
    #   if verify_adapter.is_licensed():
    #       # Check if we have the specific capability
    #       result = await verify_adapter.check_capability("domain:medical:*")
    #       if result.allowed:
    #           # Lift prohibition for medical capabilities
    #           WiseBus.PROHIBITED_CAPABILITIES.discard("medical")
    #   else:
    #       # Keep prohibitions in place
    #       pass
    #
    # =========================================================================

    async def get_license_status(self, force_refresh: bool = False) -> Optional[LicenseStatusResponse]:
        """Get current license status.

        Args:
            force_refresh: Bypass cache and fetch fresh status.

        Returns:
            LicenseStatusResponse or None.
        """
        if not self._service:
            return None
        return await self._service.get_license_status(force_refresh)

    async def check_capability(self, capability: str) -> CapabilityCheckResult:
        """Check if a capability is allowed.

        Args:
            capability: Capability string to check.

        Returns:
            CapabilityCheckResult.
        """
        if not self._service:
            return CapabilityCheckResult(
                capability=capability,
                allowed=False,
                reason="Service not available",
            )
        return await self._service.check_capability(capability)

    async def get_mandatory_disclosure(self) -> MandatoryDisclosure:
        """Get mandatory disclosure for current status.

        Returns:
            MandatoryDisclosure that MUST be shown to users.
        """
        if not self._service:
            return MandatoryDisclosure(
                text="NOTICE: License verification unavailable.",
                severity=DisclosureSeverity.WARNING,
            )
        return await self._service.get_mandatory_disclosure()

    def get_agent_tier(self) -> int:
        """Get effective agent tier based on license.

        Returns:
            Agent tier (1-5).
        """
        if not self._service:
            return 1
        return self._service.get_agent_tier()

    def is_licensed(self) -> bool:
        """Check if agent is licensed for professional operations.

        Returns:
            True if licensed.
        """
        if not self._service:
            return False
        return self._service.is_licensed()


# Export as Adapter for load_adapter() compatibility
Adapter = CIRISVerifyAdapter
