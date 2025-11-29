"""
Android on-device entrypoint for CIRIS.

This module starts the full CIRIS runtime on-device with the API adapter,
with all LLM calls routed to a remote OpenAI-compatible endpoint.

Architecture:
- Python runtime: On-device (via Chaquopy)
- CIRIS Runtime: Full 22 services + agent processor
- FastAPI server: On-device (localhost:8080)
- Web UI: On-device (bundled assets)
- LLM provider: Remote (OpenAI-compatible endpoint)
- Database: On-device SQLite
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Configure logging for Android (logcat-friendly)
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(name)s: %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


def setup_android_environment():
    """Configure environment for Android on-device operation.

    Sets up CIRIS_HOME and loads .env if present.
    First-run detection is handled by is_first_run() which is Android-aware.
    """
    from dotenv import load_dotenv

    if "ANDROID_DATA" not in os.environ:
        logger.warning("ANDROID_DATA not set - not running on Android?")
        return

    # Running on Android device
    android_data = Path(os.environ["ANDROID_DATA"])
    app_data = android_data / "data" / "ai.ciris.mobile"

    # Ensure directories exist
    ciris_home = app_data / "files" / "ciris"
    ciris_home.mkdir(parents=True, exist_ok=True)
    (ciris_home / "databases").mkdir(parents=True, exist_ok=True)
    (ciris_home / "logs").mkdir(parents=True, exist_ok=True)

    # Configure CIRIS environment - use standard paths
    # CIRIS_HOME is used by path_resolution.py for Android-aware path detection
    os.environ.setdefault("CIRIS_HOME", str(ciris_home))
    os.environ.setdefault("CIRIS_DATA_DIR", str(ciris_home))
    os.environ.setdefault("CIRIS_DB_PATH", str(ciris_home / "databases" / "ciris.db"))
    os.environ.setdefault("CIRIS_LOG_DIR", str(ciris_home / "logs"))

    # Load .env file if it exists (sets OPENAI_API_KEY, OPENAI_API_BASE, etc.)
    # First-run detection is handled by is_first_run() - don't duplicate logic here
    env_file = ciris_home / ".env"
    if env_file.exists():
        logger.info(f"Loading configuration from {env_file}")
        load_dotenv(env_file, override=True)
        logger.info(f"Loaded .env - OPENAI_API_KEY set: {bool(os.environ.get('OPENAI_API_KEY'))}")
        logger.info(f"Loaded .env - OPENAI_API_BASE: {os.environ.get('OPENAI_API_BASE', 'NOT SET')}")
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


async def start_mobile_runtime():
    """Start the full CIRIS runtime with API adapter for Android."""
    from ciris_engine.logic.adapters.api.config import APIAdapterConfig
    from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
    from ciris_engine.logic.utils.runtime_utils import load_config
    from ciris_engine.schemas.runtime.adapter_management import AdapterConfig

    logger.info("Starting CIRIS on-device runtime...")
    logger.info("API endpoint: http://127.0.0.1:8080")
    logger.info(f"LLM endpoint: {os.environ.get('OPENAI_API_BASE', 'NOT CONFIGURED')}")

    # On Android, we skip file-based config loading and use defaults directly
    # since the app doesn't have access to config/essential.yaml
    # The path resolution in EssentialConfig will use CIRIS_HOME env var
    # which was set by setup_android_environment()
    from ciris_engine.logic.utils.path_resolution import get_ciris_home, get_data_dir
    from ciris_engine.schemas.config.essential import DatabaseConfig, EssentialConfig, SecurityConfig

    # Get Android-specific paths
    ciris_home = get_ciris_home()
    data_dir = get_data_dir()

    # Create security config with absolute paths (Android CWD is read-only)
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

    # Create config with Android-specific paths
    app_config = EssentialConfig(
        security=security_config,
        database=db_config,
        template_directory=ciris_home / "ciris_templates",
    )
    logger.info(f"Using Android config - CIRIS_HOME: {ciris_home}, data_dir: {data_dir}")

    # Configure API adapter
    api_config = APIAdapterConfig()
    api_config.host = "127.0.0.1"
    api_config.port = 8080

    adapter_configs = {"api": AdapterConfig(adapter_type="api", enabled=True, settings=api_config.model_dump())}

    startup_channel_id = api_config.get_home_channel_id(api_config.host, api_config.port)

    # Create the full CIRIS runtime
    runtime = CIRISRuntime(
        adapter_types=["api"],
        essential_config=app_config,
        startup_channel_id=startup_channel_id,
        adapter_configs=adapter_configs,
        interactive=False,  # No interactive CLI on Android
        host="127.0.0.1",
        port=8080,
    )

    # Initialize all services (22 services, buses, etc.)
    logger.info("Initializing CIRIS services...")
    await runtime.initialize()
    logger.info("CIRIS runtime initialized successfully")

    # Run the runtime (includes API server and agent processor)
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


def main():
    """Main entrypoint for Android app."""
    logger.info("CIRIS Mobile - Full On-Device Runtime (LLM Remote)")
    setup_android_environment()

    try:
        asyncio.run(start_mobile_runtime())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
