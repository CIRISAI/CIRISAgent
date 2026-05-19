from ciris_engine.logic.config import get_sqlite_db_full_path

from .core import (
    get_connection_diagnostics,
    get_db_connection,
    get_graph_edges_table_schema_sql,
    get_graph_nodes_table_schema_sql,
    get_service_correlations_table_schema_sql,
    initialize_database,
)
from .migration_runner import MIGRATIONS_BASE_DIR, run_migrations

# `get_db_connection` is the legacy SQLite bootstrap helper. Post-2.9.0
# all production writes route through ciris-persist (`engine.*` calls
# in persistence/models). It survives here only for legacy fixtures
# that seed SQLite directly. Raises `RuntimeError` on `postgres://`
# DSNs — Postgres is owned entirely by persist's sqlx backend.
__all__ = [
    "get_connection_diagnostics",
    "get_db_connection",
    "initialize_database",
    "run_migrations",
    "MIGRATIONS_BASE_DIR",
    "get_sqlite_db_full_path",
    "get_graph_nodes_table_schema_sql",
    "get_graph_edges_table_schema_sql",
    "get_service_correlations_table_schema_sql",
]
