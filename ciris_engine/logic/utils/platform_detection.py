"""
CIRIS Platform Detection Utility.

Centralized platform detection that determines:
1. What platform we're running on (android, ios, linux, windows, macos)
2. What security capabilities are available (Play Integrity, TPM, etc.)
3. What authentication methods are available (native Google/Apple Sign-In)

This module populates a PlatformCapabilities object that can be used
to check if platform requirements for tools/adapters are satisfied.

NOTE: Basic platform detection (is_android, is_managed, is_development_mode)
is in path_resolution.py to avoid circular imports. This module re-exports
those functions and adds security capability detection on top.
"""

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional

# Import basic platform detection from path_resolution to avoid duplication
from ciris_engine.logic.utils.path_resolution import is_android
from ciris_engine.schemas.platform import PlatformCapabilities, PlatformRequirement

logger = logging.getLogger(__name__)


def is_ios() -> bool:
    """Detect if running on iOS platform.

    Currently iOS is not supported for Python execution,
    but this is here for future compatibility.

    Returns:
        True if running on iOS (currently always False)
    """
    # iOS detection would go here when/if we support it
    # Could check for specific environment variables or paths
    return False


def get_platform_name() -> str:
    """Get the current platform name.

    Returns:
        Platform name: 'android', 'ios', 'linux', 'windows', 'macos', or 'unknown'
    """
    if is_android():
        return "android"

    if is_ios():
        return "ios"

    if sys.platform == "darwin":
        return "macos"

    if sys.platform == "win32":
        return "windows"

    if sys.platform.startswith("linux"):
        return "linux"

    return "unknown"


# ============================================================================
# Security Capability Detection
# ============================================================================


def _detect_android_capabilities() -> set[PlatformRequirement]:
    """Detect security capabilities available on Android.

    Returns:
        Set of PlatformRequirement that are available
    """
    capabilities: set[PlatformRequirement] = set()

    # Android Keystore is always available on Android 4.3+
    # We're targeting Android 7+ (API 24) so this is safe
    capabilities.add(PlatformRequirement.ANDROID_KEYSTORE)

    # Google Play Integrity requires Google Play Services
    # Check if we have the marker that Play Services is available
    if os.getenv("GOOGLE_PLAY_SERVICES_AVAILABLE", "").lower() == "true":
        capabilities.add(PlatformRequirement.ANDROID_PLAY_INTEGRITY)

    # Native Google auth is available if Play Services is available
    # AND we have a valid Google ID token
    google_token = os.getenv("CIRIS_BILLING_GOOGLE_ID_TOKEN") or os.getenv("GOOGLE_ID_TOKEN")
    if google_token:
        capabilities.add(PlatformRequirement.GOOGLE_NATIVE_AUTH)

    # CIRIS proxy is available if we're configured to use it
    llm_base_url = os.getenv("LLM_BASE_URL", "")
    if "ciris" in llm_base_url.lower():
        capabilities.add(PlatformRequirement.CIRIS_PROXY)

    return capabilities


def _detect_ios_capabilities() -> set[PlatformRequirement]:
    """Detect security capabilities available on iOS.

    Returns:
        Set of PlatformRequirement that are available
    """
    capabilities: set[PlatformRequirement] = set()

    # iOS always has Secure Enclave on A7+ chips (iPhone 5s and later)
    capabilities.add(PlatformRequirement.SECURE_ENCLAVE)

    # App Attest is available on iOS 14+
    # This would need to be signaled by the native app
    if os.getenv("IOS_APP_ATTEST_AVAILABLE", "").lower() == "true":
        capabilities.add(PlatformRequirement.IOS_APP_ATTEST)

    # DeviceCheck is available on iOS 11+
    if os.getenv("IOS_DEVICE_CHECK_AVAILABLE", "").lower() == "true":
        capabilities.add(PlatformRequirement.IOS_DEVICE_CHECK)

    # Native Apple auth
    if os.getenv("APPLE_ID_TOKEN"):
        capabilities.add(PlatformRequirement.APPLE_NATIVE_AUTH)

    return capabilities


