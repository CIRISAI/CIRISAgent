"""SQL dialect implementations."""

from typing import Union

from .base import BaseSQLDialect
from .mysql import MySQLDialect
from .postgresql import PostgreSQLDialect
from .sqlite import SQLiteDialect

__all__ = ["BaseSQLDialect", "SQLiteDialect", "PostgreSQLDialect", "MySQLDialect", "get_dialect"]


DialectType = Union[SQLiteDialect, PostgreSQLDialect, MySQLDialect]


def get_dialect(dialect_name: str) -> DialectType:
    """Get dialect instance by name.

    Args:
        dialect_name: Dialect name (sqlite, postgresql, mysql)

    Returns:
        Dialect instance

    Raises:
        ValueError: If dialect not supported
    """
    normalized_name = dialect_name.lower()

    if normalized_name == "sqlite":
        return SQLiteDialect()
    elif normalized_name == "postgresql":
        return PostgreSQLDialect()
    elif normalized_name == "mysql":
        return MySQLDialect()
    else:
        raise ValueError(f"Unsupported dialect: {dialect_name}. Supported: sqlite, postgresql, mysql")
