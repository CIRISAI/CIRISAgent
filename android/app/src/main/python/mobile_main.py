"""
Android on-device entrypoint for CIRIS.

This module starts the FastAPI adapter on-device, with all LLM calls
routed to a remote OpenAI-compatible endpoint. No ciris.ai cloud components.

Architecture:
- Python runtime: On-device (via Chaquopy)
- FastAPI server: On-device (localhost:8000)
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
    """Configure environment for Android on-device operation."""
    # Set Android-specific paths
    if "ANDROID_DATA" in os.environ:
        # Running on Android device
        android_data = Path(os.environ["ANDROID_DATA"])
        app_data = android_data / "data" / "ai.ciris.mobile"

        # Ensure directories exist
        (app_data / "databases").mkdir(parents=True, exist_ok=True)
        (app_data / "logs").mkdir(parents=True, exist_ok=True)

        # Configure CIRIS environment
        os.environ.setdefault("CIRIS_DATA_DIR", str(app_data))
        os.environ.setdefault("CIRIS_DB_PATH", str(app_data / "databases" / "ciris.db"))
        os.environ.setdefault("CIRIS_LOG_DIR", str(app_data / "logs"))

    # Ensure remote LLM endpoint is configured
    if not os.environ.get("OPENAI_API_BASE"):
        logger.warning(
            "OPENAI_API_BASE not set. You must configure a remote LLM endpoint. "
            "Example: https://api.openai.com/v1 or http://192.168.1.100:8080/v1"
        )

    # Disable ciris.ai cloud components
    os.environ["CIRIS_OFFLINE_MODE"] = "true"
    os.environ["CIRIS_CLOUD_SYNC"] = "false"

    # Optimize for low-resource devices
    os.environ.setdefault("CIRIS_MAX_WORKERS", "1")
    os.environ.setdefault("CIRIS_LOG_LEVEL", "WARNING")
    os.environ.setdefault("CIRIS_API_HOST", "127.0.0.1")
    os.environ.setdefault("CIRIS_API_PORT", "8080")  # Match GUI SDK default


async def start_mobile_server():
    """Start the CIRIS FastAPI server for Android."""
    import uvicorn

    from ciris_engine.logic.adapters.api.app import create_app

    # Create the FastAPI app instance
    app = create_app()

    logger.info("Starting CIRIS on-device server...")
    logger.info(f"API endpoint: http://127.0.0.1:8080")
    logger.info(f"LLM endpoint: {os.environ.get('OPENAI_API_BASE', 'NOT CONFIGURED')}")

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=8080,  # Match GUI SDK default
        workers=1,  # Single worker for low-resource devices
        log_level="warning",
        access_log=False,  # Reduce overhead
        use_colors=False,  # Android logcat doesn't need colors
    )

    server = uvicorn.Server(config)
    await server.serve()


def main():
    """Main entrypoint for Android app."""
    logger.info("CIRIS Mobile - 100% On-Device (LLM Remote)")
    setup_android_environment()

    try:
        asyncio.run(start_mobile_server())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
