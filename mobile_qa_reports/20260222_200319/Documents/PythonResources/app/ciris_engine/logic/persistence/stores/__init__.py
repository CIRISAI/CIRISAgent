"""Persistence store modules for database operations.

This package provides database-agnostic store modules following the separation
of concerns pattern. Each store module handles database operations for a specific
domain (authentication, secrets, etc.) using get_db_connection() to support both
SQLite and PostgreSQL.

Pattern: Business logic services call store functions for all database operations.
"""

from ciris_engine.logic.persistence.stores import authentication_store

__all__ = ["authentication_store"]
