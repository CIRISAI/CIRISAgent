"""
Version module for CIRIS iOS app.

This provides a static version identifier for the packaged iOS build.
The version hash is computed at build time from the main repository.
"""

# Static version - updated at build time by the iOS build process
__version__ = "ios-2.2.8"


def get_version() -> str:
    """Return the version string for this iOS build."""
    return __version__
