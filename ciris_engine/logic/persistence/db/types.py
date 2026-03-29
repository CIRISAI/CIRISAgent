"""
Database type definitions.

Contains shared types used across the db module to avoid circular imports.
"""

from enum import Enum


class Dialect(str, Enum):
    """Supported database dialects."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class ConflictResolution(str, Enum):
    """How to handle conflicts during INSERT operations."""

    IGNORE = "ignore"  # INSERT OR IGNORE / ON CONFLICT DO NOTHING
    REPLACE = "replace"  # INSERT OR REPLACE / ON CONFLICT DO UPDATE
    ERROR = "error"  # Let database raise error (default behavior)
