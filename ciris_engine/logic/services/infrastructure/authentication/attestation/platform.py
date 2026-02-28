"""Platform detection helpers for attestation.

These functions detect the runtime platform (Android, iOS, mobile)
for platform-specific attestation behavior.
"""

import os


def is_android() -> bool:
    """Check if running on Android platform.

    Returns:
        True if ANDROID_ROOT environment variable is set
    """
    return os.environ.get("ANDROID_ROOT") is not None


def is_ios() -> bool:
    """Check if running on iOS platform.

    Returns:
        True if iOS framework or static link environment variables are set
    """
    return (
        os.environ.get("CIRIS_IOS_FRAMEWORK_PATH") is not None
        or os.environ.get("CIRIS_IOS_STATIC_LINK") is not None
    )


def is_mobile() -> bool:
    """Check if running on a mobile platform (Android or iOS).

    Returns:
        True if running on Android or iOS
    """
    return is_android() or is_ios()
