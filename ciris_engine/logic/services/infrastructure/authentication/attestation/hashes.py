"""Python hash loading for attestation.

This module handles loading Python module hashes from the startup file
for integrity verification.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

from .types import PythonHashesWrapper

logger = logging.getLogger(__name__)

# Default path for CIRIS home on Android
DEFAULT_ANDROID_CIRIS_HOME = "/data/data/ai.ciris.mobile/files/ciris"
HASHES_FILENAME = "startup_python_hashes.json"


def get_default_agent_version() -> Optional[str]:
    """Get the default agent version from CIRIS constants.

    Returns:
        Version string with suffixes stripped, or None if unavailable
    """
    try:
        from ciris_engine.constants import CIRIS_VERSION

        version = CIRIS_VERSION.split("-")[0] if "-" in CIRIS_VERSION else CIRIS_VERSION
        return version
    except Exception:
        return None


def load_python_hashes(
    ciris_home: Optional[str] = None,
) -> Tuple[Optional[PythonHashesWrapper], Optional[str]]:
    """Load Python module hashes from startup file.

    Args:
        ciris_home: CIRIS home directory path. Defaults to CIRIS_HOME env var.

    Returns:
        Tuple of (PythonHashesWrapper or None, agent_version or None)
    """
    if ciris_home is None:
        ciris_home = os.environ.get("CIRIS_HOME", DEFAULT_ANDROID_CIRIS_HOME)

    # Get default version in case hashes file doesn't have it
    agent_version = get_default_agent_version()

    hashes_path = Path(ciris_home) / HASHES_FILENAME

    if not hashes_path.exists():
        logger.warning(f"[attestation] No startup hashes file at {hashes_path}")
        return None, agent_version

    try:
        with open(hashes_path, encoding="utf-8") as f:
            hashes_data = json.load(f)

        python_hashes = PythonHashesWrapper.from_dict(hashes_data)

        # Update agent_version from hashes file if available
        file_version = hashes_data.get("agent_version")
        if file_version:
            # Strip -stable/-dev/-rc suffixes for registry lookup
            agent_version = file_version.split("-")[0] if "-" in file_version else file_version

        logger.info(f"[attestation] Loaded {python_hashes.module_count} " f"module hashes from {hashes_path}")

        # Debug: show first 5 module paths
        first_5 = list(python_hashes.module_hashes.keys())[:5]
        logger.info(f"[attestation] First 5 agent hash paths: {first_5}")

        return python_hashes, agent_version

    except json.JSONDecodeError as e:
        logger.warning(f"[attestation] Failed to parse Python hashes JSON: {e}")
        return None, agent_version
    except Exception as e:
        logger.warning(f"[attestation] Failed to load Python hashes: {e}")
        return None, agent_version
