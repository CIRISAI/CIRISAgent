"""Database fixtures for tests."""

import os
import tempfile

import pytest

from ciris_engine.logic import persistence
from ciris_engine.logic.persistence import initialize_database


# Every persist Engine wired during a test, captured by wrapping
# `set_persist_engine`. ciris-persist v1.8.x's Engine is a process-singleton:
# a second construction with a different DSN raises EngineConfigMismatch. Many
# test fixtures wire an engine and on teardown only restore the module global
# (`graph._engine = prior`) WITHOUT closing the Rust engine — so the singleton
# leaks invisibly. Tracking every engine here lets the autouse teardown close
# them regardless of whether a fixture nulled the global.
_wired_engines: list = []
_tracker_installed = False


def _install_engine_tracker() -> None:
    """Wrap graph.set_persist_engine so every wired Engine is tracked.

    Idempotent. All engine construction (initialize_database via
    _bootstrap_persist_engine, and the persist_engine fixture) funnels
    through set_persist_engine, so this captures every engine.
    """
    global _tracker_installed
    if _tracker_installed:
        return
    from ciris_engine.logic.persistence.models import graph as graph_persistence

    _original = graph_persistence.set_persist_engine

    def _tracked(engine, dsn=None):  # type: ignore[no-untyped-def]
        if engine is not None:
            _wired_engines.append(engine)
        return _original(engine, dsn)

    graph_persistence.set_persist_engine = _tracked  # type: ignore[assignment]
    _tracker_installed = True


def _release_persist_engine() -> None:
    """Close every persist Engine wired during the test and unwire the global.

    ciris-persist v1.8.x's Engine is a process-singleton — a leaked engine
    blocks the next test's construction with EngineConfigMismatch. Closing
    also frees the underlying tokio runtime + connection pool.
    """
    from ciris_engine.logic.persistence.models import graph as graph_persistence

    engines = list(_wired_engines)
    current = graph_persistence.get_persist_engine()
    if current is not None:
        engines.append(current)

    seen = set()
    for engine in engines:
        if id(engine) in seen:
            continue
        seen.add(id(engine))
        try:
            engine.close()
        except Exception:
            pass

    _wired_engines.clear()
    graph_persistence._engine = None
    graph_persistence._engine_dsn = None


@pytest.fixture
def test_db():
    """Create a temporary test database for each test."""
    from ciris_engine.logic.persistence.db import core

    # v1.8.x persist Engine is a process-singleton: release any engine a
    # prior test pinned before bootstrapping this test's own temp DB.
    _release_persist_engine()

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

    # Cleanup — close this test's engine so the next test starts clean.
    _release_persist_engine()
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
