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

    # CRITICAL: Set up iOS environment FIRST, before any checks
    # This sets CIRIS_HOME which is needed for database path resolution
    setup_ios_environment()

    if run_startup_checks():
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
    else:
        # Startup checks failed - keep thread alive so Swift can read status
        print("[KMP] Startup checks failed - runtime will not start")
        print("[KMP] Check startup_status.json for details")
        # Thread will exit, Swift will detect all_passed=false in status file


if __name__ == "__main__":
    main()