def _detect_desktop_capabilities() -> set[PlatformRequirement]:
    """Detect security capabilities available on desktop platforms.

    Returns:
        Set of PlatformRequirement that are available
    """
    capabilities: set[PlatformRequirement] = set()

    # Check for TPM (Trusted Platform Module)
    # On Linux, check for /dev/tpm0
    # On Windows, would check via WMI
    if sys.platform.startswith("linux"):
        if Path("/dev/tpm0").exists() or Path("/dev/tpmrm0").exists():
            capabilities.add(PlatformRequirement.TPM)

    # Check for HSM (Hardware Security Module)
    # This would typically be configured via environment variable
    if os.getenv("HSM_AVAILABLE", "").lower() == "true":
        capabilities.add(PlatformRequirement.HSM)

    # DPoP support - available if the client supports it
    # This is a protocol capability, not hardware
    if os.getenv("DPOP_ENABLED", "").lower() == "true":
        capabilities.add(PlatformRequirement.DPOP)

    # mTLS support
    if os.getenv("MTLS_CERT_PATH") and os.getenv("MTLS_KEY_PATH"):
        capabilities.add(PlatformRequirement.MTLS)

    return capabilities


# ============================================================================
# Main Detection Function
# ============================================================================


@lru_cache(maxsize=1)
def detect_platform_capabilities() -> PlatformCapabilities:
    """Detect current platform and its security capabilities.

    This function is cached since platform capabilities don't change
    during runtime (except for authentication state, which is handled
    separately via refresh_auth_state()).

    Returns:
        PlatformCapabilities object with detected platform and capabilities
    """
    platform = get_platform_name()

    # Detect platform-specific capabilities
    if platform == "android":
        capabilities = _detect_android_capabilities()
    elif platform == "ios":
        capabilities = _detect_ios_capabilities()
    else:
        capabilities = _detect_desktop_capabilities()

    # Build the capabilities object
    platform_caps = PlatformCapabilities(
        platform=platform,
        capabilities=capabilities,
        # Android-specific
        play_integrity_available=PlatformRequirement.ANDROID_PLAY_INTEGRITY in capabilities,
        hardware_keystore_available=PlatformRequirement.ANDROID_KEYSTORE in capabilities,
        google_native_auth_available=PlatformRequirement.GOOGLE_NATIVE_AUTH in capabilities,
        # iOS-specific
        app_attest_available=PlatformRequirement.IOS_APP_ATTEST in capabilities,
        apple_native_auth_available=PlatformRequirement.APPLE_NATIVE_AUTH in capabilities,
        # Desktop-specific
        tpm_available=PlatformRequirement.TPM in capabilities,
        # Token state
        has_valid_device_token=bool(
            os.getenv("CIRIS_BILLING_GOOGLE_ID_TOKEN") or os.getenv("GOOGLE_ID_TOKEN") or os.getenv("APPLE_ID_TOKEN")
        ),
        token_binding_method=_get_token_binding_method(capabilities),
    )

    logger.info(
        "[PLATFORM] Detected platform: %s, capabilities: %s",
        platform,
        [c.value for c in capabilities],
    )

    return platform_caps


def _get_token_binding_method(capabilities: set[PlatformRequirement]) -> Optional[str]:
    """Determine the token binding method based on capabilities.

    Args:
        capabilities: Set of available platform requirements

    Returns:
        Token binding method name or None
    """
    if PlatformRequirement.ANDROID_PLAY_INTEGRITY in capabilities:
        return "play_integrity"
    if PlatformRequirement.IOS_APP_ATTEST in capabilities:
        return "app_attest"
    if PlatformRequirement.DPOP in capabilities:
        return "dpop"
    if PlatformRequirement.MTLS in capabilities:
        return "mtls"
    return None


def refresh_auth_state() -> PlatformCapabilities:
    """Refresh authentication-related capabilities.

    Call this after authentication state changes (login, logout, token refresh)
    to update the cached platform capabilities.

    Returns:
        Updated PlatformCapabilities
    """
    # Clear the cache
    detect_platform_capabilities.cache_clear()
    # Re-detect
    return detect_platform_capabilities()


def check_requirements(requirements: list[PlatformRequirement]) -> tuple[bool, list[PlatformRequirement]]:
    """Check if platform requirements are satisfied.

    Args:
        requirements: List of requirements to check

    Returns:
        Tuple of (all_satisfied, missing_requirements)
    """
    capabilities = detect_platform_capabilities()
    missing = capabilities.missing_requirements(requirements)
    return len(missing) == 0, missing


# ============================================================================
# Re-exports (for convenience - use this module as single import point)
# ============================================================================

# Import from path_resolution to provide a single import point for platform detection
from ciris_engine.logic.utils.path_resolution import is_development_mode, is_managed

__all__ = [
    # Core detection (is_android imported from path_resolution)
    "is_android",
    "is_ios",
    "get_platform_name",
    "detect_platform_capabilities",
    "refresh_auth_state",
    "check_requirements",
    # Re-exported from path_resolution for convenience
    "is_managed",
    "is_development_mode",
]
