"""Path resolution helpers for attestation.

This module handles finding the agent root directory, audit database path,
and Ed25519 key fingerprint for attestation verification.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, List, Optional

from .platform import is_mobile

logger = logging.getLogger(__name__)

# Database filename constant
AUDIT_DB_FILENAME = "ciris_audit.db"


def get_agent_root() -> str:
    """Get the agent root directory for file integrity checking.

    On mobile platforms, uses the Python package path where the runtime
    extracts files. On desktop, uses CIRIS_AGENT_ROOT env var or cwd.

    Returns:
        Path to the agent root directory
    """
    if is_mobile():
        try:
            import ciris_engine

            agent_root = os.path.dirname(os.path.dirname(ciris_engine.__file__))
            logger.info(f"[attestation] Mobile agent_root from ciris_engine: {agent_root}")
            return agent_root
        except Exception as e:
            logger.warning(f"[attestation] Mobile agent_root detection failed: {e}")
            return os.getcwd()
    else:
        return os.environ.get("CIRIS_AGENT_ROOT", os.getcwd())


def get_audit_db_search_paths(ciris_home: str) -> List[Path]:
    """Get list of possible audit database paths to search.

    Args:
        ciris_home: CIRIS home directory

    Returns:
        List of paths to check for the audit database
    """
    return [
        Path(ciris_home) / "data" / AUDIT_DB_FILENAME,
        Path(ciris_home) / AUDIT_DB_FILENAME,
        Path("/data/user/0/ai.ciris.mobile/files/ciris/data") / AUDIT_DB_FILENAME,
        Path("/data/data/ai.ciris.mobile/files/ciris/data") / AUDIT_DB_FILENAME,
        Path.cwd() / "data" / AUDIT_DB_FILENAME,
        Path.cwd() / AUDIT_DB_FILENAME,
    ]


def find_audit_db_path(ciris_home: Optional[str] = None) -> Optional[str]:
    """Find the audit database path.

    Searches multiple possible locations for the audit database.

    Args:
        ciris_home: CIRIS home directory. Defaults to CIRIS_HOME env var.

    Returns:
        Path to the audit database, or None if not found
    """
    if ciris_home is None:
        ciris_home = os.environ.get("CIRIS_HOME", "")

    possible_paths = get_audit_db_search_paths(ciris_home)

    for audit_path in possible_paths:
        if audit_path.exists():
            logger.info(f"[attestation] Found audit DB at: {audit_path}")
            return str(audit_path)

    logger.info(f"[attestation] No audit DB found at any of: {[str(p) for p in possible_paths]}")
    return None


def get_ed25519_fingerprint(verifier: Any) -> Optional[str]:
    """Get Ed25519 public key fingerprint from verifier.

    Args:
        verifier: CIRISVerify verifier instance

    Returns:
        SHA256 hex fingerprint of the Ed25519 public key, or None
    """
    try:
        if hasattr(verifier, "get_ed25519_public_key_sync"):
            pub_key = verifier.get_ed25519_public_key_sync()
            if pub_key:
                fingerprint = hashlib.sha256(pub_key).hexdigest()
                logger.info(f"[attestation] Ed25519 fingerprint: {fingerprint[:16]}...")
                return fingerprint
    except Exception as e:
        logger.warning(f"[attestation] Failed to get Ed25519 fingerprint: {e}")

    return None
