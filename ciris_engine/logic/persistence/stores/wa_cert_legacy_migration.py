"""Legacy `wa_cert` recovery for long-jump upgrades (2.7.x -> 2.9.x).

The bug this closes
-------------------
Pre-2.9.0 the authentication store was raw sqlite3 against a `wa_cert`
table in whatever database the caller handed it — and the caller handed it
the **audit** database (`ciris_audit.db`). From 2.9.0 the store reroutes
every read and write through the ciris-persist engine, whose `wa_cert`
substrate lives in the **main** database as `cirislens_wa_cert`
(see `authentication_store.py`).

An agent upgraded straight from 2.7.x therefore boots perfectly GREEN —
both listeners answer 200, zero ERROR/CRITICAL incidents — while the
pre-existing owner cannot log in. Their certificate was never lost; the
new read path simply looks somewhere else. The only rows the node's store
holds after such a boot are the observers freshly minted by the adapters.

What this module does
---------------------
Copies legacy `wa_cert` rows into the store the node actually reads, once
per boot, idempotently:

* **Never invents a certificate.** Only rows that already exist are copied.
  An absent legacy database, or one with no `wa_cert` table, is a fresh
  install — logged at INFO, no error.
* **Never overwrites.** A `wa_id` (or `jwt_kid`) already present in the
  destination is left exactly as it is. This is insert-only; an older
  legacy row can never clobber a newer live one.
* **Preserves `password_hash` byte-for-byte.** The hash is PBKDF2
  `base64(salt||key)` (salt 32 / key 32 / 100k iterations, see
  `AuthenticationService.hash_password`) and the node's verifier is
  compatible by construction. A migration that mangles the hash is a
  migration that leaves the owner locked out, which is the whole bug.
* **Never fails the boot.** Every path is wrapped; failures log at ERROR
  and return. An agent that will not start is worse than one whose owner
  must re-run setup — but it must say so loudly, because a silent
  migration is exactly how this class of bug hides.

Logging carries `wa_id` and `name` for every import. Neither is a secret —
`/v1/auth/owner-hint` serves the name unauthenticated — but the
`password_hash` is never logged, at any level.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from ciris_engine.schemas.services.authority_core import OAuthIdentityLink, WACertificate

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ciris_engine.schemas.config.essential import EssentialConfig

logger = logging.getLogger(__name__)

LEGACY_TABLE = "wa_cert"

# Columns the legacy 2.7.x `wa_cert` table is known to carry. Selected
# explicitly (never `SELECT *`) so a legacy schema that gained or lost a
# column still migrates the fields we can actually map.
_LEGACY_COLUMNS = (
    "wa_id",
    "name",
    "role",
    "pubkey",
    "jwt_kid",
    "password_hash",
    "api_key_hash",
    "oauth_provider",
    "oauth_external_id",
    "oauth_links_json",
    "veilid_id",
    "auto_minted",
    "parent_wa_id",
    "parent_signature",
    "scopes_json",
    "custom_permissions_json",
    "adapter_id",
    "adapter_name",
    "adapter_metadata_json",
    "created",
    "last_login",
    "active",
)


class WACertMigrationResult(BaseModel):
    """Outcome of one migration pass. Returned for tests and callers; the
    authoritative record for operators is the log line this produces."""

    sources: List[str] = Field(default_factory=list, description="Legacy DB paths actually scanned")
    found: int = Field(default=0, description="Legacy rows read from all sources")
    imported: int = Field(default=0, description="Rows written into the destination store")
    skipped_existing: int = Field(default=0, description="Rows already present in the destination")
    skipped_inactive: int = Field(default=0, description="Legacy rows with active=0 (revoked); not resurrected")
    skipped_unreadable: int = Field(default=0, description="Legacy rows that could not be mapped to a WACertificate")
    imported_ids: List[str] = Field(default_factory=list, description="wa_id of each imported certificate")
    error: Optional[str] = Field(default=None, description="Set when the pass aborted; boot continues regardless")


# --------------------------------------------------------------------------- #
# Legacy database discovery                                                    #
# --------------------------------------------------------------------------- #


def _is_sqlite_path(dsn: str) -> bool:
    """False for PostgreSQL DSNs — there is no sqlite file to read there.

    On Postgres deployments `get_audit_db_full_path` returns a
    `postgresql://...` URL. A long-jump upgrade on Postgres is out of scope
    for this file-level recovery, and handing the URL to sqlite3 would
    create a junk file named after the URL.
    """
    return "://" not in dsn


def _candidate_legacy_paths(config: Optional["EssentialConfig"] = None) -> List[str]:
    """Legacy databases to scan, deduplicated by real path.

    The audit DB is where 2.7.x actually put `wa_cert`. The main DB is
    included because older/other builds passed the main path, and because
    when audit and main are configured to the *same file* the dedup below
    collapses them to a single scan rather than importing everything twice.
    """
    from ciris_engine.logic.config.db_paths import get_audit_db_full_path, get_sqlite_db_full_path

    candidates: List[str] = []
    for label, getter in (("audit_db", get_audit_db_full_path), ("main_db", get_sqlite_db_full_path)):
        try:
            dsn = getter(config)
        except Exception as e:
            # get_sqlite_db_full_path raises when no config is available at
            # all. That is a caller problem, not a migration problem.
            logger.warning("wa_cert migration: could not resolve %s path: %s", label, e)
            continue
        if not dsn or not _is_sqlite_path(dsn):
            logger.info(
                "wa_cert migration: %s is not a sqlite path (%s backend); skipping legacy scan",
                label,
                "postgres" if dsn else "unset",
            )
            continue
        candidates.append(dsn)

    # Dedup on real path so audit-and-main-are-the-same-file scans once.
    seen: Set[str] = set()
    unique: List[str] = []
    for path in candidates:
        try:
            key = os.path.realpath(path)
        except OSError:
            key = path
        if key in seen:
            logger.debug("wa_cert migration: %s already scanned (same file); skipping", path)
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _open_readonly(path: str) -> Optional[sqlite3.Connection]:
    """Open a legacy DB read-only, or return None if it isn't there.

    Read-only keeps us off the write path of a database the persist engine
    may hold open (the dual-libsqlite WAL contention of CIRISAgent#763).
    Existence is checked first because a plain `sqlite3.connect` would
    *create* the file, which would turn "fresh install" into "empty legacy
    database on disk forever".
    """
    if not os.path.exists(path):
        logger.info("wa_cert migration: no legacy database at %s (fresh install)", path)
        return None
    try:
        uri = f"{Path(path).resolve().as_uri()}?mode=ro"
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error as e:
        logger.warning("wa_cert migration: read-only open of %s failed (%s); retrying read-write", path, e)
    try:
        return sqlite3.connect(path)
    except sqlite3.Error as e:
        logger.error("wa_cert migration: cannot open legacy database %s: %s", path, e)
        return None


def _read_legacy_rows(path: str) -> List[Dict[str, Any]]:
    """Read every `wa_cert` row from one legacy database.

    Returns [] — not an error — when the file has no `wa_cert` table. That
    is the shape of a database that never held certificates.
    """
    conn = _open_readonly(path)
    if conn is None:
        return []
    try:
        present = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (LEGACY_TABLE,),
        ).fetchone()
        if not present:
            logger.info("wa_cert migration: %s has no `%s` table; nothing to migrate", path, LEGACY_TABLE)
            return []

        available = {r[1] for r in conn.execute(f"PRAGMA table_info({LEGACY_TABLE})")}
        columns = [c for c in _LEGACY_COLUMNS if c in available]
        if "wa_id" not in columns:
            logger.warning("wa_cert migration: %s `%s` has no wa_id column; skipping", path, LEGACY_TABLE)
            return []

        # nosec B608 — every identifier is a module-level literal from
        # _LEGACY_COLUMNS / LEGACY_TABLE, intersected with PRAGMA output.
        # Nothing here is caller-supplied.
        cursor = conn.execute(f"SELECT {', '.join(columns)} FROM {LEGACY_TABLE}")  # nosec B608
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error("wa_cert migration: failed reading %s: %s", path, e)
        return []
    finally:
        try:
            conn.close()
        except sqlite3.Error:  # pragma: no cover - close rarely fails
            pass


# --------------------------------------------------------------------------- #
# Legacy row -> WACertificate                                                  #
# --------------------------------------------------------------------------- #


def _coerce_legacy_oauth_links(raw: Any) -> List[OAuthIdentityLink]:
    """Decode the legacy `oauth_links_json` column into pydantic models."""
    if not raw:
        return []
    parsed: Any = raw
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError as e:
            logger.warning("wa_cert migration: invalid oauth_links_json skipped: %s", e)
            return []
    if not isinstance(parsed, list):
        return []
    links: List[OAuthIdentityLink] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        try:
            links.append(OAuthIdentityLink(**entry))
        except Exception as e:
            logger.warning("wa_cert migration: invalid OAuth link entry skipped: %s", e)
    return links


def _row_to_certificate(row: Dict[str, Any]) -> Optional[WACertificate]:
    """Materialize a legacy row as a WACertificate, or None if it can't be.

    `password_hash` is passed straight through, untouched — the entire
    point of the migration.
    """
    try:
        return WACertificate(
            wa_id=str(row["wa_id"]),
            name=str(row["name"]),
            role=row["role"],
            pubkey=str(row["pubkey"]),
            jwt_kid=str(row["jwt_kid"]),
            password_hash=row.get("password_hash"),
            api_key_hash=row.get("api_key_hash"),
            oauth_provider=row.get("oauth_provider"),
            oauth_external_id=row.get("oauth_external_id"),
            oauth_links=_coerce_legacy_oauth_links(row.get("oauth_links_json")),
            auto_minted=bool(row.get("auto_minted") or False),
            veilid_id=row.get("veilid_id"),
            parent_wa_id=row.get("parent_wa_id"),
            parent_signature=row.get("parent_signature"),
            scopes_json=row.get("scopes_json") or "[]",
            custom_permissions_json=row.get("custom_permissions_json"),
            adapter_id=row.get("adapter_id"),
            adapter_name=row.get("adapter_name"),
            adapter_metadata_json=row.get("adapter_metadata_json"),
            created_at=row["created"],
            last_auth=row.get("last_login"),
        )
    except Exception as e:
        # %r escapes newlines/CR in a value that came off disk (CWE-117),
        # matching the pattern used in authentication_store.
        logger.warning("wa_cert migration: legacy row wa_id=%r is not a valid WACertificate: %s", row.get("wa_id"), e)
        return None


def _order_parents_first(certs: List[WACertificate]) -> List[WACertificate]:
    """Order so a parent is inserted before any child that references it.

    The destination table declares
    `FOREIGN KEY (parent_wa_id) REFERENCES cirislens_wa_cert(wa_id)`, so
    inserting the System Authority before the root WA it descends from
    would fail on the constraint.
    """
    by_id = {c.wa_id: c for c in certs}
    ordered: List[WACertificate] = []
    emitted: Set[str] = set()

    def visit(cert: WACertificate, path: Set[str]) -> None:
        if cert.wa_id in emitted or cert.wa_id in path:
            return  # already placed, or a parent cycle in legacy data
        path.add(cert.wa_id)
        parent_id = cert.parent_wa_id
        if parent_id and parent_id in by_id:
            visit(by_id[parent_id], path)
        path.discard(cert.wa_id)
        emitted.add(cert.wa_id)
        ordered.append(cert)

    for cert in certs:
        visit(cert, set())
    return ordered


# --------------------------------------------------------------------------- #
# Public entry point                                                           #
# --------------------------------------------------------------------------- #


def _collect_legacy_certificates(
    paths: List[str], result: WACertMigrationResult
) -> List[WACertificate]:
    """Read and map every legacy row across all candidate databases."""
    certs: List[WACertificate] = []
    seen_ids: Set[str] = set()
    for path in paths:
        rows = _read_legacy_rows(path)
        if not rows:
            continue
        result.sources.append(path)
        result.found += len(rows)
        for row in rows:
            # active=0 is a revoked certificate. store_wa_certificate always
            # writes active=True, so importing one would silently un-revoke
            # it. Leave revoked things revoked.
            if not bool(row.get("active", 1)):
                result.skipped_inactive += 1
                logger.info(
                    "wa_cert migration: legacy row wa_id=%r name=%r is inactive (revoked); not imported",
                    row.get("wa_id"),
                    row.get("name"),
                )
                continue
            cert = _row_to_certificate(row)
            if cert is None:
                result.skipped_unreadable += 1
                continue
            if cert.wa_id in seen_ids:
                continue  # same cert present in two legacy files
            seen_ids.add(cert.wa_id)
            certs.append(cert)
    return certs


def _import_certificates(certs: List[WACertificate], result: WACertMigrationResult) -> None:
    """Insert the certificates that are absent from the destination store."""
    from ciris_engine.logic.persistence.stores.authentication_store import (
        list_wa_certificates,
        store_wa_certificate,
    )

    existing = list_wa_certificates(active_only=True)
    existing_ids = {wa.wa_id for wa in existing}
    existing_kids = {wa.jwt_kid for wa in existing}

    for cert in _order_parents_first(certs):
        if cert.wa_id in existing_ids:
            result.skipped_existing += 1
            logger.info(
                "wa_cert migration: %s (%s) already present in destination; left untouched",
                cert.wa_id,
                cert.name,
            )
            continue
        if cert.jwt_kid in existing_kids:
            result.skipped_existing += 1
            logger.warning(
                "wa_cert migration: %s (%s) shares jwt_kid with a certificate already in the "
                "destination; left untouched to protect the live row",
                cert.wa_id,
                cert.name,
            )
            continue
        try:
            store_wa_certificate(cert)
        except ValueError:
            # authentication_store refuses to overwrite an existing wa_id —
            # e.g. a row that is present but INACTIVE, so it never showed up
            # in the active-only listing above. Refusing is correct.
            result.skipped_existing += 1
            logger.info(
                "wa_cert migration: %s (%s) already exists in destination (inactive); left untouched",
                cert.wa_id,
                cert.name,
            )
            continue
        except Exception as e:
            result.skipped_unreadable += 1
            logger.error("wa_cert migration: failed to import %s (%s): %s", cert.wa_id, cert.name, e)
            continue

        existing_ids.add(cert.wa_id)
        existing_kids.add(cert.jwt_kid)
        result.imported += 1
        result.imported_ids.append(cert.wa_id)
        logger.info(
            "wa_cert migration: imported %s name=%r role=%s has_password=%s",
            cert.wa_id,
            cert.name,
            cert.role.value,
            cert.password_hash is not None,
        )


def migrate_legacy_wa_certificates(
    config: Optional["EssentialConfig"] = None,
) -> WACertMigrationResult:
    """Import stranded 2.7.x `wa_cert` rows into the persist-backed store.

    Runs once per boot, after the authentication service is up and before
    adapters start. Idempotent: a second pass imports nothing. Never
    raises — a failure is logged at ERROR and reported in the result, and
    the agent boots regardless.
    """
    result = WACertMigrationResult()
    try:
        paths = _candidate_legacy_paths(config)
        if not paths:
            logger.info("wa_cert migration: no sqlite legacy database candidates; nothing to do")
            return result

        certs = _collect_legacy_certificates(paths, result)
        if not certs:
            logger.info(
                "wa_cert migration: no importable legacy certificates found (scanned=%s, rows=%d)",
                paths,
                result.found,
            )
            return result

        _import_certificates(certs, result)

        logger.info(
            "wa_cert migration complete: %d legacy row(s) found in %s -> %d imported, "
            "%d already present, %d inactive, %d unreadable; imported=%s",
            result.found,
            result.sources,
            result.imported,
            result.skipped_existing,
            result.skipped_inactive,
            result.skipped_unreadable,
            result.imported_ids,
        )
        if result.imported:
            logger.warning(
                "wa_cert migration RECOVERED %d Wise Authority certificate(s) stranded by a "
                "long-jump upgrade (pre-2.9.0 stored them in the audit database). "
                "Pre-existing logins should work again.",
                result.imported,
            )
        return result
    except Exception as e:  # pragma: no cover - defensive; inner paths already guard
        result.error = str(e)
        logger.exception(
            "wa_cert migration FAILED — pre-existing Wise Authority certificates may still be "
            "stranded and their owners unable to log in. Boot continues; re-run setup if the "
            "owner cannot authenticate."
        )
        return result
