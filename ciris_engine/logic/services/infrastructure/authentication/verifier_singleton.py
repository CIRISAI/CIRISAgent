"""Global CIRISVerify singleton.

All code that needs CIRISVerify should use get_verifier() from this module
instead of creating CIRISVerify() instances directly.

This ensures:
1. Only ONE CIRISVerify instance exists across the entire application
2. Rust FFI initialization happens only once
3. Network calls to registry happen only once
4. All attestation state is shared

Environment Variables:
    CIRIS_MOCK_VERIFY=1: Use MockCIRISVerify instead of real FFI (for testing)
"""

import logging
import os
import threading
from typing import Any, Optional

from ciris_engine.logic.utils.path_resolution import ensure_ciris_home_env

logger = logging.getLogger(__name__)

# Global singleton state
_verifier: Optional[Any] = None
_verifier_lock = threading.Lock()
_init_error: Optional[Exception] = None


def get_verifier() -> Any:
    """Get the global CIRISVerify singleton instance.

    Creates the instance on first call (with 8MB stack thread for Rust/Tokio).
    All subsequent calls return the same instance.

    Returns:
        CIRISVerify instance

    Raises:
        ImportError: If ciris_verify is not available
        RuntimeError: If initialization fails or times out
    """
    global _verifier, _init_error

    # Fast path - already initialized
    if _verifier is not None:
        return _verifier

    with _verifier_lock:
        # Double-check after acquiring lock
        if _verifier is not None:
            return _verifier

        # Re-raise previous init error (but allow retry for transient failures)
        if _init_error is not None:
            # Only cache permanent errors (ImportError = library not installed)
            # For other errors (timing, thread, etc.), clear and retry
            if isinstance(_init_error, ImportError):
                raise _init_error
            logger.info(f"[verifier_singleton] Clearing previous init error and retrying: {_init_error}")
            _init_error = None

        try:
            # Check for mock mode (for testing without FFI)
            use_mock = os.environ.get("CIRIS_MOCK_VERIFY", "").lower() in ("1", "true", "yes")

            if use_mock:
                from ciris_adapters.ciris_verify import MockCIRISVerify
                _verifier = MockCIRISVerify()
                logger.info("[verifier_singleton] Using MockCIRISVerify (CIRIS_MOCK_VERIFY=1)")
                return _verifier

            from ciris_adapters.ciris_verify import CIRISVerify

            # CRITICAL: Ensure CIRIS_HOME and CIRIS_DATA_DIR are set robustly
            # This uses path_resolution which has fallbacks for all platforms:
            # - /app/ for CIRIS Manager/Docker
            # - CWD for development mode (git repo)
            # - ~/ciris/ for installed mode
            # - Android/iOS specific paths for mobile
            ciris_home = ensure_ciris_home_env()
            logger.info(f"[verifier_singleton] Initializing CIRISVerify with CIRIS_HOME={ciris_home}")

            # CIRISVerify() triggers Rust/Tokio init which needs 8MB stack
            holder: list[Any] = [None, None]  # [verifier, error]

            def _create() -> None:
                try:
                    holder[0] = CIRISVerify(skip_integrity_check=True)
                except Exception as exc:
                    holder[1] = exc

            # Save and set stack size
            old_stack_size = threading.stack_size()
            try:
                threading.stack_size(8 * 1024 * 1024)  # 8MB
                t = threading.Thread(target=_create, daemon=True)
                t.start()
                t.join(timeout=30)
            finally:
                threading.stack_size(old_stack_size)

            if holder[1] is not None:
                _init_error = holder[1]
                raise holder[1]
            if holder[0] is None:
                err = RuntimeError("CIRISVerify creation timed out")
                _init_error = err
                raise err

            _verifier = holder[0]
            logger.info("[verifier_singleton] Created global CIRISVerify instance")

            # Set up logging callback
            _setup_logging(_verifier)

            return _verifier

        except ImportError as e:
            _init_error = e
            raise


def _setup_logging(verifier: Any) -> None:
    """Set up Rust logging callback to forward to Python logging."""
    try:
        from ciris_adapters.ciris_verify import setup_logging

        # Use TRACE level for maximum detail during attestation debugging
        setup_logging(verifier, level="TRACE")
        # Ensure ciris_verify logger outputs at DEBUG level
        import logging as pylogging

        cv_logger = pylogging.getLogger("ciris_verify")
        cv_logger.setLevel(pylogging.DEBUG)
        logger.info("[verifier_singleton] Rust logging callback registered (TRACE level)")
    except Exception as e:
        logger.warning(f"[verifier_singleton] Could not set up Rust logging: {e}")


def has_verifier() -> bool:
    """Check if verifier singleton has been initialized."""
    return _verifier is not None


def reset_verifier() -> None:
    """Reset the singleton (for testing only)."""
    global _verifier, _init_error
    with _verifier_lock:
        _verifier = None
        _init_error = None
