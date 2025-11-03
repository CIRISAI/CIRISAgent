"""Database fixtures for tests."""

import os
import tempfile

import pytest

from ciris_engine.logic import persistence
from ciris_engine.logic.persistence import initialize_database


@pytest.fixture
def test_db():
    """Create a temporary test database for each test."""
    # Create a temporary database file
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Ensure the database file is writable
    os.chmod(db_path, 0o666)

    # Initialize the database
    initialize_database(db_path)

    # Set the persistence module to use our test database
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

    # Restore original database path
    if original_db_path:
        persistence._db_path = original_db_path
        if hasattr(persistence, "_init_db"):
            persistence._init_db()


@pytest.fixture
def clean_db(test_db):
    """Ensure database is clean before each test."""
    # Clear all tables
    from ciris_engine.logic.persistence.db.core import get_db_connection

    with get_db_connection(test_db) as conn:
        # Clear tables in reverse dependency order
        conn.execute("DELETE FROM service_correlations")
        conn.execute("DELETE FROM thoughts")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM graph_edges")
        conn.execute("DELETE FROM graph_nodes")
        conn.execute("DELETE FROM feedback_mappings")
        conn.execute("DELETE FROM audit_log")
        conn.execute("DELETE FROM dsar_tickets")
        conn.commit()

    return test_db
