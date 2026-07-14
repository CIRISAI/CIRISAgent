"""
Database dialect adapter for SQLite and PostgreSQL compatibility.

Post-2.9.7 (#896) this module is dialect *detection* only: ciris-persist's
Engine owns all SQL execution, so the legacy per-statement translation
helpers (upsert, json_extract, placeholder rewriting on raw connections)
are gone. What survives is connection-string parsing plus the
`placeholder()` / `is_postgresql()` probes consumed by the few remaining
SQL-string builders (wise_authority) and startup logging
(initialization_steps).
"""

from typing import Optional
from urllib.parse import unquote, urlparse

from ciris_engine.logic.persistence.db.types import Dialect


def parse_postgres_url(url: str) -> tuple[str, str, str, int, str, str, str]:
    """Parse PostgreSQL URL handling special characters in password.

    Handles passwords with special characters (@, }, ], {, etc.) that break urlparse.

    Args:
        url: PostgreSQL connection string

    Returns:
        Tuple of (scheme, username, password, port, host, database, params)

    Raises:
        ValueError: If URL format is invalid
    """
    import re

    # Pattern: postgresql://username:password@host:port/database?params
    # Password may contain special chars INCLUDING @, so we need to parse carefully
    # The password is everything after the first : and before the LAST @
    # Use non-greedy match for scheme/user, greedy for password (can contain @ or be empty)
    pattern = r"^(postgres(?:ql)?):\/\/([^:]+):(.*)@([^:\/\?]+):(\d+)\/([^?]+)(\?.*)?$"
    match = re.match(pattern, url)

    if not match:
        raise ValueError(f"Invalid PostgreSQL URL format: {url}")

    scheme, username, password_and_host, host, port, database, params = match.groups()

    # Now we need to split password from host at the LAST @
    # Find the last @ that's followed by host:port pattern
    # The host part should not contain @ (it's the part after the last @)
    last_at_idx = password_and_host.rfind("@")
    if last_at_idx == -1:
        # No @ found - this means password_and_host is just the password (empty host captured)
        password = password_and_host
    else:
        # Split at the last @
        password = password_and_host[:last_at_idx]
        # The part after @ should match our captured host
        rest = password_and_host[last_at_idx + 1 :]
        if rest != host:
            # Host mismatch - means our regex didn't capture correctly
            # Fall back to treating everything as password
            password = password_and_host

    # URL-decode the password component (handles %XX encoding)
    password = unquote(password) if password else ""
    params = params or ""

    return scheme, username, password, int(port), host, database, params


class DialectAdapter:
    """Detects the database dialect from a connection string.

    Backward compatible (SQLite default); the connection string determines
    the dialect. Consumers use `placeholder()` / `is_postgresql()` to build
    dialect-correct SQL strings — execution is owned by ciris-persist.
    """

    def __init__(self, connection_string: str):
        """Initialize adapter from connection string.

        Args:
            connection_string: Database URL (sqlite://path or postgresql://...)
        """
        # Quick check for PostgreSQL scheme
        if connection_string.startswith(("postgresql://", "postgres://")):
            # Use robust parser that handles special characters in passwords
            try:
                _scheme, _user, _password, _port, _host, _database, _params = parse_postgres_url(connection_string)
                self.dialect = Dialect.POSTGRESQL
                self.db_url = connection_string
                self.db_path = ""  # Empty string for PostgreSQL (not a file path)
            except ValueError as e:
                # Fall back to urlparse if custom parser fails
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to parse PostgreSQL URL with custom parser: {e}")
                logger.warning("Falling back to standard urlparse - may fail with special chars in password")

                parsed = urlparse(connection_string)
                self.dialect = Dialect.POSTGRESQL
                self.db_url = connection_string
                self.db_path = ""
        else:
            # Use standard urlparse for SQLite and other schemes
            parsed = urlparse(connection_string)

            if parsed.scheme in ("sqlite", "sqlite3", ""):
                self.dialect = Dialect.SQLITE
                # For SQLite, store the path (with or without leading //)
                self.db_path = parsed.path or connection_string
                self.db_url = connection_string
            else:
                # Default to SQLite for backward compatibility
                self.dialect = Dialect.SQLITE
                self.db_path = connection_string
                self.db_url = connection_string

    def placeholder(self) -> str:
        """Return parameter placeholder for the target dialect.

        Returns:
            '?' for SQLite, '%s' for PostgreSQL
        """
        if self.dialect == Dialect.SQLITE:
            return "?"
        return "%s"

    def is_sqlite(self) -> bool:
        """Check if using SQLite dialect."""
        return self.dialect == Dialect.SQLITE

    def is_postgresql(self) -> bool:
        """Check if using PostgreSQL dialect."""
        return self.dialect == Dialect.POSTGRESQL


# Global adapter instance
_adapter: Optional[DialectAdapter] = None


def init_dialect(connection_string: str = "data/ciris.db") -> DialectAdapter:
    """Initialize global dialect adapter.

    Args:
        connection_string: Database URL (defaults to SQLite for backward compatibility)

    Returns:
        Initialized DialectAdapter instance
    """
    global _adapter
    _adapter = DialectAdapter(connection_string)
    return _adapter


def get_adapter() -> DialectAdapter:
    """Get global dialect adapter instance.

    Returns:
        Global DialectAdapter instance

    Raises:
        RuntimeError: If adapter not initialized
    """
    if _adapter is None:
        # Auto-initialize with SQLite default for backward compatibility
        return init_dialect()
    return _adapter
