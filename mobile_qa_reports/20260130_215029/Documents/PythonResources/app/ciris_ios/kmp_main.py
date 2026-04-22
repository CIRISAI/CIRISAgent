"""
KMP iOS entrypoint for CIRIS.

This module starts the CIRIS runtime without Toga (which requires main thread signal handling).
For use with Kotlin Multiplatform where the UI is Compose-based.

Entry point: python -m ciris_ios.kmp_main
"""

import sys

# Import compatibility shims FIRST before any CIRIS imports
import ciris_ios.crypto_compat  # noqa: F401 - Provides asymmetric.types for old cryptography

from ciris_ios.ios_main import (
    run_startup_checks,
    setup_ios_environment,
    start_mobile_runtime,
)


def main():
    """Main entrypoint for KMP iOS app - runs checks and starts runtime directly."""
    print("[KMP] CIRIS iOS - KMP Runtime")
    print("[KMP] Running without Toga (UI handled by Compose)")
    print("")

    if run_startup_checks():
        setup_ios_environment()
        try:
            import asyncio
            asyncio.run(start_mobile_runtime())
        except KeyboardInterrupt:
            print("[KMP] Server stopped by user")
        except Exception as e:
            print(f"[KMP] Server error: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    main()
