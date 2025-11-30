"""
Version module for CIRIS Android app.

This provides a static version identifier for the packaged Android build.
The version hash is computed at build time from the main repository.
"""

# Static version - updated at build time by the Android build process
# This avoids file-system hashing logic that doesn't work in the Android package
__version__ = "android-1.0.0"


def get_version() -> str:
    """Return the version string for this Android build."""
    return __version__
