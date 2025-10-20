"""Database execution helpers for PostgreSQL/SQLite abstraction.

This module provides database-agnostic helper functions to reduce cognitive
complexity in database initialization and migration code.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Set

from ciris_engine.logic.persistence.db.dialect import get_adapter

logger = logging.getLogger(__name__)


def execute_sql_statements(conn: Any, sql_statements: List[str], adapter: Any) -> None:
    """Execute SQL statements using appropriate method for database backend.

    Args:
        conn: Database connection object
        sql_statements: List of SQL statements to execute
        adapter: Database adapter for dialect detection

    PostgreSQL requires individual cursor.execute() calls,
    SQLite can use executescript() for batch execution.
    """
    if adapter.is_postgresql():
        cursor = conn.cursor()
        try:
            for statement in sql_statements:
                if statement.strip():
                    cursor.execute(statement)
        finally:
            cursor.close()
    else:
        # SQLite uses executescript for batch execution
        combined_sql = ";\n".join(sql_statements)
        conn.executescript(combined_sql)


def _update_dollar_quote_state(
    tag: str, in_dollar_quote: bool, current_tag: Optional[str]
) -> tuple[bool, Optional[str]]:
    """Update dollar quote tracking state based on matched tag.

    Args:
        tag: Matched dollar quote tag (e.g., "$$", "$func$")
        in_dollar_quote: Current state - inside dollar-quoted block?
        current_tag: Current opening tag we're tracking

    Returns:
        Tuple of (new_in_dollar_quote, new_current_tag)
    """
    if not in_dollar_quote:
        # Starting a new dollar-quoted block
        return True, tag
    elif tag == current_tag:
        # Found matching closing tag
        return False, None
    return in_dollar_quote, current_tag


def _should_finalize_statement(line: str, in_dollar_quote: bool) -> bool:
    """Check if line terminates a statement (semicolon at end, not in dollar quote).

    Args:
        line: SQL line to check
        in_dollar_quote: Whether we're currently inside a dollar-quoted block

    Returns:
        True if this line terminates a statement
    """
    return ";" in line and not in_dollar_quote and line.strip().endswith(";")


def _finalize_statement(current_statement: List[str]) -> Optional[str]:
    """Finalize current statement by joining and stripping.

    Args:
        current_statement: List of lines making up the statement

    Returns:
        Finalized statement string, or None if empty
    """
    statement = "\n".join(current_statement).strip()
    return statement if statement else None


def split_sql_statements(table_sql: str) -> List[str]:
    """Split multi-statement SQL into individual statements.

    Handles PostgreSQL dollar-quoted blocks correctly, including both
    simple ($$) and tagged ($identifier$) dollar quotes.

    Args:
        table_sql: SQL string potentially containing multiple statements

    Returns:
        List of individual SQL statements (stripped, non-empty)
    """
    import re

    # Quick check: if no dollar quotes, use simple split
    if "$" not in table_sql:
        return [s.strip() for s in table_sql.split(";") if s.strip()]

    statements: List[str] = []
    current_statement: List[str] = []
    in_dollar_quote = False
    current_tag: Optional[str] = None

    # Regex to match dollar quote tags: $$ or $identifier$
    # Matches: $$, $func$, $BODY$, $tag123$, etc.
    dollar_quote_pattern = re.compile(r"\$([a-zA-Z_]\w*)?\$")

    lines = table_sql.split("\n")
    for line in lines:
        # Find all dollar quotes in this line and update state
        matches = list(dollar_quote_pattern.finditer(line))
        for match in matches:
            tag = match.group(0)  # Full match like $$ or $func$
            in_dollar_quote, current_tag = _update_dollar_quote_state(tag, in_dollar_quote, current_tag)

        current_statement.append(line)

        # Split on semicolon only if not in dollar-quoted block
        if _should_finalize_statement(line, in_dollar_quote):
            statement = _finalize_statement(current_statement)
            if statement:
                statements.append(statement)
            current_statement = []

    # Add any remaining statement
    statement = _finalize_statement(current_statement)
    if statement:
        statements.append(statement)

    return statements


def mask_password_in_url(db_url: str) -> str:
    """Mask password in database URL for safe logging.

    Args:
        db_url: Database URL (e.g., postgresql://user:pass@host/db)

    Returns:
        URL with password replaced by ****

    Examples:
        postgresql://user:PASSWORD@host/db -> postgresql://user:****@host/db
        sqlite:///path/to/db.sqlite -> sqlite:///path/to/db.sqlite
    """
    if "://" in db_url and "@" in db_url:
        protocol, rest = db_url.split("://", 1)
        # Find the last @ symbol (separates credentials from host)
        if "@" in rest:
            last_at_index = rest.rfind("@")
            credentials = rest[:last_at_index]
            host = rest[last_at_index + 1 :]
            if ":" in credentials:
                username, _ = credentials.split(":", 1)
                return f"{protocol}://{username}:****@{host}"
    return db_url


def get_applied_migrations(conn: Any) -> Set[str]:
    """Retrieve set of already-applied migration names.

    Args:
        conn: Database connection with migrations table

    Returns:
        Set of migration names that have been applied
    """
    cursor = conn.cursor()
    cursor.execute("SELECT migration_name FROM migrations")
    return {row["migration_name"] for row in cursor.fetchall()}


def get_pending_migrations(migrations_dir: Path, applied_migrations: Set[str]) -> List[Path]:
    """Get list of pending migration files in order.

    Args:
        migrations_dir: Directory containing migration SQL files
        applied_migrations: Set of migration names already applied

    Returns:
        List of migration file paths sorted by name, excluding applied ones
    """
    all_migrations = sorted(migrations_dir.glob("*.sql"))
    return [m for m in all_migrations if m.name not in applied_migrations]


def record_migration(conn: Any, migration_name: str, adapter: Any) -> None:
    """Record a migration as applied.

    Args:
        conn: Database connection
        migration_name: Name of migration file (e.g., "001_initial.sql")
        adapter: Database adapter for parameter placeholder detection
    """
    cursor = conn.cursor()
    applied_at = datetime.now().isoformat()

    if adapter.is_postgresql():
        cursor.execute(
            "INSERT INTO migrations (migration_name, applied_at) VALUES (%s, %s)",
            (migration_name, applied_at),
        )
    else:
        cursor.execute(
            "INSERT INTO migrations (migration_name, applied_at) VALUES (?, ?)",
            (migration_name, applied_at),
        )
