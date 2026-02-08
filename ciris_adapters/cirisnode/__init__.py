"""
CIRISNode adapter for WBD, benchmarks, and agent event tracking.

This adapter provides tools for interacting with CIRISNode services:
- Wisdom-Based Deferral (WBD) submission and resolution
- HE-300 and SimpleBench benchmarks
- Agent event tracking and observability

Production deployment: https://admin.ethicsengine.org
"""

from ciris_adapters.cirisnode.client import CIRISNodeClient
from ciris_adapters.cirisnode.services import CIRISNodeToolService

__all__ = ["CIRISNodeClient", "CIRISNodeToolService"]
