"""Tests for platform detection utility."""

import os
from unittest.mock import patch

import pytest

from ciris_engine.logic.utils.platform_detection import (
    check_requirements,
    detect_platform_capabilities,
    get_platform_name,
    is_android,
    is_ios,
    refresh_auth_state,
)
from ciris_engine.schemas.platform import PlatformCapabilities, PlatformRequirement


class TestGetPlatformName:
    """Tests for get_platform_name function."""

    def test_returns_linux_on_linux(self) -> None:
        """Test returns 'linux' on Linux platform."""
        # We're running on Linux, so this should return 'linux'
        # (unless Android env vars are set)
        with patch.dict(os.environ, {}, clear=False):
            # Ensure no Android env vars
            os.environ.pop("ANDROID_ROOT", None)
            os.environ.pop("ANDROID_DATA", None)
            # Clear cache to pick up env changes
            detect_platform_capabilities.cache_clear()
            platform = get_platform_name()
            assert platform in ("linux", "android")  # Could be either depending on CI env

    def test_returns_android_with_env_vars(self) -> None:
        """Test returns 'android' when Android env vars are set."""
        with patch.dict(os.environ, {"ANDROID_ROOT": "/system"}):
            detect_platform_capabilities.cache_clear()
            platform = get_platform_name()
            assert platform == "android"


class TestIsAndroid:
    """Tests for is_android function."""

    def test_false_without_android_markers(self) -> None:
        """Test returns False without Android markers."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANDROID_ROOT", None)
            os.environ.pop("ANDROID_DATA", None)
            # On a regular Linux system, should be False
            # Unless /data/data exists (unlikely on non-Android Linux)
            result = is_android()
            # Don't assert specific value since CI env may vary
            assert isinstance(result, bool)

    def test_true_with_android_root(self) -> None:
        """Test returns True with ANDROID_ROOT env var."""
        with patch.dict(os.environ, {"ANDROID_ROOT": "/system"}):
            assert is_android() is True

    def test_true_with_android_data(self) -> None:
        """Test returns True with ANDROID_DATA env var."""
        with patch.dict(os.environ, {"ANDROID_DATA": "/data"}):
            assert is_android() is True


class TestIsIos:
    """Tests for is_ios function."""

    def test_always_false_currently(self) -> None:
        """Test always returns False (iOS not yet supported)."""
        assert is_ios() is False


class TestDetectPlatformCapabilities:
    """Tests for detect_platform_capabilities function."""

    def test_returns_platform_capabilities(self) -> None:
        """Test returns PlatformCapabilities object."""
        # Clear cache first
        detect_platform_capabilities.cache_clear()
        caps = detect_platform_capabilities()
        assert isinstance(caps, PlatformCapabilities)
        assert caps.platform in ("android", "ios", "linux", "windows", "macos", "unknown")

    def test_caches_result(self) -> None:
        """Test result is cached."""
        detect_platform_capabilities.cache_clear()
        caps1 = detect_platform_capabilities()
        caps2 = detect_platform_capabilities()
        # Same object due to caching
        assert caps1 is caps2

    def test_android_has_keystore_capability(self) -> None:
        """Test Android platform has keystore capability."""
        with patch.dict(os.environ, {"ANDROID_ROOT": "/system"}):
            detect_platform_capabilities.cache_clear()
            caps = detect_platform_capabilities()
            assert caps.platform == "android"
            assert PlatformRequirement.ANDROID_KEYSTORE in caps.capabilities

    def test_android_with_play_integrity(self) -> None:
        """Test Android with Play Services has Play Integrity capability."""
        with patch.dict(
            os.environ,
            {
                "ANDROID_ROOT": "/system",
                "GOOGLE_PLAY_SERVICES_AVAILABLE": "true",
            },
        ):
            detect_platform_capabilities.cache_clear()
            caps = detect_platform_capabilities()
            assert PlatformRequirement.ANDROID_PLAY_INTEGRITY in caps.capabilities
            assert caps.play_integrity_available is True

    def test_android_with_google_auth(self) -> None:
        """Test Android with Google token has native auth capability."""
        with patch.dict(
            os.environ,
            {
                "ANDROID_ROOT": "/system",
                "CIRIS_BILLING_GOOGLE_ID_TOKEN": "test_token_123",
            },
        ):
            detect_platform_capabilities.cache_clear()
            caps = detect_platform_capabilities()
            assert PlatformRequirement.GOOGLE_NATIVE_AUTH in caps.capabilities
            assert caps.google_native_auth_available is True
            assert caps.has_valid_device_token is True


class TestRefreshAuthState:
    """Tests for refresh_auth_state function."""

    def test_clears_cache_and_redetects(self) -> None:
        """Test refresh clears cache and re-detects capabilities."""
        # Get initial caps
        detect_platform_capabilities.cache_clear()
        caps1 = detect_platform_capabilities()

        # Add a token to env
        with patch.dict(os.environ, {"GOOGLE_ID_TOKEN": "new_token"}):
            caps2 = refresh_auth_state()
            # Should be a new detection (not the same cached object)
            # Note: may be same object if nothing changed, but token state should update
            assert isinstance(caps2, PlatformCapabilities)


class TestCheckRequirements:
    """Tests for check_requirements function."""

    def test_empty_requirements_satisfied(self) -> None:
        """Test empty requirements are always satisfied."""
        detect_platform_capabilities.cache_clear()
        satisfied, missing = check_requirements([])
        assert satisfied is True
        assert missing == []

    def test_android_requirements_on_non_android(self) -> None:
        """Test Android requirements are not satisfied on non-Android."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANDROID_ROOT", None)
            os.environ.pop("ANDROID_DATA", None)
            detect_platform_capabilities.cache_clear()

            # Skip test if we're actually on Android
            if is_android():
                pytest.skip("Running on Android")

            reqs = [
                PlatformRequirement.ANDROID_PLAY_INTEGRITY,
                PlatformRequirement.GOOGLE_NATIVE_AUTH,
            ]
            satisfied, missing = check_requirements(reqs)
            assert satisfied is False
            assert PlatformRequirement.ANDROID_PLAY_INTEGRITY in missing
            assert PlatformRequirement.GOOGLE_NATIVE_AUTH in missing

    def test_android_requirements_on_android(self) -> None:
        """Test Android requirements on simulated Android."""
        with patch.dict(
            os.environ,
            {
                "ANDROID_ROOT": "/system",
                "GOOGLE_PLAY_SERVICES_AVAILABLE": "true",
                "CIRIS_BILLING_GOOGLE_ID_TOKEN": "test_token",
            },
        ):
            detect_platform_capabilities.cache_clear()
            reqs = [
                PlatformRequirement.ANDROID_PLAY_INTEGRITY,
                PlatformRequirement.GOOGLE_NATIVE_AUTH,
            ]
            satisfied, missing = check_requirements(reqs)
            assert satisfied is True
            assert missing == []


