"""
MockLLM modular service.

This is the first modular service in CIRIS, demonstrating:
- Self-contained service packaging
- MOCK safety enforcement
- Module-based architecture
"""

from .service import MockLLMClient, MockLLMService

__all__ = ["MockLLMService", "MockLLMClient"]
