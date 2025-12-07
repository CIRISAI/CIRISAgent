"""Authentication Store - Database operations for WA certificates.

This module provides a database-agnostic persistence layer for Wise Authority (WA)
certificates, supporting both SQLite and PostgreSQL backends via get_db_connection().

Pattern: Follows SecretsService store pattern for separation of concerns.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ciris_engine.logic.persistence.db import get_db_connection
from ciris_engine.schemas.services.authority_core import OAuthIdentityLink, WACertificate

logger = logging.getLogger(__name__)


def _row_to_wa(row_dict: Dict[str, Any]) -> WACertificate:
    """Convert a database row dictionary to a WACertificate instance.

    Args:
        row_dict: Database row as dictionary

    Returns:
        WACertificate instance
    """
    from ciris_engine.logic.persistence.stores.auth_helpers import build_wa_certificate_dict

    wa_dict = build_wa_certificate_dict(row_dict)
    return WACertificate(**wa_dict)


def init_auth_database(db_path: str) -> None:
    """Initialize authentication database tables if needed.

    Args:
        db_path: Database connection string (SQLite path or PostgreSQL URL)
    """
    from ciris_engine.logic.persistence.db.dialect import DialectAdapter

    # Create adapter from db_path to determine database type
    # This avoids race conditions with global adapter in parallel tests
    adapter = DialectAdapter(db_path)
    is_postgres = adapter.is_postgresql()

    # Import appropriate table definition based on database type
    if is_postgres:
        from ciris_engine.schemas.persistence.postgres.tables import WA_CERT_TABLE_V1
    else:
        from ciris_engine.schemas.persistence.sqlite.tables import WA_CERT_TABLE_V1

    with get_db_connection(db_path=db_path) as conn:
        if is_postgres:
            # PostgreSQL: Execute statements individually
            statements = [s.strip() for s in WA_CERT_TABLE_V1.split(";") if s.strip()]
            cursor = conn.cursor()
            for statement in statements:
                cursor.execute(statement)
            cursor.close()
        else:
            # SQLite: Use executescript and PRAGMA
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(WA_CERT_TABLE_V1)

        # Backfill newer columns when running against existing databases
        # Get table info to check existing columns
        cursor = conn.cursor()

        if is_postgres:
            # PostgreSQL: Query information_schema
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'wa_cert'
            """
            )
            existing_columns = {row[0] if isinstance(row, tuple) else row["column_name"] for row in cursor.fetchall()}
        else:
            # SQLite: Use PRAGMA
            cursor.execute("PRAGMA table_info(wa_cert)")
            existing_columns = {row[1] for row in cursor.fetchall()}

        # Column migrations for backward compatibility
        column_migrations = {
            "custom_permissions_json": "ALTER TABLE wa_cert ADD COLUMN custom_permissions_json TEXT",
            "adapter_name": "ALTER TABLE wa_cert ADD COLUMN adapter_name TEXT",
            "adapter_metadata_json": "ALTER TABLE wa_cert ADD COLUMN adapter_metadata_json TEXT",
            "oauth_links_json": "ALTER TABLE wa_cert ADD COLUMN oauth_links_json TEXT",
        }

        for column_name, ddl in column_migrations.items():
            if column_name not in existing_columns:
                cursor.execute(ddl)

        cursor.close()
        conn.commit()


