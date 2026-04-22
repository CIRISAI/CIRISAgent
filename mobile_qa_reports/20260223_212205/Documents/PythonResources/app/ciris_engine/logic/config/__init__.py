"""
Configuration module for CIRIS Engine.

Provides graph-based configuration with bootstrap support.
"""

from .bootstrap import ConfigBootstrap
from .config_accessor import ConfigAccessor
from .db_paths import (
    get_audit_db_full_path,
    get_graph_memory_full_path,
    get_secrets_db_full_path,
    get_sqlite_db_full_path,
)
from .env_utils import get_env_var

__all__ = [
    "ConfigBootstrap",
    "ConfigAccessor",
    "get_env_var",
    "get_sqlite_db_full_path",
    "get_secrets_db_full_path",
    "get_audit_db_full_path",
    "get_graph_memory_full_path",
]
