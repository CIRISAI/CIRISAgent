"""CIRIS Engine - Core Agent Runtime and Services"""

from .constants import CIRIS_VERSION

__version__ = CIRIS_VERSION

# Import key runtime components for easy access
from .logic.runtime.ciris_runtime import CIRISRuntime
from .logic.runtime.runtime_interface import RuntimeInterface

__all__ = [
    "__version__",
    "CIRISRuntime",
    "RuntimeInterface",
]
