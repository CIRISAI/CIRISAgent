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

import os
import sys
import time
from pathlib import Path
from typing import Optional

# =============================================================================
# CONSTANTS
# =============================================================================

_MSG_IMPORTING_RUNTIME = "Importing runtime components"

# =============================================================================
# PHASE 1: EARLY INIT - Before any complex imports
# =============================================================================


def _early_log(msg: str):
    """Early logging before logging system is initialized."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [EARLY] {msg}", flush=True)


def _get_ciris_dir() -> Path:
    """Get the ciris directory, creating if needed."""
    ciris_dir = Path.home() / "Documents" / "ciris"
    ciris_dir.mkdir(parents=True, exist_ok=True)
    return ciris_dir


def _write_early_status(phase: str, status: str, error: Optional[str] = None):
    """Write early status for Swift to read."""
    import json

    status_file = _get_ciris_dir() / "runtime_status.json"
    data = {"phase": phase, "status": status, "timestamp": time.time(), "error": error}
    try:
        with open(status_file, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


_early_log("=== KMP MAIN STARTING ===")
_write_early_status("EARLY_INIT", "starting")

# =============================================================================
# PHASE 2: COMPATIBILITY SHIMS
# =============================================================================

_early_log("Phase 2: Loading compatibility shims...")
try:
    import ciris_ios.crypto_compat  # noqa: F401

    _early_log("  [OK] crypto_compat loaded")
except Exception as e:
    _early_log(f"  [FAIL] crypto_compat: {e}")
    _write_early_status("COMPAT_SHIMS", "failed", str(e))
    raise

# =============================================================================
# PHASE 3: IOS ENVIRONMENT SETUP
# =============================================================================

_early_log("Phase 3: Setting up iOS environment...")
try:
    from ciris_ios.ios_main import run_startup_checks, setup_ios_environment

    _early_log("  [OK] ios_main imports loaded")
except Exception as e:
    _early_log(f"  [FAIL] ios_main imports: {e}")
    _write_early_status("IOS_MAIN_IMPORT", "failed", str(e))
    raise

# =============================================================================
# PHASE 4: LOGGING SYSTEM
# =============================================================================

_early_log("Phase 4: Initializing logging system...")
try:
    from ciris_ios.ios_logger import get_log_dir, init_logging, log_phase, log_step, write_status_file

    _log = init_logging("kmp.main")
    _early_log("  [OK] Logging system initialized")
except Exception as e:
    _early_log(f"  [FAIL] Logging system: {e}")
    # Fall back to simple logging
    import logging

    _log = logging.getLogger("ciris.kmp.main")
    _log.setLevel(logging.DEBUG)
    _log.addHandler(logging.StreamHandler(sys.stdout))

    def log_phase(logger, phase, status="START", details=""):
        logger.info(f"PHASE: {phase} [{status}] {details}")

    def log_step(logger, step, status="...", details=""):
        logger.info(f"  [{status}] {step}: {details}")

    def write_status_file(status):
        _write_early_status(status.get("phase", "unknown"), status.get("status", "unknown"))

    def get_log_dir():
        return _get_ciris_dir() / "logs"


# =============================================================================
# SIGNAL FILE UTILITIES
# =============================================================================


def get_restart_signal_path() -> Path:
    """Get path to the restart signal file."""
    return _get_ciris_dir() / ".restart_signal"


def check_restart_signal() -> bool:
    """Check if restart signal file exists."""
    return get_restart_signal_path().exists()


def clear_restart_signal():
    """Clear the restart signal file."""
    signal_path = get_restart_signal_path()
    try:
        if signal_path.exists():
            signal_path.unlink()
            _log.info("Cleared restart signal file")
    except Exception as e:
        _log.warning(f"Could not clear restart signal: {e}")


def write_ready_signal():
    """Write a ready signal file to indicate server is up."""
    ready_path = _get_ciris_dir() / ".server_ready"
    try:
        ready_path.write_text(str(time.time()))
        _log.info(f"Wrote server ready signal: {ready_path}")
    except Exception as e:
        _log.warning(f"Could not write ready signal: {e}")


def clear_ready_signal():
    """Clear the ready signal file."""
    ready_path = _get_ciris_dir() / ".server_ready"
    try:
        if ready_path.exists():
            ready_path.unlink()
    except Exception:
        pass


# =============================================================================
# WATCHDOG THREAD
# =============================================================================

# Global state for watchdog coordination
_restart_requested = False
_event_loop = None
_watchdog_log = None


def watchdog_thread_func():
    """
    Background thread that monitors for restart signal file.

    This runs OUTSIDE of asyncio so it can detect the signal even when
    the event loop is frozen/stuck after iOS suspension.
    """
    global _restart_requested, _event_loop, _watchdog_log

    if _watchdog_log is None:
        _watchdog_log = init_logging("kmp.watchdog")

    _watchdog_log.info("Watchdog thread started")
    _watchdog_log.info(f"  Signal file: {get_restart_signal_path()}")

    check_count = 0
    while True:
        time.sleep(1.0)
        check_count += 1

        # Log heartbeat every 30 seconds
        if check_count % 30 == 0:
            _watchdog_log.debug(f"Watchdog heartbeat (checks: {check_count})")

        if check_restart_signal():
            _watchdog_log.warning("!!! RESTART SIGNAL DETECTED !!!")
            clear_restart_signal()
            _restart_requested = True

            # Try to stop the event loop if it exists
            if _event_loop is not None:
                try:
                    _watchdog_log.info("Signaling event loop to stop...")
                    _event_loop.call_soon_threadsafe(_event_loop.stop)
                    _watchdog_log.info("Event loop stop signal sent")
                except Exception as e:
                    _watchdog_log.error(f"Could not stop event loop: {e}")

            # Exit watchdog - will be restarted with new runtime
            break

    _watchdog_log.info("Watchdog thread exiting")


def start_watchdog_thread():
    """Start the watchdog thread as a daemon."""
    import threading

    thread = threading.Thread(target=watchdog_thread_func, daemon=True, name="KMPWatchdog")
    thread.start()
    _log.info(f"Started watchdog thread: {thread.name}")
    return thread


# =============================================================================
# RUNTIME MANAGEMENT
# =============================================================================


async def start_mobile_runtime_with_watchdog():
    """
    Start runtime with a watchdog that checks for restart signals.

    This wraps the normal runtime with periodic checks for the restart signal file.
    When detected, raises RestartRequested to trigger a clean restart.
    """
    import asyncio

    runtime_log = init_logging("kmp.runtime")
    log_phase(runtime_log, "RUNTIME_INIT", "START")

    write_status_file({"phase": "RUNTIME_INIT", "status": "importing"})

    # Import runtime components
    log_step(runtime_log, _MSG_IMPORTING_RUNTIME, "...")
    try:
        from ciris_engine.logic.adapters.api.config import APIAdapterConfig
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
        from ciris_engine.logic.utils.path_resolution import get_ciris_home, get_data_dir
        from ciris_engine.schemas.config.essential import DatabaseConfig, EssentialConfig, SecurityConfig
        from ciris_engine.schemas.runtime.adapter_management import AdapterConfig

        log_step(runtime_log, _MSG_IMPORTING_RUNTIME, "OK")
    except Exception as e:
        log_step(runtime_log, _MSG_IMPORTING_RUNTIME, "FAIL", str(e))
        write_status_file({"phase": "RUNTIME_INIT", "status": "failed", "error": str(e)})
        raise

    # Clear any pending restart signal from previous run
    clear_restart_signal()

    # Get paths
    log_step(runtime_log, "Resolving paths", "...")
    ciris_home = get_ciris_home()
    data_dir = get_data_dir()
    runtime_log.info(f"  CIRIS_HOME: {ciris_home}")
    runtime_log.info(f"  DATA_DIR: {data_dir}")
    log_step(runtime_log, "Resolving paths", "OK")

    # Create configs
    log_step(runtime_log, "Creating configuration", "...")
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
    log_step(runtime_log, "Creating configuration", "OK")

    # Create runtime
    log_step(runtime_log, "Creating CIRISRuntime", "...")
    runtime = CIRISRuntime(
        adapter_types=["api"],
        essential_config=app_config,
        startup_channel_id=startup_channel_id,
        adapter_configs=adapter_configs,
        interactive=False,
        host="127.0.0.1",
        port=8080,
    )
    log_step(runtime_log, "Creating CIRISRuntime", "OK")

    # Store event loop reference for external watchdog thread
    global _event_loop
    _event_loop = asyncio.get_running_loop()
    runtime_log.info(f"Event loop captured: {_event_loop}")

    # Initialize
    log_phase(runtime_log, "RUNTIME_INIT", "END", "Configuration complete")
    log_phase(runtime_log, "SERVICE_INIT", "START")
    write_status_file({"phase": "SERVICE_INIT", "status": "initializing"})

    try:
        await runtime.initialize()
        log_phase(runtime_log, "SERVICE_INIT", "OK", "All services initialized")
    except Exception as e:
        log_phase(runtime_log, "SERVICE_INIT", "FAIL", str(e))
        write_status_file({"phase": "SERVICE_INIT", "status": "failed", "error": str(e)})
        raise

    # Write ready signal
    write_ready_signal()
    write_status_file({"phase": "RUNNING", "status": "healthy", "port": 8080})

    log_phase(runtime_log, "SERVER", "START", "API server starting on 127.0.0.1:8080")

    try:
        await runtime.run()
    except Exception as e:
        runtime_log.error(f"Runtime error: {e}", exc_info=True)
        write_status_file({"phase": "RUNNING", "status": "error", "error": str(e)})
        raise
    finally:
        log_phase(runtime_log, "SHUTDOWN", "START")
        clear_ready_signal()
        _event_loop = None
        await runtime.shutdown()
        log_phase(runtime_log, "SHUTDOWN", "OK", "Runtime shutdown complete")
        write_status_file({"phase": "STOPPED", "status": "shutdown"})


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


def _init_environment() -> bool:
    """Initialize iOS environment. Returns True on success."""
    log_phase(_log, "ENVIRONMENT", "START")
    try:
        setup_ios_environment()
        log_phase(_log, "ENVIRONMENT", "OK")
        return True
    except Exception as e:
        log_phase(_log, "ENVIRONMENT", "FAIL", str(e))
        write_status_file({"phase": "ENVIRONMENT", "status": "failed", "error": str(e)})
        return False


def _run_checks() -> bool:
    """Run startup checks. Returns True on success."""
    log_phase(_log, "STARTUP_CHECKS", "START")
    write_status_file({"phase": "STARTUP_CHECKS", "status": "running"})

    if not run_startup_checks():
        log_phase(_log, "STARTUP_CHECKS", "FAIL", "See startup_status.json for details")
        write_status_file({"phase": "STARTUP_CHECKS", "status": "failed"})
        _log.error("Startup checks failed - runtime will not start")
        return False

    log_phase(_log, "STARTUP_CHECKS", "OK")
    return True


def _reset_shutdown_service() -> None:
    """Reset global shutdown service for new event loop."""
    try:
        from ciris_engine.logic.utils.shutdown_manager import reset_global_shutdown_service

        reset_global_shutdown_service()
        _log.info("Reset global shutdown service for new event loop")
    except Exception as e:
        _log.warning(f"Could not reset shutdown service: {e}")


def _run_runtime_iteration(restart_count: int) -> tuple[bool, bool]:
    """Run one runtime iteration. Returns (should_continue, clean_exit)."""
    import asyncio

    global _restart_requested

    _restart_requested = False
    _reset_shutdown_service()

    _log.info(f"Starting runtime iteration {restart_count + 1}")
    start_watchdog_thread()

    write_status_file({"phase": "RUNTIME", "status": "starting", "restart_count": restart_count})
    asyncio.run(start_mobile_runtime_with_watchdog())

    if _restart_requested:
        _log.warning(f"Restart requested by watchdog (count: {restart_count + 1})")
        write_status_file({"phase": "RESTARTING", "status": "watchdog_triggered", "restart_count": restart_count + 1})
        time.sleep(1.0)
        return True, False  # continue, not clean exit

    _log.info("Runtime exited normally")
    return False, True  # don't continue, clean exit


def main():
    """Main entrypoint for KMP iOS app - runs checks and starts runtime with restart support."""
    log_phase(_log, "KMP_MAIN", "START", "CIRIS iOS KMP Runtime")
    _log.info("UI: Compose (Kotlin Multiplatform)")
    _log.info("Restart signaling: ENABLED")
    _log.info(f"Log directory: {get_log_dir()}")

    write_status_file({"phase": "STARTUP", "status": "environment_setup"})

    if not _init_environment():
        return

    if not _run_checks():
        return

    # Run with restart loop
    global _restart_requested
    restart_count = 0
    max_restarts = 10

    while restart_count < max_restarts:
        try:
            should_continue, clean_exit = _run_runtime_iteration(restart_count)
            if clean_exit:
                break
            if should_continue:
                restart_count += 1
                continue

        except KeyboardInterrupt:
            _log.info("Server stopped by user (KeyboardInterrupt)")
            break

        except Exception as e:
            _log.error(f"Server error: {e}", exc_info=True)
            write_status_file({"phase": "ERROR", "status": "exception", "error": str(e)})

            if _restart_requested or check_restart_signal():
                restart_count += 1
                clear_restart_signal()
                _log.warning(f"Restart signal found after error, restarting... (count: {restart_count})")
                time.sleep(1.0)
                continue
            raise

    if restart_count >= max_restarts:
        _log.error(f"Max restarts ({max_restarts}) reached, giving up")
        write_status_file({"phase": "STOPPED", "status": "max_restarts_reached", "restart_count": restart_count})

    log_phase(_log, "KMP_MAIN", "END")


if __name__ == "__main__":
    main()
