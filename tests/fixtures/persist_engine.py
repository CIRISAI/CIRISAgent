"""Shared persist-engine wiring fixture for Lane T* absorption tests.

Tests that exercise persistence/models/* functions need a real
ciris-persist Engine wired into the module-global at
`ciris_engine.logic.persistence.models.graph._engine`.

This fixture:
  1. Creates a temp SQLite-backed persist Engine.
  2. Captures and replaces the module-global, restoring on teardown.
  3. Tears down by clearing the engine + unlinking the temp file.

Use with::

    @pytest.fixture
    def persist_db(persist_engine):
        return persist_engine.db_path

The previous tests used `get_db_connection` against the same temp DB; now
that the absorption-routed functions go through persist, they need the
engine wired instead. This shared fixture is the migration's "wire once,
reuse everywhere" pattern.
"""

from __future__ import annotations

import os
import tempfile
from typing import Iterator

import pytest

from ciris_persist import Engine  # type: ignore[import-untyped]


@pytest.fixture
def persist_engine() -> Iterator[Engine]:
    """Wire a fresh persist Engine into persistence.models.graph for the test.

    Yields the Engine instance for direct use; restores the prior
    module-global on teardown so tests can run in any order.
    """
    # Lazy import to avoid pulling persistence.models.graph during conftest
    # collection (some tests check module-level side effects).
    import ciris_engine.logic.persistence.models.graph as _graph_mod
    from ciris_engine.logic.persistence.models.graph import set_persist_engine

    prior_engine = _graph_mod._engine
    prior_dsn = _graph_mod._engine_dsn

    with tempfile.NamedTemporaryFile(suffix="-persist.db", delete=False) as pf:
        db_path = pf.name

    engine = Engine(f"sqlite:///{db_path}", "test-key")
    set_persist_engine(engine, dsn=f"sqlite:///{db_path}")

    try:
        yield engine
    finally:
        _graph_mod._engine = prior_engine
        _graph_mod._engine_dsn = prior_dsn
        try:
            os.unlink(db_path)
        except OSError:
            pass
