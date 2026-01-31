"""
KMP iOS entrypoint for CIRIS.

This module starts the CIRIS runtime without Toga (which requires main thread signal handling).
For use with Kotlin Multiplatform where the UI is Compose-based.

Supports restart signaling:
- Swift writes .restart_signal file when app resumes and server is dead
- This module detects the signal and restarts the runtime
- Allows recovery from iOS background suspension without app restart

Entry point: python -m ciris_ios.kmp_main
"""

import sys
import os
import time
from pathlib import Path

# Import compatibility shims FIRST before any CIRIS imports
import ciris_ios.crypto_compat  # noqa: F401 - Provides asymmetric.types for old cryptography

from ciris_ios.ios_main import (
    run_startup_checks,
    setup_ios_environment,
    start_mobile_runtime,
)


def get_restart_signal_path() -> Path:
    """Get path to the restart signal file."""
    home = Path.home()
    return home / "Documents" / "ciris" / ".restart_signal"


def check_restart_signal() -> bool:
    """Check if restart signal file exists."""
    signal_path = get_restart_signal_path()
    return signal_path.exists()


def clear_restart_signal():
    """Clear the restart signal file."""
    signal_path = get_restart_signal_path()
    try:
        if signal_path.exists():
            signal_path.unlink()
            print("[KMP] Cleared restart signal file")
    except Exception as e:
        print(f"[KMP] Warning: Could not clear restart signal: {e}")


def write_ready_signal():
    """Write a ready signal file to indicate server is up."""
    ready_path = Path.home() / "Documents" / "ciris" / ".server_ready"
    try:
        ready_path.write_text(str(time.time()))
    except Exception as e:
        print(f"[KMP] Warning: Could not write ready signal: {e}")


def clear_ready_signal():
    """Clear the ready signal file."""
    ready_path = Path.home() / "Documents" / "ciris" / ".server_ready"
    try:
        if ready_path.exists():
            ready_path.unlink()
    except Exception:
        pass


class RestartRequested(Exception):
    """Exception raised when a restart is requested."""
    pass


async def start_mobile_runtime_with_watchdog():
    """Start runtime with a watchdog that checks for restart signals.

    This wraps the normal runtime with periodic checks for the restart signal file.
    When detected, raises RestartRequested to trigger a clean restart.
    """
    import asyncio

    # Import runtime components
    from ciris_engine.logic.adapters.api.config import APIAdapterConfig
    from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
    from ciris_engine.schemas.runtime.adapter_management import AdapterConfig
    from ciris_engine.logic.utils.path_resolution import get_ciris_home, get_data_dir
    from ciris_engine.schemas.config.essential import DatabaseConfig, EssentialConfig, SecurityConfig

    print("[KMP] Starting runtime with restart watchdog...", flush=True)

    # Clear any pending restart signal from previous run
    clear_restart_signal()

    # Get paths
    ciris_home = get_ciris_home()
    data_dir = get_data_dir()

    # Create configs (same as start_mobile_runtime)
    security_config = SecurityConfig(
        secrets_key_path=ciris_home / ".ciris_keys",
        audit_key_path=ciris_home / "audit_keys",
    )
    db_config = DatabaseConfig(
        main_db=data_dir / "ciris_engine.db",
        secrets_db=data_dir / "secrets.db",
        audit_db=data_dir / "ciris_audit.db",
    )
    app_config = EssentialConfig(
        security=security_config,
        database=db_config,
        template_directory=ciris_home / "ciris_templates",
    )

    api_config = APIAdapterConfig()
    api_config.host = "127.0.0.1"
    api_config.port = 8080

    adapter_configs = {"api": AdapterConfig(adapter_type="api", enabled=True, settings=api_config.model_dump())}
    startup_channel_id = api_config.get_home_channel_id(api_config.host, api_config.port)

    # Create runtime
    runtime = CIRISRuntime(
        adapter_types=["api"],
        essential_config=app_config,
        startup_channel_id=startup_channel_id,
        adapter_configs=adapter_configs,
        interactive=False,
        host="127.0.0.1",
        port=8080,
    )

    # Initialize
    print("[KMP] Initializing CIRIS services...")
    await runtime.initialize()
    print("[KMP] CIRIS runtime initialized")

    # Write ready signal
    write_ready_signal()

    # Watchdog task to check for restart signal
    async def restart_watchdog():
        """Check for restart signal every second."""
        while True:
            await asyncio.sleep(1.0)
            if check_restart_signal():
                print("[KMP] Restart signal detected!")
                clear_restart_signal()
                # Request graceful shutdown
                runtime.request_shutdown("Restart signal from iOS")
                return

    # Run runtime with watchdog
    watchdog_task = asyncio.create_task(restart_watchdog())

    try:
        await runtime.run()
    except Exception as e:
        print(f"[KMP] Runtime error: {e}")
        raise
    finally:
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass
        clear_ready_signal()
        await runtime.shutdown()
        print("[KMP] Runtime shutdown complete")

    # If we get here, check if restart was requested
    if check_restart_signal():
        clear_restart_signal()
        raise RestartRequested()


def main():
    """Main entrypoint for KMP iOS app - runs checks and starts runtime with restart support."""
    print("[KMP] CIRIS iOS - KMP Runtime")
    print("[KMP] Running without Toga (UI handled by Compose)")
    print("[KMP] Restart signaling enabled")
    print("")

    # CRITICAL: Set up iOS environment FIRST, before any checks
    # This sets CIRIS_HOME which is needed for database path resolution
    setup_ios_environment()

    if not run_startup_checks():
        # Startup checks failed - keep thread alive so Swift can read status
        print("[KMP] Startup checks failed - runtime will not start")
        print("[KMP] Check startup_status.json for details")
        return

    # Run with restart loop
    restart_count = 0
    max_restarts = 10  # Prevent infinite restart loops

    while restart_count < max_restarts:
        try:
            import asyncio
            print(f"[KMP] Starting runtime (restart count: {restart_count})")
            asyncio.run(start_mobile_runtime_with_watchdog())
            print("[KMP] Runtime exited normally")
            break  # Clean exit, don't restart

        except RestartRequested:
            restart_count += 1
            print(f"[KMP] Restart requested, restarting... (count: {restart_count})")
            # Small delay before restart
            time.sleep(1.0)
            continue

        except KeyboardInterrupt:
            print("[KMP] Server stopped by user")
            break

        except Exception as e:
            print(f"[KMP] Server error: {e}")
            import traceback
            traceback.print_exc()

            # Check if restart was signaled during error
            if check_restart_signal():
                restart_count += 1
                clear_restart_signal()
                print(f"[KMP] Restart signal found after error, restarting... (count: {restart_count})")
                time.sleep(1.0)
                continue
            else:
                # Real error, don't restart
                raise

    if restart_count >= max_restarts:
        print(f"[KMP] Max restarts ({max_restarts}) reached, giving up")


if __name__ == "__main__":
    main()
