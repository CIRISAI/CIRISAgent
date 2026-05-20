from ciris_engine.logic.config import get_sqlite_db_full_path

from .core import (
    get_connection_diagnostics,
    get_db_connection,
    initialize_database,
)

# `get_db_connection` is the legacy SQLite connection helper. Post-2.9.0
# all production reads + writes route through ciris-persist (`engine.*`
# calls in persistence/models). It survives only for test fixtures that
# seed a SQLite file directly, and raises `RuntimeError` on `postgres://`
# DSNs — Postgres is owned entirely by persist's sqlx backend. The legacy
# CREATE TABLE / migration machinery (migration_runner.py, the
# migrations/*.sql files, the table-DDL modules) was removed in 2.9.0;
# `initialize_database` now just bootstraps persist's Engine.
__all__ = [
    "get_connection_diagnostics",
    "get_db_connection",
    "initialize_database",
    "get_sqlite_db_full_path",
]
