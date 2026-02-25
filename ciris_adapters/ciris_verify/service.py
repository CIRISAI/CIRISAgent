"""CIRISVerify service implementation for license verification."""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from ciris_verify import (
    BinaryNotFoundError,
    BinaryTamperedError,
    CapabilityCheckResult,
    CIRISVerify,
    DisclosureSeverity,
    LicenseStatusResponse,
    LicenseTier,
    MandatoryDisclosure,
)
from pydantic import BaseModel, Field

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


class CIRISVerifyService:
    """Service providing license verification capabilities.

    This service wraps the CIRISVerify client and provides
    caching, capability checking, and integration with WiseBus.

    CIRISVerify handles its own fallback to software-only signing
    when hardware security is unavailable (community mode).
    """

    # Log level names for callback
    _LOG_LEVEL_NAMES = {1: "ERROR", 2: "WARN", 3: "INFO", 4: "DEBUG", 5: "TRACE"}

    def __init__(self, config: Optional[VerificationConfig] = None):
        self.config = config or VerificationConfig()
        self._client: Optional[CIRISVerify] = None
        self._cache: Optional[CachedLicenseStatus] = None
        self._cache_lock = asyncio.Lock()
        self._initialized = False
        self._last_nonce: Optional[bytes] = None
        self._log_callback_enabled = False

    def _setup_log_callback(self) -> None:
        """Set up log callback to capture internal CIRISVerify diagnostics.

        This routes Rust-side log messages to Python logging for debugging.
        Enabled when CIRIS_VERIFY_DEBUG=1 or log level is DEBUG.
        """
        if not self._client:
            return

        # Check if debug logging is enabled
        debug_env = os.environ.get("CIRIS_VERIFY_DEBUG", "").lower() in ("1", "true", "yes")
        debug_level = logger.isEnabledFor(logging.DEBUG)

        if not (debug_env or debug_level):
            return

        # Set callback level based on environment
        # Level: 1=ERROR, 2=WARN, 3=INFO, 4=DEBUG, 5=TRACE
        callback_level = 5 if os.environ.get("CIRIS_VERIFY_TRACE") else 4

        def log_callback(level: int, target: str, message: str) -> None:
            """Route CIRISVerify logs to Python logging."""
            level_name = self._LOG_LEVEL_NAMES.get(level, "?")
            log_msg = f"[CIRISVerify/{target}] {message}"

            if level == 1:  # ERROR
                logger.error(log_msg)
            elif level == 2:  # WARN
                logger.warning(log_msg)
            elif level == 3:  # INFO
                logger.info(log_msg)
            else:  # DEBUG/TRACE
                logger.debug(log_msg)

        try:
            self._client.set_log_callback(log_callback, level=callback_level)  # type: ignore[attr-defined]
            self._log_callback_enabled = True
            logger.debug("CIRISVerify log callback enabled at level %d", callback_level)
        except Exception as e:
            logger.debug("CIRISVerify log callback not available: %s", e)

    async def initialize(self) -> bool:
        """Initialize the verification client.

        Returns:
            True if initialization successful, False otherwise.
        """
        if self._initialized:
            return True

        try:
            self._client = CIRISVerify(
                binary_path=self.config.binary_path,
                timeout_seconds=self.config.timeout_seconds,
            )

            # Set up log callback for debugging (v0.9.3+)
            self._setup_log_callback()

            self._initialized = True
            logger.info("CIRISVerify service initialized successfully")
            return True

        except BinaryNotFoundError as e:
            logger.error("CIRISVerify binary not found: %s", e)
            return False

        except BinaryTamperedError as e:
            logger.critical("SECURITY ALERT: CIRISVerify binary tampered: %s", e)
            return False

        except Exception as e:
            logger.error("Failed to initialize CIRISVerify: %s", e)
            return False

    async def shutdown(self) -> None:
        """Shutdown the service and cleanup resources."""
        # Clear log callback before destroying client
        if self._client and self._log_callback_enabled:
            try:
                self._client.set_log_callback(None)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._log_callback_enabled = False

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
            if not force_refresh and self._cache and self._cache.is_valid():
                return LicenseStatusResponse.model_validate(self._cache.response)

            nonce = os.urandom(32)
            self._last_nonce = nonce

            try:
                assert self._client is not None, "Client not initialized"
                response = await self._client.get_license_status(
                    challenge_nonce=nonce,
                )

                self._cache = CachedLicenseStatus(
                    response=response.model_dump(),
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.config.cache_ttl_seconds),
                )

                return response

            except Exception as e:
                logger.error("License verification failed: %s", e)
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
                return CapabilityCheckResult(
                    capability=capability,
                    allowed=False,
                    reason="Verification service not available",
                )

        try:
            assert self._client is not None, "Client not initialized"
            return await self._client.check_capability(capability)
        except Exception as e:
            logger.error("Capability check failed: %s", e)
            return CapabilityCheckResult(
                capability=capability,
                allowed=False,
                reason=f"Check failed: {e}",
            )

    async def get_mandatory_disclosure(self) -> MandatoryDisclosure:
        """Get the mandatory disclosure for current license status.

        Returns:
            MandatoryDisclosure that MUST be shown to users.
        """
        status = await self.get_license_status()
        if status:
            return status.mandatory_disclosure

        return MandatoryDisclosure(
            text=(
                "NOTICE: License verification unavailable. "
                "Operating in community mode with limited capabilities. "
                "Professional features (medical, legal, financial) are NOT available."
            ),
            severity=DisclosureSeverity.WARNING,
        )

    def get_agent_tier(self) -> int:
        """Get the effective agent tier based on license.

        Returns:
            Agent tier (1-5). Community mode returns 1.
        """
        if self._cache and self._cache.is_valid():
            response = LicenseStatusResponse.model_validate(self._cache.response)
            if response.status.allows_licensed_operation():
                if response.license and response.license.tier >= LicenseTier.PROFESSIONAL_FULL:
                    return 5
                return 3
        return 1

    def is_licensed(self) -> bool:
        """Quick check if agent is licensed.

        Returns:
            True if licensed for professional operations.
        """
        if self._cache and self._cache.is_valid():
            response = LicenseStatusResponse.model_validate(self._cache.response)
            return response.allows_licensed_operation()
        return False
