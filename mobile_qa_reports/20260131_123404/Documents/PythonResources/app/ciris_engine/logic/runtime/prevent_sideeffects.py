"""
Prevent side effects during module imports.

This module should be imported at the very beginning of any test or module
that might import CIRIS components to ensure no runtime instances are created
as side effects.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Set a flag to prevent runtime initialization during imports
os.environ["CIRIS_IMPORT_MODE"] = "true"

# Also ensure mock LLM is used if we're in a test environment
if "pytest" in os.environ.get("_", "") or "PYTEST_CURRENT_TEST" in os.environ:
    logger.info("Detected pytest environment, setting CIRIS_MOCK_LLM=true")
    os.environ["CIRIS_MOCK_LLM"] = "true"


def allow_runtime_creation() -> None:
    """Allow runtime creation after imports are complete."""
    os.environ.pop("CIRIS_IMPORT_MODE", None)


def is_import_mode() -> bool:
    """Check if we're in import mode (preventing side effects)."""
    return os.environ.get("CIRIS_IMPORT_MODE", "").lower() == "true"
