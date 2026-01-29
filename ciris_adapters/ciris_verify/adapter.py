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

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ciris_engine.logic.adapters.base_adapter import BaseAdapterProtocol
from ciris_engine.schemas.adapter_schemas import AdapterMetadata, AdapterServiceRegistration
from ciris_engine.schemas.foundational_schemas import Priority, ServiceType

from .service import CIRISVerifyService, VerificationConfig

logger = logging.getLogger(__name__)


class CIRISVerifyAdapter(BaseAdapterProtocol):
    """Adapter for CIRISVerify license verification.

    This adapter:
    1. Provides license verification services
    2. Integrates with WiseBus for capability enforcement
    3. Manages mandatory disclosure display
    4. Caches verification results for performance

    The adapter automatically falls back to community mode if:
    - CIRISVerify binary is not installed
    - Hardware security is unavailable
    - License verification fails

    Configuration (via config dict):
        binary_path: Optional path to CIRISVerify binary
        cache_ttl_seconds: Cache duration (default: 300)
        timeout_seconds: Verification timeout (default: 10.0)
        require_hardware: Require hardware HSM (default: false)
        use_mock: Use mock for testing (default: false)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the CIRISVerify adapter.

        Args:
            config: Optional configuration dictionary.
        """
        self.config = config or {}
        self._service: Optional[CIRISVerifyService] = None
        self._started = False

    @property
    def name(self) -> str:
        """Adapter name."""
        return "ciris_verify"

    @property
    def version(self) -> str:
        """Adapter version."""
        return "0.1.0"

    def get_metadata(self) -> AdapterMetadata:
        """Get adapter metadata."""
        return AdapterMetadata(
            name=self.name,
            version=self.version,
            description="Hardware-rooted license verification for CIRIS agents",
            author="CIRIS Engineering",
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
                service_type=ServiceType.VERIFICATION,
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
            binary_path=self.config.get("binary_path"),
            cache_ttl_seconds=self.config.get("cache_ttl_seconds", 300),
            timeout_seconds=self.config.get("timeout_seconds", 10.0),
            require_hardware=self.config.get("require_hardware", False),
            use_mock=self.config.get("use_mock", False),
        )

        self._service = CIRISVerifyService(service_config)

        if await self._service.initialize():
            self._started = True
            logger.info("CIRISVerify adapter started successfully")

            # Log initial license status
            status = await self._service.get_license_status()
            if status:
                if hasattr(status, "status"):
                    logger.info(f"License status: {status.status}")
                    if status.allows_licensed_operation():
                        logger.info("Running in LICENSED mode")
                    else:
                        logger.info("Running in COMMUNITY mode")
                else:
                    logger.info(f"License status: {status.get('status', 'unknown')}")
        else:
            logger.warning("CIRISVerify initialization failed - operating in community mode")
            self._started = True  # Still mark as started, just in degraded mode

    async def stop(self) -> None:
        """Stop the adapter and cleanup resources."""
        if not self._started:
            return

        logger.info("Stopping CIRISVerify adapter")

        if self._service:
            await self._service.shutdown()
            self._service = None

        self._started = False
        logger.info("CIRISVerify adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        The CIRISVerify adapter doesn't have long-running operations,
        so this method just ensures the service stays initialized.

        Args:
            agent_task: The main agent task (for coordination).
        """
        # Periodically refresh license status in background
        import asyncio

        while self._started:
            try:
                await asyncio.sleep(self.config.get("cache_ttl_seconds", 300) / 2)

                if self._service:
                    # Refresh license status
                    await self._service.get_license_status(force_refresh=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in CIRISVerify lifecycle: {e}")

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

    async def get_license_status(self, force_refresh: bool = False) -> Optional[Any]:
        """Get current license status.

        Args:
            force_refresh: Bypass cache and fetch fresh status.

        Returns:
            LicenseStatusResponse or None.
        """
        if not self._service:
            return None
        return await self._service.get_license_status(force_refresh)

    async def check_capability(self, capability: str) -> Any:
        """Check if a capability is allowed.

        Args:
            capability: Capability string to check.

        Returns:
            CapabilityCheckResult.
        """
        if not self._service:
            return {"capability": capability, "allowed": False, "reason": "Service not available"}
        return await self._service.check_capability(capability)

    async def get_mandatory_disclosure(self) -> Any:
        """Get mandatory disclosure for current status.

        Returns:
            MandatoryDisclosure that MUST be shown to users.
        """
        if not self._service:
            return {
                "text": "NOTICE: License verification unavailable.",
                "severity": "warning",
            }
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
