"""
iOS on-device entrypoint for CIRIS.

This module starts the full CIRIS runtime on-device with the API adapter,
with all LLM calls routed to a remote OpenAI-compatible endpoint.

Architecture:
- Python runtime: On-device (via BeeWare/Briefcase)
- CIRIS Runtime: Full 22 services + agent processor
- FastAPI server: On-device (localhost:8080)
- Web UI: On-device (bundled assets served by FastAPI)
- LLM provider: Remote (OpenAI-compatible endpoint)
- Database: On-device SQLite
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Configure logging for iOS (NSLog-friendly via std-nslog)
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(name)s: %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

# Check if running on iOS
IS_IOS = sys.platform == "ios" or "darwin" in sys.platform


# =============================================================================
# STARTUP CHECKS
# =============================================================================

def check_pydantic() -> bool:
    """Verify pydantic loads correctly."""
    print("[1/6] Checking pydantic...")
    try:
        import pydantic
        from pydantic_core import _pydantic_core
        print(f"      Pydantic: {pydantic.VERSION}")
        print(f"      pydantic-core: {_pydantic_core.__version__}")
        print("[1/6] OK")
        return True
    except ImportError as e:
        print(f"[1/6] FAILED: {e}")
        return False


def check_fastapi() -> bool:
    """Verify FastAPI loads correctly."""
    print("[2/6] Checking FastAPI...")
    try:
        import fastapi
        print(f"      FastAPI: {fastapi.__version__}")
        print("[2/6] OK")
        return True
    except ImportError as e:
        print(f"[2/6] FAILED: {e}")
        return False


def check_cryptography() -> bool:
    """Verify cryptography loads correctly."""
    print("[3/6] Checking cryptography...")
    try:
        import cryptography
        print(f"      Cryptography: {cryptography.__version__}")
        print("[3/6] OK")
        return True
    except ImportError as e:
        print(f"[3/6] FAILED: {e}")
        return False


def check_httpx() -> bool:
    """Verify httpx loads correctly."""
    print("[4/6] Checking httpx...")
    try:
        import httpx
        print(f"      httpx: {httpx.__version__}")
        print("[4/6] OK")
        return True
    except ImportError as e:
        print(f"[4/6] FAILED: {e}")
        return False


def check_aiosqlite() -> bool:
    """Verify aiosqlite loads correctly."""
    print("[5/6] Checking aiosqlite...")
    try:
        import aiosqlite
        print(f"      aiosqlite: {aiosqlite.__version__}")
        print("[5/6] OK")
        return True
    except ImportError as e:
        print(f"[5/6] FAILED: {e}")
        return False


def check_ciris_engine() -> bool:
    """Verify CIRIS engine loads correctly."""
    print("[6/6] Checking CIRIS engine...")
    try:
        from ciris_engine.schemas.config.essential import EssentialConfig
        print("      EssentialConfig: OK")
        print("[6/6] OK")
        return True
    except ImportError as e:
        print(f"[6/6] FAILED: {e}")
        return False


# =============================================================================
# ENVIRONMENT SETUP
# =============================================================================

def setup_ios_environment() -> Path:
    """Configure environment for iOS on-device operation.

    Sets up CIRIS_HOME and loads .env if present.
    First-run detection is handled by is_first_run() which is iOS-aware.
    """
    # Get the app's Documents directory for persistent storage
    home = Path.home()

    # Use Documents directory for CIRIS data
    ciris_home = home / "Documents" / "ciris"
    ciris_home.mkdir(parents=True, exist_ok=True)
    (ciris_home / "databases").mkdir(parents=True, exist_ok=True)
    (ciris_home / "logs").mkdir(parents=True, exist_ok=True)

    # Configure CIRIS environment - use standard paths
    # CIRIS_HOME is used by path_resolution.py for iOS-aware path detection
    os.environ.setdefault("CIRIS_HOME", str(ciris_home))
    os.environ.setdefault("CIRIS_DATA_DIR", str(ciris_home))
    os.environ.setdefault("CIRIS_DB_PATH", str(ciris_home / "databases" / "ciris.db"))
    os.environ.setdefault("CIRIS_LOG_DIR", str(ciris_home / "logs"))

    # Load .env file if it exists (sets OPENAI_API_KEY, OPENAI_API_BASE, etc.)
    # First-run detection is handled by is_first_run() - don't duplicate logic here
    env_file = ciris_home / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=True)
            logger.info(f"Loaded configuration from {env_file}")
        except ImportError:
            logger.warning("dotenv not available, skipping .env loading")
    else:
        logger.info(f"No .env file at {env_file} - is_first_run() will detect this")

    # Disable ciris.ai cloud components
    os.environ["CIRIS_OFFLINE_MODE"] = "true"
    os.environ["CIRIS_CLOUD_SYNC"] = "false"

    # Optimize for low-resource devices
    os.environ.setdefault("CIRIS_MAX_WORKERS", "1")
    os.environ.setdefault("CIRIS_LOG_LEVEL", "INFO")
    os.environ.setdefault("CIRIS_API_HOST", "127.0.0.1")
    os.environ.setdefault("CIRIS_API_PORT", "8080")

    return ciris_home


# =============================================================================
# RUNTIME STARTUP
# =============================================================================

def _runtime_log(msg):
    """Log to both stdout and stderr for visibility."""
    print(msg, flush=True)
    sys.stderr.write(f"{msg}\n")
    sys.stderr.flush()


async def start_mobile_runtime():
    """Start the full CIRIS runtime with API adapter for iOS.

    Auto-loads adapters based on platform capabilities:
    - api: Always loaded (core functionality)
    """
    _runtime_log("[CIRIS RUNTIME] ========================================")
    _runtime_log("[CIRIS RUNTIME] start_mobile_runtime() called")
    _runtime_log("[CIRIS RUNTIME] ========================================")

    try:
        _runtime_log("[CIRIS RUNTIME] Importing APIAdapterConfig...")
        from ciris_engine.logic.adapters.api.config import APIAdapterConfig

        _runtime_log("[CIRIS RUNTIME] Importing CIRISRuntime...")
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        _runtime_log("[CIRIS RUNTIME] Importing AdapterConfig...")
        from ciris_engine.schemas.runtime.adapter_management import AdapterConfig

        _runtime_log("[CIRIS RUNTIME] Importing path_resolution...")
        from ciris_engine.logic.utils.path_resolution import get_ciris_home, get_data_dir

        _runtime_log("[CIRIS RUNTIME] Importing config schemas...")
        from ciris_engine.schemas.config.essential import DatabaseConfig, EssentialConfig, SecurityConfig

        _runtime_log("[CIRIS RUNTIME] All imports successful!")
    except Exception as e:
        _runtime_log(f"[CIRIS RUNTIME] !!!!! IMPORT ERROR !!!!!")
        _runtime_log(f"[CIRIS RUNTIME] Error: {e}")
        import traceback
        tb = traceback.format_exc()
        for line in tb.split('\n'):
            _runtime_log(f"[CIRIS RUNTIME] {line}")
        return

    _runtime_log("[CIRIS RUNTIME] Starting CIRIS on-device runtime...")
    _runtime_log("[CIRIS RUNTIME] API endpoint: http://127.0.0.1:8080")

    # Get iOS-specific paths
    ciris_home = get_ciris_home()
    data_dir = get_data_dir()
    logger.info(f"Using iOS config - CIRIS_HOME: {ciris_home}, data_dir: {data_dir}")

    # Create security config with absolute paths
    security_config = SecurityConfig(
        secrets_key_path=ciris_home / ".ciris_keys",
        audit_key_path=ciris_home / "audit_keys",
    )

    # Create database config with absolute paths
    db_config = DatabaseConfig(
        main_db=data_dir / "ciris_engine.db",
        secrets_db=data_dir / "secrets.db",
        audit_db=data_dir / "ciris_audit.db",
    )

    # Create config with iOS-specific paths
    app_config = EssentialConfig(
        security=security_config,
        database=db_config,
        template_directory=ciris_home / "ciris_templates",
    )

    # Configure API adapter - bind to localhost
    api_config = APIAdapterConfig()
    api_config.host = "127.0.0.1"
    api_config.port = 8080

    adapter_configs = {"api": AdapterConfig(adapter_type="api", enabled=True, settings=api_config.model_dump())}
    adapter_types = ["api"]

    startup_channel_id = api_config.get_home_channel_id(api_config.host, api_config.port)

    # Create the full CIRIS runtime
    runtime = CIRISRuntime(
        adapter_types=adapter_types,
        essential_config=app_config,
        startup_channel_id=startup_channel_id,
        adapter_configs=adapter_configs,
        interactive=False,  # No interactive CLI on iOS
        host="127.0.0.1",
        port=8080,
    )

    # Initialize all services (22 services, buses, etc.)
    logger.info("Initializing CIRIS services...")
    await runtime.initialize()
    logger.info("CIRIS runtime initialized successfully")

    # Run the runtime
    try:
        await runtime.run()
    except KeyboardInterrupt:
        logger.info("Runtime interrupted, shutting down...")
        runtime.request_shutdown("User interrupt")
    except Exception as e:
        logger.error(f"Runtime error: {e}", exc_info=True)
        runtime.request_shutdown(f"Error: {e}")
    finally:
        await runtime.shutdown()


# =============================================================================
# STARTUP CHECKS RUNNER
# =============================================================================

def run_startup_checks() -> bool:
    """Run all startup checks and return True if all pass."""
    print("=" * 50)
    print("CIRIS iOS RUNTIME")
    print("=" * 50)
    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {sys.platform}")
    print("=" * 50)
    print("")

    checks = [
        check_pydantic,
        check_fastapi,
        check_cryptography,
        check_httpx,
        check_aiosqlite,
        check_ciris_engine,
    ]

    all_passed = True
    for check in checks:
        if not check():
            all_passed = False

    print("")

    if all_passed:
        print("=" * 50)
        print("ALL CHECKS PASSED")
        print("=" * 50)
    else:
        print("!" * 50)
        print("SOME CHECKS FAILED")
        print("!" * 50)

    print("")
    return all_passed


# =============================================================================
# BACKGROUND THREAD RUNNER
# =============================================================================

def start_runtime_thread():
    """Start the CIRIS runtime in a background thread."""
    import threading

    def _log(msg):
        """Log to both stdout and stderr for visibility."""
        print(msg, flush=True)
        sys.stderr.write(f"{msg}\n")
        sys.stderr.flush()

    def run_async_runtime():
        try:
            _log("[CIRIS THREAD] ========================================")
            _log("[CIRIS THREAD] Starting CIRIS runtime thread")
            _log("[CIRIS THREAD] ========================================")

            # Environment already setup by app.py - skip duplicate setup
            _log("[CIRIS THREAD] Calling asyncio.run(start_mobile_runtime())...")

            # Run the async runtime
            asyncio.run(start_mobile_runtime())

            _log("[CIRIS THREAD] asyncio.run() completed normally")
        except Exception as e:
            _log(f"[CIRIS THREAD] !!!!! RUNTIME ERROR !!!!!")
            _log(f"[CIRIS THREAD] Error: {e}")
            import traceback
            tb = traceback.format_exc()
            for line in tb.split('\n'):
                _log(f"[CIRIS THREAD] {line}")

    thread = threading.Thread(target=run_async_runtime, daemon=True, name="CIRIS-Runtime")
    thread.start()
    print("CIRIS runtime started in background thread", flush=True)
    return thread


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """Main entrypoint for iOS app - runs checks and starts runtime."""
    print("CIRIS iOS - Full On-Device Runtime")
    print("")

    if run_startup_checks():
        setup_ios_environment()
        try:
            asyncio.run(start_mobile_runtime())
        except KeyboardInterrupt:
            print("Server stopped by user")
        except Exception as e:
            print(f"Server error: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    main()
