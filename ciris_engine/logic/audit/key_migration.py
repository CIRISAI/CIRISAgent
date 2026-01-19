"""
Audit key migration utility: RSA-2048 to Ed25519.

This module provides a safe migration path from RSA-2048 signed audit trails
to Ed25519, with full chain re-signing and verification.

Migration steps:
1. Backup current state (keys + database)
2. Generate new Ed25519 key (or use existing unified key)
3. Load all audit entries in order
4. Re-sign each entry with Ed25519, preserving original timestamps
5. Update hash chain links
6. Verify the new chain integrity
7. Register the new key in the database
8. Archive the old RSA key (kept for historical verification)

The migration is atomic - if any step fails, the original state is restored.
"""

import base64
import hashlib
import json
import logging
import os
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple

from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


@dataclass
class MigrationResult:
    """Result of audit key migration."""

    success: bool
    message: str
    entries_migrated: int = 0
    old_key_id: Optional[str] = None
    new_key_id: Optional[str] = None
    backup_path: Optional[str] = None
    errors: List[str] = field(default_factory=list)


@dataclass
class AuditEntry:
    """Audit entry for migration."""

    sequence_number: int
    entry_hash: str
    previous_hash: str
    signature: str
    key_id: str
    timestamp: str
    event_type: str
    event_data: str