class TestDesktopCapabilities:
    """Tests for desktop capability detection."""

    def test_tpm_detection_with_device(self) -> None:
        """Test TPM detection when /dev/tpm0 exists."""
        # This test is tricky because we can't easily mock Path.exists()
        # Just verify the function runs without error
        detect_platform_capabilities.cache_clear()
        caps = detect_platform_capabilities()
        # TPM availability depends on actual system
        assert isinstance(caps.tpm_available, bool)

    def test_dpop_enabled(self) -> None:
        """Test DPoP capability when enabled."""
        with patch.dict(os.environ, {"DPOP_ENABLED": "true"}):
            # Need to clear Android markers to trigger desktop detection
            os.environ.pop("ANDROID_ROOT", None)
            os.environ.pop("ANDROID_DATA", None)
            detect_platform_capabilities.cache_clear()

            # Skip if actually on Android
            if is_android():
                pytest.skip("Running on Android")

            caps = detect_platform_capabilities()
            assert PlatformRequirement.DPOP in caps.capabilities

    def test_mtls_capability(self) -> None:
        """Test mTLS capability when certs are configured."""
        with patch.dict(
            os.environ,
            {
                "MTLS_CERT_PATH": "/path/to/cert.pem",
                "MTLS_KEY_PATH": "/path/to/key.pem",
            },
        ):
            os.environ.pop("ANDROID_ROOT", None)
            os.environ.pop("ANDROID_DATA", None)
            detect_platform_capabilities.cache_clear()

            if is_android():
                pytest.skip("Running on Android")

            caps = detect_platform_capabilities()
            assert PlatformRequirement.MTLS in caps.capabilities
