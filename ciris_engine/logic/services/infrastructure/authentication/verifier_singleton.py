"""Global CIRISVerify singleton.

All code that needs CIRISVerify should use get_verifier() from this module
instead of creating CIRISVerify() instances directly.

This ensures:
1. Only ONE CIRISVerify instance exists across the entire application
2. Rust FFI initialization happens only once
3. Network calls to registry happen only once
4. All attestation state is shared
"""

import logging
import threading
from typing import Any, Dict, Optional

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


def _normalize_descriptor(descriptor: Any) -> Optional[Dict[str, Any]]:
    """Normalize a storage descriptor to a dict for /health serialization.

    The FFI may return: None | dict | Pydantic model (model_dump) |
    arbitrary object with __dict__ | scalar (path string). Each shape gets
    coerced to a dict (or None) so callers see a single contract.
    """
    if descriptor is None:
        return None
    if isinstance(descriptor, dict):
        return descriptor
    if hasattr(descriptor, "model_dump"):
        try:
            return dict(descriptor.model_dump())
        except Exception:
            pass
    if hasattr(descriptor, "__dict__"):
        return {k: v for k, v in descriptor.__dict__.items() if not k.startswith("_")}
    # Scalar — wrap so downstream consumers can rely on dict shape.
    return {"value": str(descriptor)}


def get_storage_descriptor() -> Optional[Dict[str, Any]]:
    """Return the verifier's hardware-signer storage descriptor, or None.

    Added 2.7.8.1 for CIRISVerify v1.8.0 (PoB substrate primitive coordination —
    see https://github.com/CIRISAI/CIRISAgent/issues/708 and
    https://github.com/CIRISAI/CIRISVerify/issues/1).

    The descriptor declares where the agent's identity seed lives — the same
    Ed25519 key that signs traces, addresses Reticulum destinations, and
    authors gratitude signals. Surfacing it on /health and at boot time lets
    operators confirm the keyring is on a mounted volume rather than silently
    landing in container ephemeral storage (the lens-scrub-key incident class).

    Returns:
        Dict-shaped descriptor (path, signer-type, hardware-backed flag, etc.)
        if the loaded ciris-verify supports it (v1.8.0+).
        None if the verifier hasn't been initialized, the loaded library
        predates v1.8.0, or the descriptor call raised.

    Best-effort: this MUST NOT raise. Boot-time logging callers depend on
    being able to call this without a try/except wrapper.
    """
    if _verifier is None:
        return None

    # Defensive accessor: v1.8.0 ships HardwareSigner.storage_descriptor() but
    # the exact Python binding surface in older bundled FFI .so files may differ.
    # Try the documented method name first; fall through to None on any failure.
    for attr_name in ("storage_descriptor", "get_storage_descriptor"):
        method = getattr(_verifier, attr_name, None)
        if not callable(method):
            continue
        try:
            descriptor = method()
        except Exception as e:
            logger.debug(
                "[verifier_singleton] %s() raised: %s — falling through.",
                attr_name,
                e,
            )
            continue
        return _normalize_descriptor(descriptor)

    return None


def log_storage_descriptor_at_boot() -> None:
    """Emit a single boot-time log line surfacing the storage descriptor.

    Called once during agent startup. Logs at WARNING level so it surfaces
    even with default-suppressed runtime loggers — operators need this
    visible in deploy logs without having to re-run with --debug.

    Silent (DEBUG only) when the descriptor is unavailable, since the v1.8
    feature is opt-in by ciris-verify version. Loud (WARNING) when the
    descriptor IS available but points at a path that *looks* ephemeral —
    a defensive heuristic for the canonical container-misconfiguration
    failure mode (see issue #708 / CIRISVerify#1).
    """
    descriptor = get_storage_descriptor()
    if descriptor is None:
        logger.debug(
            "[verifier_singleton] storage_descriptor() unavailable — "
            "ciris-verify <1.8.0 or descriptor not yet exposed."
        )
        return

    logger.warning(
        "[verifier_singleton] CIRISVerify storage descriptor: %s",
        descriptor,
    )

    # Defensive heuristic: any path string containing /tmp/, /run/, or
    # /var/lib/docker (without an explicit user override) flags as ephemeral.
    # This is intentionally conservative — false positives are louder than
    # false negatives here. The CIRIS_PERSIST_KEYRING_PATH_OK=1 override
    # mirrors the CIRISPersist convention.
    import os as _os

    path_value = ""
    for key in ("path", "keyring_path", "value"):
        if isinstance(descriptor.get(key), str):
            path_value = descriptor[key]
            break

    if not path_value:
        return

    ephemeral_markers = ("/tmp/", "/run/", "/var/lib/docker")
    if any(marker in path_value for marker in ephemeral_markers):
        if _os.environ.get("CIRIS_PERSIST_KEYRING_PATH_OK") == "1":
            logger.info(
                "[verifier_singleton] Storage path %s matched ephemeral heuristic "
                "but CIRIS_PERSIST_KEYRING_PATH_OK=1 is set — proceeding.",
                path_value,
            )
        else:
            logger.error(
                "[verifier_singleton] WARNING: keyring path %s looks ephemeral. "
                "Identity seed may be lost on container restart, which would reset "
                "this agent's PoB S-factor decay window to zero. Mount a persistent "
                "volume, or set CIRIS_PERSIST_KEYRING_PATH_OK=1 to acknowledge.",
                path_value,
            )


def reset_verifier() -> None:
    """Reset the singleton (for testing only)."""
    global _verifier, _init_error
    with _verifier_lock:
        _verifier = None
        _init_error = None