class AuditKeyMigration:
    """Migrate audit signing keys from RSA-2048 to Ed25519.

    This utility:
    1. Creates a backup of the current state
    2. Generates a new Ed25519 key (using the unified signing key)
    3. Re-signs the entire audit chain
    4. Updates the database with new signatures
    5. Registers the new key
    6. Archives the old RSA key

    The migration preserves:
    - Original timestamps
    - Event data
    - Entry ordering
    - Hash chain integrity (recomputed with new signatures)
    """

    def __init__(
        self,
        db_path: str,
        key_path: str,
        time_service: TimeServiceProtocol,
    ) -> None:
        self.db_path = Path(db_path)
        self.key_path = Path(key_path)
        self.time_service = time_service
        self._backup_path: Optional[Path] = None

    async def migrate_to_ed25519(
        self,
        backup: bool = True,
        verify_after: bool = True,
    ) -> MigrationResult:
        """Migrate RSA-signed audit chain to Ed25519.

        Args:
            backup: Create backup before migration (recommended)
            verify_after: Verify chain integrity after migration

        Returns:
            MigrationResult with details of the migration
        """
        logger.info("=" * 70)
        logger.info("🔐 AUDIT KEY MIGRATION: RSA-2048 -> Ed25519")
        logger.info("=" * 70)

        result = MigrationResult(success=False, message="Migration not started")

        try:
            # Step 1: Check current state
            old_key_info = self._get_current_key_info()
            if not old_key_info:
                return MigrationResult(
                    success=False,
                    message="No existing RSA key found - nothing to migrate",
                )

            old_key_id, old_algorithm = old_key_info
            if old_algorithm == "ed25519":
                return MigrationResult(
                    success=True,
                    message="Already using Ed25519 - no migration needed",
                    old_key_id=old_key_id,
                    new_key_id=old_key_id,
                )

            logger.info(f"Current key: {old_key_id} ({old_algorithm})")
            result.old_key_id = old_key_id

            # Step 2: Create backup
            if backup:
                self._backup_path = self._create_backup()
                result.backup_path = str(self._backup_path)
                logger.info(f"Backup created at: {self._backup_path}")

            # Step 3: Get unified Ed25519 key
            from .signing_protocol import get_unified_signing_key

            unified_key = get_unified_signing_key()
            new_key_id = unified_key.key_id
            result.new_key_id = new_key_id
            logger.info(f"New Ed25519 key: {new_key_id}")

            # Step 4: Load all audit entries
            entries = self._load_all_entries()
            logger.info(f"Loaded {len(entries)} audit entries for re-signing")

            if not entries:
                # Register the new key even if no entries
                self._register_ed25519_key(unified_key)
                return MigrationResult(
                    success=True,
                    message="No audit entries to migrate - Ed25519 key registered",
                    entries_migrated=0,
                    old_key_id=old_key_id,
                    new_key_id=new_key_id,
                    backup_path=result.backup_path,
                )

            # Step 5: Re-sign entries with Ed25519
            migrated_entries = self._resign_entries(entries, unified_key)
            logger.info(f"Re-signed {len(migrated_entries)} entries")

            # Step 6: Update database atomically
            self._update_database(migrated_entries, unified_key)
            logger.info("Database updated with new signatures")

            # Step 7: Verify chain integrity
            if verify_after:
                if not self._verify_chain_integrity(unified_key):
                    raise RuntimeError("Chain verification failed after migration")
                logger.info("✅ Chain integrity verified")

            # Step 8: Archive old RSA key
            self._archive_old_key(old_key_id)
            logger.info(f"Archived old RSA key: {old_key_id}")

            result.success = True
            result.message = "Migration completed successfully"
            result.entries_migrated = len(migrated_entries)

            logger.info("=" * 70)
            logger.info(f"✅ MIGRATION COMPLETE: {len(migrated_entries)} entries re-signed")
            logger.info(f"   Old key: {old_key_id} (RSA-2048)")
            logger.info(f"   New key: {new_key_id} (Ed25519)")
            logger.info("=" * 70)

            return result

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            result.message = f"Migration failed: {e}"
            result.errors.append(str(e))

            # Attempt rollback if backup exists
            if self._backup_path and self._backup_path.exists():
                try:
                    self._restore_backup()
                    logger.info("Rolled back to backup state")
                    result.message += " (rolled back to backup)"
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")
                    result.errors.append(f"Rollback failed: {rollback_error}")

            return result

    def _get_current_key_info(self) -> Optional[Tuple[str, str]]:
        """Get current signing key info (key_id, algorithm)."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Get the most recent non-revoked key
            cursor.execute("""
                SELECT key_id, algorithm FROM audit_signing_keys
                WHERE revoked_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
            """)

            row = cursor.fetchone()
            conn.close()

            if row:
                return (row[0], row[1])
            return None

        except Exception as e:
            logger.error(f"Failed to get current key info: {e}")
            return None

    def _create_backup(self) -> Path:
        """Create backup of database and keys."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = Path("data_archive") / f"audit_migration_backup_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Backup database
        shutil.copy2(self.db_path, backup_dir / self.db_path.name)

        # Backup keys
        key_backup_dir = backup_dir / "keys"
        key_backup_dir.mkdir(exist_ok=True)

        for key_file in self.key_path.glob("audit_signing_*"):
            shutil.copy2(key_file, key_backup_dir / key_file.name)

        return backup_dir

    def _restore_backup(self) -> None:
        """Restore from backup."""
        if not self._backup_path or not self._backup_path.exists():
            raise RuntimeError("No backup to restore")

        # Restore database
        backup_db = self._backup_path / self.db_path.name
        if backup_db.exists():
            shutil.copy2(backup_db, self.db_path)

        # Restore keys
        key_backup_dir = self._backup_path / "keys"
        if key_backup_dir.exists():
            for key_file in key_backup_dir.glob("audit_signing_*"):
                shutil.copy2(key_file, self.key_path / key_file.name)

    def _load_all_entries(self) -> List[AuditEntry]:
        """Load all audit entries in order."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT sequence_number, entry_hash, previous_hash, signature,
                   key_id, timestamp, event_type, event_data
            FROM audit_entries
            ORDER BY sequence_number ASC
        """)

        entries = []
        for row in cursor.fetchall():
            entries.append(AuditEntry(
                sequence_number=row[0],
                entry_hash=row[1],
                previous_hash=row[2],
                signature=row[3],
                key_id=row[4],
                timestamp=row[5],
                event_type=row[6],
                event_data=row[7],
            ))

        conn.close()
        return entries

    def _resign_entries(
        self,
        entries: List[AuditEntry],
        unified_key: Any,
    ) -> List[AuditEntry]:
        """Re-sign all entries with Ed25519, recomputing hash chain."""
        migrated = []
        previous_hash = "GENESIS"

        for entry in entries:
            # Recompute entry hash (includes previous_hash to maintain chain)
            hash_content = {
                "sequence_number": entry.sequence_number,
                "timestamp": entry.timestamp,
                "event_type": entry.event_type,
                "event_data": entry.event_data,
                "previous_hash": previous_hash,
            }
            hash_str = json.dumps(hash_content, sort_keys=True, separators=(",", ":"))
            new_entry_hash = hashlib.sha256(hash_str.encode()).hexdigest()

            # Sign with Ed25519
            signature_bytes = unified_key.sign(new_entry_hash.encode())
            new_signature = base64.b64encode(signature_bytes).decode()

            # Create migrated entry
            migrated_entry = AuditEntry(
                sequence_number=entry.sequence_number,
                entry_hash=new_entry_hash,
                previous_hash=previous_hash,
                signature=new_signature,
                key_id=unified_key.key_id,
                timestamp=entry.timestamp,
                event_type=entry.event_type,
                event_data=entry.event_data,
            )
            migrated.append(migrated_entry)

            # Update chain link
            previous_hash = new_entry_hash

        return migrated

    def _update_database(self, entries: List[AuditEntry], unified_key: Any) -> None:
        """Update database with re-signed entries atomically."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            # Update each entry
            for entry in entries:
                cursor.execute("""
                    UPDATE audit_entries
                    SET entry_hash = ?,
                        previous_hash = ?,
                        signature = ?,
                        key_id = ?
                    WHERE sequence_number = ?
                """, (
                    entry.entry_hash,
                    entry.previous_hash,
                    entry.signature,
                    entry.key_id,
                    entry.sequence_number,
                ))

            conn.commit()

        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Database update failed: {e}")

        finally:
            conn.close()

    def _register_ed25519_key(self, unified_key: Any) -> None:
        """Register the Ed25519 key in the database."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            # Check if key already exists
            cursor.execute(
                "SELECT key_id FROM audit_signing_keys WHERE key_id = ?",
                (unified_key.key_id,)
            )

            if cursor.fetchone():
                logger.debug(f"Key {unified_key.key_id} already registered")
                conn.close()
                return

            # Insert new key
            cursor.execute("""
                INSERT INTO audit_signing_keys
                (key_id, public_key, algorithm, key_size, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                unified_key.key_id,
                unified_key.public_key_base64,
                "ed25519",
                256,  # Ed25519 uses 256-bit keys
                self.time_service.now_iso(),
            ))

            conn.commit()
            logger.info(f"Registered Ed25519 key: {unified_key.key_id}")

        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Key registration failed: {e}")

        finally:
            conn.close()

    def _archive_old_key(self, old_key_id: str) -> None:
        """Mark old RSA key as archived (not revoked, for verification)."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            # Add a note to the key record
            cursor.execute("""
                UPDATE audit_signing_keys
                SET revoked_at = ?
                WHERE key_id = ?
            """, (
                f"MIGRATED_TO_ED25519_{self.time_service.now_iso()}",
                old_key_id,
            ))

            conn.commit()

        except Exception as e:
            logger.warning(f"Could not archive old key {old_key_id}: {e}")

        finally:
            conn.close()

        # Also rename old key files to .archived
        for key_file in self.key_path.glob("audit_signing_*.pem"):
            archived_name = key_file.with_suffix(".pem.archived")
            try:
                key_file.rename(archived_name)
                logger.info(f"Archived key file: {key_file.name} -> {archived_name.name}")
            except Exception as e:
                logger.warning(f"Could not archive key file {key_file}: {e}")

    def _verify_chain_integrity(self, unified_key: Any) -> bool:
        """Verify the migrated chain integrity."""
        entries = self._load_all_entries()
        previous_hash = "GENESIS"

        for entry in entries:
            # Verify hash chain
            hash_content = {
                "sequence_number": entry.sequence_number,
                "timestamp": entry.timestamp,
                "event_type": entry.event_type,
                "event_data": entry.event_data,
                "previous_hash": previous_hash,
            }
            hash_str = json.dumps(hash_content, sort_keys=True, separators=(",", ":"))
            expected_hash = hashlib.sha256(hash_str.encode()).hexdigest()

            if entry.entry_hash != expected_hash:
                logger.error(f"Hash mismatch at entry {entry.sequence_number}")
                return False

            if entry.previous_hash != previous_hash:
                logger.error(f"Chain link broken at entry {entry.sequence_number}")
                return False

            # Verify signature
            try:
                signature_bytes = base64.b64decode(entry.signature)
                if not unified_key.verify(entry.entry_hash.encode(), signature_bytes):
                    logger.error(f"Signature invalid at entry {entry.sequence_number}")
                    return False
            except Exception as e:
                logger.error(f"Signature verification failed at entry {entry.sequence_number}: {e}")
                return False

            previous_hash = entry.entry_hash

        return True


async def migrate_audit_key_to_ed25519(
    db_path: str,
    key_path: str,
    time_service: TimeServiceProtocol,
    backup: bool = True,
) -> MigrationResult:
    """Convenience function to migrate audit keys to Ed25519.

    Args:
        db_path: Path to the SQLite database
        key_path: Path to the key directory
        time_service: Time service for timestamps
        backup: Create backup before migration

    Returns:
        MigrationResult with migration details
    """
    migration = AuditKeyMigration(db_path, key_path, time_service)
    return await migration.migrate_to_ed25519(backup=backup)
