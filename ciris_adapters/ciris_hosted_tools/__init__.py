"""
CIRIS Hosted Tools Adapter.

Provides access to CIRIS-hosted tools via the CIRIS proxy, including:
- web_search: Search the web using Brave Search API

These tools require platform-level security (device attestation) to prevent abuse.
Currently supported on Android with Google Play Integrity.

Credit Model:
- 10 free searches for new users (one-time welcome bonus)
- 3 free searches per day (resets at UTC midnight)
- 1 credit per search after free tier exhausted
"""

from .adapter import Adapter, CIRISHostedToolsAdapter
from .services import CIRISHostedToolService, ToolBalance

__all__ = [
    "Adapter",
    "CIRISHostedToolsAdapter",
    "CIRISHostedToolService",
    "ToolBalance",
]
