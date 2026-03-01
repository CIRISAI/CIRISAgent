"""Play Integrity token verification via CIRISVerify FFI.

This module handles Google Play Integrity token verification using the
CIRISVerify FFI library. It provides crash protection by running FFI
calls in a separate thread with timeout.
"""

import ctypes
import json
import logging
import threading
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


def _verify_on_large_stack(
    verifier: Any,
    token: str,
    nonce: str,
    result: Dict[str, Any],
) -> None:
    """Run Play Integrity verification on a large stack thread.

    Args:
        verifier: The CIRISVerify instance
        token: Play Integrity token
        nonce: Nonce used when requesting the token
        result: Dict to store results (modified in place)
    """
    try:
        lib = getattr(verifier, "_lib", None)
        if not lib or not hasattr(lib, "ciris_verify_verify_integrity_token"):
            result["error"] = "Play Integrity FFI not available (need CIRISVerify >= 1.0.0)"
            result["verified"] = False
            return

        # Set argtypes - Rust FFI expects null-terminated c_char pointers
        lib.ciris_verify_verify_integrity_token.argtypes = [
            ctypes.c_void_p,  # handle
            ctypes.c_char_p,  # token (null-terminated)
            ctypes.c_char_p,  # nonce (null-terminated)
            ctypes.POINTER(ctypes.c_void_p),  # result_ptr
            ctypes.POINTER(ctypes.c_size_t),  # result_len
        ]
        lib.ciris_verify_verify_integrity_token.restype = ctypes.c_int

        handle = getattr(verifier, "_handle", None)
        if not handle:
            result["error"] = "CIRISVerify handle not available"
            result["verified"] = False
            return

        # Encode to bytes with null terminator for C strings
        token_bytes = token.encode("utf-8") + b"\x00"
        nonce_bytes = nonce.encode("utf-8") + b"\x00"
        result_ptr = ctypes.c_void_p()
        result_len = ctypes.c_size_t()

        ret = lib.ciris_verify_verify_integrity_token(
            handle,
            token_bytes,
            nonce_bytes,
            ctypes.byref(result_ptr),
            ctypes.byref(result_len),
        )

        if ret != 0:
            result["error"] = f"FFI error code: {ret}"
            result["verified"] = False
            return

        if result_ptr.value and result_len.value > 0:
            result_bytes = ctypes.string_at(result_ptr.value, result_len.value)
            lib.ciris_verify_free(ctypes.cast(result_ptr, ctypes.c_char_p))
            data = json.loads(result_bytes.decode("utf-8"))
            result.update(data)
        else:
            result["error"] = "Empty response from FFI"
            result["verified"] = False

    except Exception as e:
        logger.warning(f"[play-integrity] FFI exception: {e}")
        result["error"] = str(e)
        result["verified"] = False


def run_play_integrity_verification(
    verifier: Any,
    token: str,
    nonce: str,
    timeout_seconds: int = 45,
) -> Dict[str, Any]:
    """Run Play Integrity verification in a thread with crash protection.

    Args:
        verifier: The CIRISVerify instance
        token: Play Integrity token
        nonce: Nonce used when requesting the token
        timeout_seconds: Timeout for FFI call

    Returns:
        Dict with verification result or error
    """
    result: Dict[str, Any] = {}

    old_stack_size = threading.stack_size()
    try:
        threading.stack_size(8 * 1024 * 1024)  # 8MB for Rust/Tokio
        t = threading.Thread(
            target=_verify_on_large_stack,
            args=(verifier, token, nonce, result),
            daemon=True,
        )
        t.start()
        t.join(timeout=timeout_seconds)

        if t.is_alive():
            logger.warning(f"[play-integrity] FFI call timed out after {timeout_seconds} seconds")
            return {"error": "Play Integrity verification timed out", "verified": False}

        return result
    finally:
        threading.stack_size(old_stack_size)


def get_verifier_or_error() -> tuple[Optional[Any], Optional[Dict[str, Any]]]:
    """Get the CIRISVerify verifier or return an error dict.

    Returns:
        Tuple of (verifier, error_dict). If verifier is None, error_dict contains the error.
    """
    from ..verifier_singleton import get_verifier

    try:
        verifier = get_verifier()
    except Exception as e:
        logger.warning(f"[play-integrity] CIRISVerify not available: {e}")
        return None, {"error": f"CIRISVerify not available: {e}", "verified": False}

    if not verifier:
        return None, {"error": "CIRISVerify not initialized", "verified": False}

    return verifier, None
