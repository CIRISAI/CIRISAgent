"""CIRISVerify service implementation for license verification."""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Set

from pydantic import BaseModel, Field

# Import from ciris-verify package (installed separately)
try:
    from ciris_verify import (
        BinaryNotFoundError,
        BinaryTamperedError,
        CapabilityCheckResult,
        CIRISVerify,
        DisclosureSeverity,
        HardwareType,
        LicenseStatus,
        LicenseStatusResponse,
        LicenseTier,
        MandatoryDisclosure,
        MockCIRISVerify,
    )

    CIRIS_VERIFY_AVAILABLE = True
except ImportError:
    CIRIS_VERIFY_AVAILABLE = False

    # Define stub types for when package not installed
    class LicenseStatus:
        UNLICENSED_COMMUNITY = 200

    class LicenseTier:
        COMMUNITY = 0

    class HardwareType:
        SOFTWARE_ONLY = "software_only"

    class DisclosureSeverity:
        WARNING = "warning"


logger = logging.getLogger(__name__)


class CachedLicenseStatus(BaseModel):
    """Cached license status with expiration."""

    response: Dict[str, Any] = Field(..., description="Serialized LicenseStatusResponse")
    cached_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(..., description="Cache expiration time")

    def is_valid(self) -> bool:
        """Check if cache is still valid."""
        return datetime.now(timezone.utc) < self.expires_at


class VerificationConfig(BaseModel):
    """Configuration for CIRISVerify service."""

    binary_path: Optional[str] = None
    cache_ttl_seconds: int = 300
    timeout_seconds: float = 10.0
    require_hardware: bool = False
    use_mock: bool = False  # For testing


