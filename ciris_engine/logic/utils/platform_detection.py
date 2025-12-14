"""Platform detection utilities for CIRIS."""

import os

from ciris_engine.schemas.platform import PlatformCapabilities


def detect_platform_capabilities() -> PlatformCapabilities:
    """
    Detect the current platform's capabilities.

    On Android, this checks for Google Play Services, Play Integrity API,
    and Android Keystore availability. On other platforms, returns defaults.
    """
    is_android = "ANDROID_DATA" in os.environ

    if not is_android:
        # Non-Android platform - return minimal capabilities
        return PlatformCapabilities(
            platform="server",
            is_android=False,
            google_native_auth_available=False,
            play_integrity_available=False,
            keystore_available=False,
        )

    # Android platform - check for available services
    # These checks are performed at runtime on Android
    google_auth_available = False
    play_integrity_available = False
    keystore_available = False

    try:
        # Check for Google Sign-In availability
        from jnius import autoclass

        GoogleSignIn = autoclass("com.google.android.gms.auth.api.signin.GoogleSignIn")
        google_auth_available = GoogleSignIn is not None
    except Exception:
        pass

    try:
        # Check for Play Integrity API
        from jnius import autoclass

        IntegrityManager = autoclass(
            "com.google.android.play.core.integrity.IntegrityManagerFactory"
        )
        play_integrity_available = IntegrityManager is not None
    except Exception:
        pass

    try:
        # Check for Android Keystore
        from jnius import autoclass

        KeyStore = autoclass("java.security.KeyStore")
        ks = KeyStore.getInstance("AndroidKeyStore")
        keystore_available = ks is not None
    except Exception:
        pass

    return PlatformCapabilities(
        platform="android",
        is_android=True,
        google_native_auth_available=google_auth_available,
        play_integrity_available=play_integrity_available,
        keystore_available=keystore_available,
    )
