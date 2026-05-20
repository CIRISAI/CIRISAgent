"""Database fixtures for tests."""

import os
import tempfile

import pytest

from ciris_engine.logic import persistence
from ciris_engine.logic.persistence import initialize_database


@pytest.fixture
def test_db():
    """Create a temporary test database for each test."""
    from ciris_engine.logic.persistence.db import core

    # Create a temporary database file
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Ensure the database file is writable
    os.chmod(db_path, 0o666)

    # Initialize the database
    initialize_database(db_path)

    # Set the core module-level test override
    original_test_db_path = core._test_db_path
    core._test_db_path = db_path

    # Also set legacy persistence module paths for backward compatibility
    original_db_path = persistence._db_path if hasattr(persistence, "_db_path") else None
    persistence._db_path = db_path

    # Re-initialize persistence with test database
    if hasattr(persistence, "_init_db"):
        persistence._init_db()

    yield db_path

    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass

    # Restore original database paths
    core._test_db_path = original_test_db_path
    if original_db_path:
        persistence._db_path = original_db_path
        if hasattr(persistence, "_init_db"):
            persistence._init_db()


@pytest.fixture
def clean_db(test_db):
    """Ensure database is clean before each test.

    `test_db` already mkstemps a fresh file and bootstraps persist, so the
    `cirislens.*` / `cirisgraph.*` tables start empty. This fixture clears
    them defensively (best-effort) in case a prior fixture in the same
    test wired the persist engine and wrote rows.
    """
    from ciris_engine.logic.persistence.db.core import get_db_connection

    _PERSIST_TABLES = [
        "cirislens_service_correlations",
        "cirislens_thoughts",
        "cirislens_tasks",
        "cirisgraph_edges",
        "cirisgraph_nodes",
        "cirislens_feedback_mappings",
        "cirislens_audit_log",
        "cirislens_tickets",
    ]
    with get_db_connection(test_db) as conn:
        for table in _PERSIST_TABLES:
            try:
                conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass  # table absent — nothing to clear
        conn.commit()

    return test_db
