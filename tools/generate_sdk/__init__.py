"""
CIRIS Mobile SDK Generator

Generates a Kotlin Multiplatform API client from the CIRIS OpenAPI spec.

Usage:
    python -m tools.generate_sdk generate    # Full generation
    python -m tools.generate_sdk fetch       # Just fetch OpenAPI spec
    python -m tools.generate_sdk fix         # Just apply fixes to existing generated code
    python -m tools.generate_sdk clean       # Clean generated files
"""

from .generator import SDKGenerator

__all__ = ["SDKGenerator"]
