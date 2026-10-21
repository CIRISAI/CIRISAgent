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



def _has_proxy_token() -> bool:
    """Any OAuth proxy token, under any of the handshake names.

    These presence checks used to ask only about the Google variable, so a
    client that had refreshed under a different one looked exactly like a user
    who never signed in — the capability was withdrawn while a good token sat
    right there in the environment.
    """
    from ciris_engine.logic.utils.token_handshake import has_proxy_token

    return has_proxy_token()


def is_ios() -> bool:
    """Detect if running on iOS platform.

    Checks multiple indicators:
    - sys.platform == 'ios' (set by BeeWare/Briefcase)
    - Running under BeeWare with iOS-specific paths

    Returns:
        True if running on iOS
    """
    # BeeWare/Briefcase sets sys.platform to 'ios'
    if sys.platform == "ios":
        return True

    # Check for iOS-specific paths
    if sys.platform == "darwin":
        # Check for iOS Simulator or device paths
        home = str(Path.home())
        if "CoreSimulator/Devices" in home or "/var/mobile" in home:
            return True

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


# Platform names that denote a full desktop/server host: a real filesystem, a
# shell, and a user who installed the agent deliberately. Deliberately a
# positive allow-list -- anything not named here (android, ios, unknown) is
# treated as NOT desktop, so an unrecognized platform loses capability rather
# than gaining it.
DESKTOP_PLATFORM_NAMES = frozenset({"linux", "macos", "windows"})


def is_desktop() -> bool:
    """Detect if running on a desktop/server host rather than a mobile device.

    Used to gate host-level capabilities (shell execution, file writes) that are
    meaningful on a desktop install and meaningless-or-worse inside a sandboxed
    mobile app. See ``FSD/CLI_TOOLS_DESKTOP.md``.

    **Fails closed.** ``get_platform_name()`` returns ``"unknown"`` for anything
    it does not positively recognize, and ``"unknown"`` is not in
    :data:`DESKTOP_PLATFORM_NAMES`, so an unrecognized platform gets the mobile
    (no-shell) answer. Android is recognized via ``ANDROID_ROOT`` /
    ``ANDROID_DATA`` / ``sys.getandroidapilevel`` (Chaquopy) / ``/data/data``;
    iOS via ``sys.platform == 'ios'`` or a simulator/device home path.

    Returns:
        True only on a positively-identified desktop platform.
    """
    return get_platform_name() in DESKTOP_PLATFORM_NAMES


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
    # On Android, we assume Play Services is available since:
    # 1. Our app is distributed via Google Play Store
    # 2. We require Google Sign-In (which needs Play Services)
    # 3. Non-GMS devices wouldn't work with our auth flow anyway
    # Also allow explicit env var for testing/override
    if os.getenv("GOOGLE_PLAY_SERVICES_AVAILABLE", "true").lower() == "true":
        capabilities.add(PlatformRequirement.ANDROID_PLAY_INTEGRITY)

    # Native Google auth is available if Play Services is available
    # AND we have a valid Google ID token
    google_token = _has_proxy_token() or bool(os.getenv("GOOGLE_ID_TOKEN"))
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


def _detect_unknown_capabilities() -> set[PlatformRequirement]:
    """Capabilities for a host we could not positively identify: none.

    ``get_platform_name()`` returns ``"unknown"`` only after android, ios and
    the three desktop platforms have all failed to match, so reaching here means
    the runtime genuinely does not know where it is. Every capability in this
    module is a claim about the host — that a Secure Enclave exists, that a TPM
    is reachable, that shell access is meaningful. None of those can be asserted
    about an unidentified machine, so the honest answer is the empty set.

    Notably this withholds ``DESKTOP_CLI``, which previously came free with the
    desktop fallthrough (#948). ``is_desktop()`` in this same file already fails
    closed by testing membership in ``DESKTOP_PLATFORM_NAMES`` rather than
    "not one of the platforms I recognize"; this brings capability detection
    onto that footing so the two cannot disagree.
    """
    return set()


def _detect_desktop_capabilities() -> set[PlatformRequirement]:
    """Detect security capabilities available on desktop platforms.

    Returns:
        Set of PlatformRequirement that are available
    """
    capabilities: set[PlatformRequirement] = set()

    # Desktop CLI tools are available on desktop but not mobile
    capabilities.add(PlatformRequirement.DESKTOP_CLI)

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
    # Every branch is a POSITIVE match. The desktop arm used to be a bare
    # `else`, so a host the runtime could not classify was handed the desktop
    # capability set — including DESKTOP_CLI, the predicate that gates shell
    # execution and file writes (#948). Unknown is now its own branch with an
    # empty set, which is what `is_desktop()` has always done a few lines up.
    if platform == "android":
        capabilities = _detect_android_capabilities()
    elif platform == "ios":
        capabilities = _detect_ios_capabilities()
    elif platform in DESKTOP_PLATFORM_NAMES:
        capabilities = _detect_desktop_capabilities()
    else:
        capabilities = _detect_unknown_capabilities()

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
            _has_proxy_token() or os.getenv("GOOGLE_ID_TOKEN") or os.getenv("APPLE_ID_TOKEN")
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
    "is_desktop",
    "DESKTOP_PLATFORM_NAMES",
    "get_platform_name",
    "detect_platform_capabilities",
    "refresh_auth_state",
    "check_requirements",
    # Re-exported from path_resolution for convenience
    "is_managed",
    "is_development_mode",
]
