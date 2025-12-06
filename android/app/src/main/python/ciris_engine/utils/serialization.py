"""Serialization utilities for CIRIS."""

from datetime import datetime
from typing import Any, Optional


def serialize_timestamp(timestamp: datetime, _info: Any = None) -> Optional[str]:
    """
    Standard timestamp serialization for Pydantic models.

    Converts datetime to ISO format string for JSON serialization.

    Args:
        timestamp: The datetime to serialize
        _info: Pydantic serialization info (unused but required for field_serializer)

    Returns:
        ISO format string or None if timestamp is None
    """
    return timestamp.isoformat() if timestamp else None


def serialize_datetime(dt: datetime) -> Optional[str]:
    """
    Serialize datetime to ISO format.

    Simple version without the _info parameter for non-Pydantic use.

    Args:
        dt: The datetime to serialize

    Returns:
        ISO format string or None if dt is None
    """
    return dt.isoformat() if dt else None
