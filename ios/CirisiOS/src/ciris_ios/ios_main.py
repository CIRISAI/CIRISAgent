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

    Returns the CIRIS home directory path.
    """
    print("=" * 50)
    print("Setting up iOS environment...")
    print("=" * 50)

    # Get the app's Documents directory for persistent storage
    home = Path.home()

    # Use Documents directory for CIRIS data
    ciris_home = home / "Documents" / "ciris"
    ciris_home.mkdir(parents=True, exist_ok=True)
    (ciris_home / "databases").mkdir(parents=True, exist_ok=True)
    (ciris_home / "logs").mkdir(parents=True, exist_ok=True)

    # Configure CIRIS environment
    os.environ.setdefault("CIRIS_HOME", str(ciris_home))
    os.environ.setdefault("CIRIS_DATA_DIR", str(ciris_home))
    os.environ.setdefault("CIRIS_DB_PATH", str(ciris_home / "databases" / "ciris.db"))
    os.environ.setdefault("CIRIS_LOG_DIR", str(ciris_home / "logs"))

    # Load .env file if it exists
    env_file = ciris_home / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=True)
            print(f"Loaded .env from {env_file}")
            print(f"OPENAI_API_KEY set: {bool(os.environ.get('OPENAI_API_KEY'))}")
            print(f"OPENAI_API_BASE: {os.environ.get('OPENAI_API_BASE', 'NOT SET')}")
        except ImportError:
            print("dotenv not available, skipping .env loading")
    else:
        print(f"No .env file at {env_file}")

    # Disable cloud components for offline operation
    os.environ["CIRIS_OFFLINE_MODE"] = "true"
    os.environ["CIRIS_CLOUD_SYNC"] = "false"

    # Optimize for mobile
    os.environ.setdefault("CIRIS_MAX_WORKERS", "1")
    os.environ.setdefault("CIRIS_LOG_LEVEL", "INFO")
    os.environ.setdefault("CIRIS_API_HOST", "127.0.0.1")
    os.environ.setdefault("CIRIS_API_PORT", "8080")

    print(f"CIRIS_HOME: {ciris_home}")
    print("Environment setup complete.")
    print("")

    return ciris_home


# =============================================================================
# RUNTIME STARTUP
# =============================================================================

async def start_mobile_runtime():
    """Start the full CIRIS runtime with API adapter for iOS."""
    from ciris_engine.logic.adapters.api.config import APIAdapterConfig
    from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
    from ciris_engine.schemas.runtime.adapter_management import AdapterConfig
    from ciris_engine.logic.utils.path_resolution import get_ciris_home, get_data_dir
    from ciris_engine.schemas.config.essential import DatabaseConfig, EssentialConfig, SecurityConfig

    print("=" * 50)
    print("Starting CIRIS Mobile Runtime")
    print("=" * 50)
    print(f"API endpoint: http://127.0.0.1:8080")
    print(f"LLM endpoint: {os.environ.get('OPENAI_API_BASE', 'NOT CONFIGURED')}")
    print("")

    # Get iOS-specific paths
    ciris_home = get_ciris_home()
    data_dir = get_data_dir()

    print(f"CIRIS_HOME: {ciris_home}")
    print(f"Data dir: {data_dir}")
    print("")

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

    print("Creating CIRIS runtime...")

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

    # Initialize all services
    print("Initializing services...")
    await runtime.initialize()
    print("")
    print("=" * 50)
    print("CIRIS runtime initialized successfully")
    print("API server starting on http://127.0.0.1:8080")
    print("=" * 50)
    print("")

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

    def run_async_runtime():
        try:
            # Setup environment first
            setup_ios_environment()

            # Run the async runtime
            asyncio.run(start_mobile_runtime())
        except Exception as e:
            print(f"Runtime thread error: {e}")
            import traceback
            traceback.print_exc()

    thread = threading.Thread(target=run_async_runtime, daemon=True, name="CIRIS-Runtime")
    thread.start()
    print("CIRIS runtime started in background thread")
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
