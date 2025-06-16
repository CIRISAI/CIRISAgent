"""Runtime utilities for CIRIS engine startup and configuration."""

import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional, List

from ..config.config_manager import load_config_from_file_async, AppConfig
from ..runtime.ciris_runtime import CIRISRuntime


async def load_config(config_path: Optional[str]) -> AppConfig:
    """Load application configuration from a path."""
    return await load_config_from_file_async(Path(config_path) if config_path else None)


async def run_with_shutdown_handler(runtime: CIRISRuntime, num_rounds: Optional[int] = None) -> None:
    """Run the runtime and handle shutdown signals gracefully."""
    loop = asyncio.get_running_loop()
    shutdown_requested_event = asyncio.Event()

    def signal_handler() -> None:
        if not shutdown_requested_event.is_set():
            logging.info("Shutdown signal received. Requesting runtime shutdown...")
            runtime.request_shutdown("Signal received by main.py handler")
            shutdown_requested_event.set()  # Prevent multiple calls to request_shutdown from signals
        else:
            logging.info("Shutdown already in progress.")

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Some environments (like Windows default loop) might not support add_signal_handler
            logging.warning(f"Signal handler for {sig} could not be set. Manual shutdown might be required.")
            pass  # Continue without signal handlers if not supported

    try:
        await runtime.run(num_rounds=num_rounds)
    except Exception as e:
        logging.critical(f"Runtime execution failed: {e}", exc_info=True)
        # Ensure shutdown is requested if a top-level error occurs in runtime.run() itself
        if runtime._shutdown_event is None or not runtime._shutdown_event.is_set():  # Accessing protected member for check
            runtime.request_shutdown(f"Runtime error: {e}")
        await runtime.shutdown()  # Attempt graceful shutdown
    finally:
        logging.info("Runtime execution finished or was interrupted.")
        # Ensure signal handlers are removed to avoid issues if the loop is reused
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.remove_signal_handler(sig)
            except (NotImplementedError, ValueError):  # ValueError if not set
                pass