def store_wa_certificate(wa: WACertificate, db_path: str) -> None:
    """Store a WA certificate in the database.

    Args:
        wa: WACertificate to store
        db_path: Database connection string
    """
    from datetime import datetime

    with get_db_connection(db_path=db_path) as conn:
        # Convert WA to dict for insertion
        wa_dict = wa.model_dump()

        # Map schema fields to database fields
        db_dict = {
            "wa_id": wa_dict["wa_id"],
            "name": wa_dict["name"],
            "role": wa_dict["role"],
            "pubkey": wa_dict["pubkey"],
            "jwt_kid": wa_dict["jwt_kid"],
            "password_hash": wa_dict.get("password_hash"),
            "api_key_hash": wa_dict.get("api_key_hash"),
            "oauth_provider": wa_dict.get("oauth_provider"),
            "oauth_external_id": wa_dict.get("oauth_external_id"),
            "veilid_id": wa_dict.get("veilid_id"),
            "oauth_links_json": (
                json.dumps([link.model_dump(mode="json") for link in wa_dict.get("oauth_links", [])])
                if wa_dict.get("oauth_links")
                else None
            ),
            "auto_minted": int(wa_dict.get("auto_minted", False)),
            "parent_wa_id": wa_dict.get("parent_wa_id"),
            "parent_signature": wa_dict.get("parent_signature"),
            "scopes_json": wa_dict["scopes_json"],
            "custom_permissions_json": wa_dict.get("custom_permissions_json"),
            "adapter_id": wa_dict.get("adapter_id"),
            "adapter_name": wa_dict.get("adapter_name"),
            "adapter_metadata_json": wa_dict.get("adapter_metadata_json"),
            "token_type": wa_dict.get("token_type", "standard"),
            "created": (
                wa_dict["created_at"].isoformat()
                if isinstance(wa_dict["created_at"], datetime)
                else wa_dict["created_at"]
            ),
            "last_login": (
                wa_dict["last_auth"].isoformat()
                if wa_dict.get("last_auth") and isinstance(wa_dict["last_auth"], datetime)
                else wa_dict.get("last_auth")
            ),
            "active": 1,  # New WAs are active by default
        }

        columns = ", ".join(db_dict.keys())
        placeholders = ", ".join(["?" for _ in db_dict])

        cursor = conn.cursor()
        cursor.execute(f"INSERT INTO wa_cert ({columns}) VALUES ({placeholders})", list(db_dict.values()))
        cursor.close()
        conn.commit()


def get_wa_by_id(wa_id: str, db_path: str) -> Optional[WACertificate]:
    """Get WA certificate by ID.

    Args:
        wa_id: WA certificate ID
        db_path: Database connection string

    Returns:
        WACertificate if found, None otherwise
    """
    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wa_cert WHERE wa_id = ? AND active = 1", (wa_id,))
        row = cursor.fetchone()
        cursor.close()

        if row:
            # Convert row to dict
            row_dict = (
                dict(row)
                if hasattr(row, "keys")
                else {column[0]: row[i] for i, column in enumerate(cursor.description)}
            )
            return _row_to_wa(row_dict)
        return None


def get_wa_by_kid(jwt_kid: str, db_path: str) -> Optional[WACertificate]:
    """Get WA certificate by JWT key ID.

    Args:
        jwt_kid: JWT key identifier
        db_path: Database connection string

    Returns:
        WACertificate if found, None otherwise
    """
    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wa_cert WHERE jwt_kid = ? AND active = 1", (jwt_kid,))
        row = cursor.fetchone()
        cursor.close()

        if row:
            row_dict = (
                dict(row)
                if hasattr(row, "keys")
                else {column[0]: row[i] for i, column in enumerate(cursor.description)}
            )
            return _row_to_wa(row_dict)
        return None


def get_wa_by_oauth(provider: str, external_id: str, db_path: str) -> Optional[WACertificate]:
    """Get WA certificate by OAuth identity.

    Args:
        provider: OAuth provider name
        external_id: External OAuth ID
        db_path: Database connection string

    Returns:
        WACertificate if found, None otherwise
    """
    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM wa_cert WHERE oauth_provider = ? AND oauth_external_id = ? AND active = 1",
            (provider, external_id),
        )
        row = cursor.fetchone()

        if row:
            row_dict = (
                dict(row)
                if hasattr(row, "keys")
                else {column[0]: row[i] for i, column in enumerate(cursor.description)}
            )
            cursor.close()
            return _row_to_wa(row_dict)

        # Fallback: search linked identities stored in JSON
        cursor.execute("SELECT * FROM wa_cert WHERE oauth_links_json IS NOT NULL AND active = 1")
        for link_row in cursor.fetchall():
            link_row_dict = (
                dict(link_row)
                if hasattr(link_row, "keys")
                else {column[0]: link_row[i] for i, column in enumerate(cursor.description)}
            )
            wa = _row_to_wa(link_row_dict)
            for link in wa.oauth_links:
                if link.provider == provider and link.external_id == external_id:
                    cursor.close()
                    return wa

        cursor.close()
        return None


