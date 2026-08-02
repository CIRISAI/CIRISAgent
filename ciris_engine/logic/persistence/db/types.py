"""
Database type definitions.

Contains shared types used across the db module to avoid circular imports.
"""

from enum import Enum


class Dialect(str, Enum):
    """Supported database dialects."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
