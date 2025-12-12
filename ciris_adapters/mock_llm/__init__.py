"""
MockLLM modular service.

This is the first modular service in CIRIS, demonstrating:
- Self-contained service packaging
- MOCK safety enforcement
- Module-based architecture
- Wizard-configurable adapter support
"""

from .adapter import Adapter, MockLLMAdapter
from .configurable import MockLLMConfigurableAdapter
from .service import MockLLMClient, MockLLMService

__all__ = [
    "MockLLMService",
    "MockLLMClient",
    "MockLLMAdapter",
    "MockLLMConfigurableAdapter",
    "Adapter",
]
