"""Persistence schemas v1.

SQLite schemas are in sqlite/tables.py
PostgreSQL schemas are in postgres/tables.py
"""

# For backward compatibility, export SQLite schemas by default
from .sqlite.tables import (
    ALL_TABLES,
    AUDIT_LOG_TABLE_V1,
    AUDIT_ROOTS_TABLE_V1,
    AUDIT_SIGNING_KEYS_TABLE_V1,
    FEEDBACK_MAPPINGS_TABLE_V1,
    GRAPH_EDGES_TABLE_V1,
    GRAPH_NODES_TABLE_V1,
    SERVICE_CORRELATIONS_TABLE_V1,
    TASKS_TABLE_V1,
    THOUGHTS_TABLE_V1,
    WA_CERT_TABLE_V1,
)

__all__ = [
    "TASKS_TABLE_V1",
    "THOUGHTS_TABLE_V1",
    "FEEDBACK_MAPPINGS_TABLE_V1",
    "GRAPH_NODES_TABLE_V1",
    "GRAPH_EDGES_TABLE_V1",
    "SERVICE_CORRELATIONS_TABLE_V1",
    "AUDIT_LOG_TABLE_V1",
    "AUDIT_ROOTS_TABLE_V1",
    "AUDIT_SIGNING_KEYS_TABLE_V1",
    "WA_CERT_TABLE_V1",
    "ALL_TABLES",
]
