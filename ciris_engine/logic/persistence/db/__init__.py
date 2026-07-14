from ciris_engine.logic.config import get_sqlite_db_full_path

from .core import initialize_database

# Post-2.9.0 all production reads + writes route through ciris-persist
# (`engine.*` calls in persistence/models). The legacy SQLite connection
# helper (`get_db_connection`, retry wrappers, iOS serialized connections)
# was deleted in 2.9.7 (#896) — the persist Engine owns all pooling.
# `initialize_database` bootstraps persist's Engine and runs the one-shot
# A0a/A0b legacy migrations.
__all__ = [
    "initialize_database",
    "get_sqlite_db_full_path",
]
