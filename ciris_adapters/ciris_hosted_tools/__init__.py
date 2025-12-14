"""
CIRIS Hosted Tools Adapter.

Provides access to CIRIS-hosted tools via the CIRIS proxy, including:
- web_search: Search the web using Brave Search API

These tools require platform-level security (device attestation) to prevent abuse.
Currently supported on Android with Google Play Integrity.
"""

from .adapter import Adapter, CIRISHostedToolsAdapter
from .services import CIRISHostedToolService

__all__ = [
    "Adapter",
    "CIRISHostedToolsAdapter",
    "CIRISHostedToolService",
]