def get_wa_by_adapter(adapter_id: str, db_path: str) -> Optional[WACertificate]:
    """Get WA certificate by adapter ID.

    Args:
        adapter_id: Adapter identifier
        db_path: Database connection string

    Returns:
        WACertificate if found, None otherwise
    """
    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM wa_cert WHERE adapter_id = ? AND active = 1", (adapter_id,))
        row = cursor.fetchone()
        cursor.close()

        if row:
            row_dict = (
                dict(row)
                if hasattr(row, "keys")
                else {column[0]: row[i] for i, column in enumerate(cursor.description)}
            )
            return _row_to_wa(row_dict)
        return None


def update_wa_certificate(wa_id: str, updates: Dict[str, Any], db_path: str) -> None:
    """Update WA certificate fields.

    Args:
        wa_id: WA certificate ID to update
        updates: Dictionary of field names and values to update
        db_path: Database connection string
    """
    from datetime import datetime

    if not updates:
        return

    # Handle datetime fields
    processed_updates = {}
    for key, value in updates.items():
        if isinstance(value, datetime):
            processed_updates[key] = value.isoformat()
        else:
            processed_updates[key] = value

    set_clause = ", ".join([f"{key} = ?" for key in processed_updates.keys()])
    values = list(processed_updates.values()) + [wa_id]

    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE wa_cert SET {set_clause} WHERE wa_id = ?", values)
        cursor.close()
        conn.commit()


def list_wa_certificates(active_only: bool, db_path: str) -> List[WACertificate]:
    """List all WA certificates.

    Args:
        active_only: If True, only return active certificates
        db_path: Database connection string

    Returns:
        List of WACertificate objects
    """
    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()

        if active_only:
            query = "SELECT * FROM wa_cert WHERE active = 1 ORDER BY created DESC"
        else:
            query = "SELECT * FROM wa_cert ORDER BY created DESC"

        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()

        result = []
        for row in rows:
            row_dict = (
                dict(row)
                if hasattr(row, "keys")
                else {column[0]: row[i] for i, column in enumerate(cursor.description)}
            )
            result.append(_row_to_wa(row_dict))

        return result


def get_certificate_counts(db_path: str) -> Dict[str, int]:
    """Get counts of certificates by status and role.

    Args:
        db_path: Database connection string

    Returns:
        Dictionary with certificate counts
    """
    from typing import cast

    from ciris_engine.logic.persistence.db.dialect import DialectAdapter

    counts: Dict[str, Any] = {"total": 0, "active": 0, "revoked": 0, "by_role": cast(Dict[str, int], {})}

    try:
        # Create adapter from db_path to avoid race conditions in parallel tests
        adapter = DialectAdapter(db_path)
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()

            # Total certificates
            cursor.execute("SELECT COUNT(*) FROM wa_cert")
            counts["total"] = adapter.extract_scalar(cursor.fetchone()) or 0

            # Active certificates
            cursor.execute("SELECT COUNT(*) FROM wa_cert WHERE active = 1")
            counts["active"] = adapter.extract_scalar(cursor.fetchone()) or 0

            # Revoked certificates
            cursor.execute("SELECT COUNT(*) FROM wa_cert WHERE active = 0")
            counts["revoked"] = adapter.extract_scalar(cursor.fetchone()) or 0

            # Count by role
            cursor.execute("SELECT role, COUNT(*) FROM wa_cert WHERE active = 1 GROUP BY role")
            for role, count in cursor.fetchall():
                counts["by_role"][role] = count

            cursor.close()
    except Exception as e:
        logger.warning(f"Failed to get certificate counts: {e}")

    return counts


def check_database_health(db_path: str) -> bool:
    """Check if the authentication database is accessible.

    Args:
        db_path: Database connection string

    Returns:
        True if database is healthy, False otherwise
    """
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
        return True
    except Exception as e:
        logger.warning(f"Authentication database health check failed: {e}")
        return False