class CIRISVerifyService:
    """Service providing license verification capabilities.

    This service wraps the CIRISVerify binary (or mock) and provides
    caching, capability checking, and integration with WiseBus.
    """

    def __init__(self, config: Optional[VerificationConfig] = None):
        """Initialize the verification service.

        Args:
            config: Service configuration. Uses defaults if not provided.
        """
        self.config = config or VerificationConfig()
        self._client: Optional[Any] = None
        self._cache: Optional[CachedLicenseStatus] = None
        self._cache_lock = asyncio.Lock()
        self._initialized = False
        self._last_nonce: Optional[bytes] = None

    async def initialize(self) -> bool:
        """Initialize the verification client.

        Returns:
            True if initialization successful, False otherwise.
        """
        if self._initialized:
            return True

        if not CIRIS_VERIFY_AVAILABLE and not self.config.use_mock:
            logger.warning("ciris-verify package not installed. " "Install with: pip install ciris-verify")
            # Fall back to mock in community mode
            self.config.use_mock = True

        try:
            if self.config.use_mock:
                logger.info("Using MockCIRISVerify for testing")
                # Import mock from our local implementation if package not available
                if CIRIS_VERIFY_AVAILABLE:
                    self._client = MockCIRISVerify(
                        mock_status=LicenseStatus.UNLICENSED_COMMUNITY,
                        mock_hardware=HardwareType.SOFTWARE_ONLY,
                    )
                else:
                    self._client = _FallbackMockClient()
            else:
                self._client = CIRISVerify(
                    binary_path=self.config.binary_path,
                    timeout_seconds=self.config.timeout_seconds,
                )
            self._initialized = True
            logger.info("CIRISVerify service initialized successfully")
            return True

        except BinaryNotFoundError as e:
            logger.error(f"CIRISVerify binary not found: {e}")
            # Fall back to mock
            self._client = _FallbackMockClient()
            self._initialized = True
            return True

        except BinaryTamperedError as e:
            logger.critical(f"SECURITY ALERT: CIRISVerify binary tampered: {e}")
            # DO NOT fall back - this is a security issue
            return False

        except Exception as e:
            logger.error(f"Failed to initialize CIRISVerify: {e}")
            return False

    async def shutdown(self) -> None:
        """Shutdown the service and cleanup resources."""
        self._client = None
        self._cache = None
        self._initialized = False

    async def get_license_status(
        self,
        force_refresh: bool = False,
    ) -> Optional[LicenseStatusResponse]:
        """Get current license status.

        Args:
            force_refresh: Bypass cache and fetch fresh status.

        Returns:
            LicenseStatusResponse or None if verification failed.
        """
        if not self._initialized:
            if not await self.initialize():
                return None

        async with self._cache_lock:
            # Check cache first
            if not force_refresh and self._cache and self._cache.is_valid():
                if CIRIS_VERIFY_AVAILABLE:
                    return LicenseStatusResponse.model_validate(self._cache.response)
                return self._cache.response

            # Generate fresh nonce
            nonce = os.urandom(32)
            self._last_nonce = nonce

            try:
                response = await self._client.get_license_status(
                    challenge_nonce=nonce,
                )

                # Update cache
                self._cache = CachedLicenseStatus(
                    response=response.model_dump() if hasattr(response, "model_dump") else response,
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.config.cache_ttl_seconds),
                )

                return response

            except Exception as e:
                logger.error(f"License verification failed: {e}")
                return None

    async def check_capability(self, capability: str) -> CapabilityCheckResult:
        """Check if a specific capability is allowed.

        Args:
            capability: Capability string (e.g., "medical:diagnosis").

        Returns:
            CapabilityCheckResult with allow/deny decision.
        """
        if not self._initialized:
            if not await self.initialize():
                if CIRIS_VERIFY_AVAILABLE:
                    return CapabilityCheckResult(
                        capability=capability,
                        allowed=False,
                        reason="Verification service not available",
                    )
                return {"capability": capability, "allowed": False, "reason": "Service unavailable"}

        try:
            return await self._client.check_capability(capability)
        except Exception as e:
            logger.error(f"Capability check failed: {e}")
            if CIRIS_VERIFY_AVAILABLE:
                return CapabilityCheckResult(
                    capability=capability,
                    allowed=False,
                    reason=f"Check failed: {e}",
                )
            return {"capability": capability, "allowed": False, "reason": str(e)}

    async def get_mandatory_disclosure(self) -> MandatoryDisclosure:
        """Get the mandatory disclosure for current license status.

        Returns:
            MandatoryDisclosure that MUST be shown to users.
        """
        status = await self.get_license_status()
        if status:
            return status.mandatory_disclosure

        # Fallback disclosure when verification unavailable
        if CIRIS_VERIFY_AVAILABLE:
            return MandatoryDisclosure(
                text=(
                    "NOTICE: License verification unavailable. "
                    "Operating in community mode with limited capabilities. "
                    "Professional features (medical, legal, financial) are NOT available."
                ),
                severity=DisclosureSeverity.WARNING,
            )
        return {
            "text": "NOTICE: Operating in community mode.",
            "severity": "warning",
        }

    def get_agent_tier(self) -> int:
        """Get the effective agent tier based on license.

        Returns:
            Agent tier (1-5). Community mode returns 1.
        """
        if self._cache and self._cache.is_valid():
            response = self._cache.response
            if isinstance(response, dict):
                if response.get("status", 200) in (100, 101):  # LICENSED_PROFESSIONAL*
                    license_data = response.get("license", {})
                    tier = license_data.get("tier", 0)
                    # Map license tier to agent tier
                    # License Tier 2 (PROFESSIONAL_FULL) = Agent Tier 4-5
                    if tier >= 2:
                        return 5
                    elif tier >= 1:
                        return 3
            elif hasattr(response, "status"):
                if response.status.allows_licensed_operation():
                    if response.license and response.license.tier >= LicenseTier.PROFESSIONAL_FULL:
                        return 5
                    return 3
        return 1  # Community tier

    def is_licensed(self) -> bool:
        """Quick check if agent is licensed.

        Returns:
            True if licensed for professional operations.
        """
        if self._cache and self._cache.is_valid():
            response = self._cache.response
            if isinstance(response, dict):
                return response.get("status", 200) in (100, 101)
            elif hasattr(response, "allows_licensed_operation"):
                return response.allows_licensed_operation()
        return False


class _FallbackMockClient:
    """Fallback mock when ciris-verify package not installed."""

    async def get_license_status(self, challenge_nonce: bytes) -> Dict[str, Any]:
        """Return community mode status."""
        return {
            "status": 200,  # UNLICENSED_COMMUNITY
            "license": None,
            "mandatory_disclosure": {
                "text": (
                    "NOTICE: This is an unlicensed community agent. " "Professional capabilities are NOT available."
                ),
                "severity": "info",
            },
            "hardware_type": "software_only",
            "cached": False,
        }

    async def check_capability(self, capability: str) -> Dict[str, Any]:
        """Deny all professional capabilities."""
        # Allow standard operations
        if capability.startswith("standard:") or capability.startswith("tool:"):
            return {
                "capability": capability,
                "allowed": True,
                "reason": "Standard operation allowed",
            }
        # Deny professional capabilities
        return {
            "capability": capability,
            "allowed": False,
            "reason": "Community mode - professional capabilities not available",
        }
