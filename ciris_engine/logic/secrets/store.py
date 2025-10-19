"""
Encrypted Secrets Storage System for CIRIS Agent.

Provides secure, encrypted storage for detected secrets with AES-256-GCM encryption
and comprehensive access auditing.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, cast

from ciris_engine.logic.persistence.db import get_db_connection
from ciris_engine.logic.persistence.db.dialect import get_adapter
from ciris_engine.logic.persistence.db.query_builder import ConflictResolution
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.secrets.core import DetectedSecret, SecretAccessLog, SecretRecord, SecretReference

from .encryption import SecretsEncryption

logger = logging.getLogger(__name__)


class SecretsStore:
    """
    Encrypted storage for secrets with comprehensive access controls.

    Stores secrets in SQLite database with AES-256-GCM encryption
    and maintains full audit trail of all access.
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        db_path: str = "secrets.db",
        master_key: Optional[bytes] = None,
        max_accesses_per_minute: int = 10,
        max_accesses_per_hour: int = 100,
    ):
        """
        Initialize secrets store.

        Args:
            time_service: Time service for consistent timestamps
            db_path: Path to SQLite database file
            master_key: Master encryption key (generated if None)
            max_accesses_per_minute: Rate limit for secret access
            max_accesses_per_hour: Hourly access limit
        """
        self.time_service = time_service
        # For PostgreSQL, keep connection string as-is; for SQLite, ensure Path object
        self.db_path: str | Path
        if db_path.startswith(("postgresql://", "postgres://")):
            self.db_path = db_path
        else:
            self.db_path = Path(db_path)
        self.encryption = SecretsEncryption(master_key)
        self.max_accesses_per_minute = max_accesses_per_minute
        self.max_accesses_per_hour = max_accesses_per_hour
        self._access_counts: Dict[str, List[datetime]] = {}
        self._lock = asyncio.Lock()

        self._init_database()

    def _get_auto_decapsulate_actions(self, sensitivity: str) -> List[str]:
        """
        Get default auto-decapsulation actions based on sensitivity.

        Args:
            sensitivity: Secret sensitivity level (LOW, MEDIUM, HIGH, CRITICAL)

        Returns:
            List of action types that can auto-decapsulate this secret
        """
        if sensitivity == "CRITICAL":
            return []  # Require manual access for critical secrets
        elif sensitivity == "HIGH":
            return ["tool"]  # Only tool actions for high sensitivity
        elif sensitivity == "MEDIUM":
            return ["tool", "speak"]  # Tool and speak actions
        else:  # LOW
            return ["tool", "speak", "memorize"]  # Most actions allowed

    def _init_database(self) -> None:
        """Initialize database with required tables."""
        # Ensure directory exists (only for SQLite file paths)
        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Detect database type - PostgreSQL uses BYTEA instead of BLOB
        db_path_str = str(self.db_path)
        is_postgres = db_path_str.startswith(("postgresql://", "postgres://"))
        blob_type = "BYTEA" if is_postgres else "BLOB"

        with get_db_connection(str(self.db_path)) as conn:
            # Secrets table
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS secrets (
                    secret_uuid TEXT PRIMARY KEY,
                    encrypted_value {blob_type} NOT NULL,
                    encryption_key_ref TEXT NOT NULL,
                    salt {blob_type} NOT NULL,
                    nonce {blob_type} NOT NULL,
                    description TEXT NOT NULL,
                    sensitivity_level TEXT NOT NULL,
                    detected_pattern TEXT NOT NULL,
                    context_hint TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_accessed TEXT,
                    access_count INTEGER DEFAULT 0,
                    source_message_id TEXT,
                    auto_decapsulate_for_actions TEXT,
                    manual_access_only INTEGER DEFAULT 0
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS secret_access_log (
                    access_id TEXT PRIMARY KEY,
                    secret_uuid TEXT NOT NULL,
                    access_type TEXT NOT NULL,
                    accessor TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    source_ip TEXT,
                    user_agent TEXT,
                    action_context TEXT,
                    success INTEGER DEFAULT 1,
                    failure_reason TEXT,
                    FOREIGN KEY (secret_uuid) REFERENCES secrets (secret_uuid)
                )
            """
            )

            # Indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_secrets_pattern ON secrets(detected_pattern)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_secrets_sensitivity ON secrets(sensitivity_level)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_access_log_timestamp ON secret_access_log(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_access_log_secret ON secret_access_log(secret_uuid)")

            conn.commit()

    async def store_secret(self, secret: DetectedSecret, source_id: Optional[str] = None) -> SecretRecord:
        """
        Store encrypted secret in database.

        Args:
            secret: The detected secret to store
            source_id: Optional identifier for the source

        Returns:
            SecretRecord with storage metadata
        """
        async with self._lock:
            try:
                # Encrypt the secret value
                encrypted_value, salt, nonce = self.encryption.encrypt_secret(secret.original_value)

                # Create secret record with encryption data
                secret_record = SecretRecord(
                    secret_uuid=secret.secret_uuid,
                    encrypted_value=encrypted_value,
                    encryption_key_ref="master_key_v1",  # Key versioning
                    salt=salt,
                    nonce=nonce,
                    description=secret.description,
                    sensitivity_level=secret.sensitivity,
                    detected_pattern=secret.pattern_name,
                    context_hint=secret.context_hint,
                    created_at=self.time_service.now(),
                    last_accessed=None,
                    access_count=0,
                    source_message_id=source_id,
                    auto_decapsulate_for_actions=self._get_auto_decapsulate_actions(secret.sensitivity.value),
                    manual_access_only=False,
                )

                # Use dialect-aware query builder for UPSERT
                adapter = get_adapter()
                builder = adapter.get_query_builder()

                query = builder.insert(
                    table="secrets",
                    columns=[
                        "secret_uuid",
                        "encrypted_value",
                        "encryption_key_ref",
                        "salt",
                        "nonce",
                        "description",
                        "sensitivity_level",
                        "detected_pattern",
                        "context_hint",
                        "created_at",
                        "last_accessed",
                        "access_count",
                        "source_message_id",
                        "auto_decapsulate_for_actions",
                        "manual_access_only",
                    ],
                    conflict_resolution=ConflictResolution.REPLACE,
                    conflict_columns=["secret_uuid"],
                )
                sql = query.to_sql(adapter)

                with get_db_connection(str(self.db_path)) as conn:
                    conn.execute(
                        sql,
                        (
                            secret_record.secret_uuid,
                            secret_record.encrypted_value,
                            secret_record.encryption_key_ref,
                            secret_record.salt,
                            secret_record.nonce,
                            secret_record.description,
                            secret_record.sensitivity_level,
                            secret_record.detected_pattern,
                            secret_record.context_hint,
                            secret_record.created_at.isoformat(),
                            secret_record.last_accessed.isoformat() if secret_record.last_accessed else None,
                            secret_record.access_count,
                            secret_record.source_message_id,
                            ",".join(secret_record.auto_decapsulate_for_actions),
                            1 if secret_record.manual_access_only else 0,
                        ),
                    )
                    conn.commit()

                await self._log_access(secret_record.secret_uuid, "STORE", "system", "Initial secret storage", True)

                logger.info(f"Stored encrypted secret {secret_record.secret_uuid}")
                return secret_record

            except Exception as e:  # pragma: no cover - error path
                logger.error(f"Failed to store secret {secret.secret_uuid}: {type(e).__name__}")
                await self._log_access(secret.secret_uuid, "STORE", "system", "Initial secret storage", False, str(e))
                raise

    async def retrieve_secret(self, secret_uuid: str, decrypt: bool = False) -> Optional[SecretRecord]:
        """
        Retrieve secret from storage.

        Args:
            secret_uuid: UUID of secret to retrieve
            decrypt: Whether to decrypt the secret value

        Returns:
            SecretRecord if found, None otherwise
        """
        async with self._lock:
            if not await self._check_rate_limits("system"):
                await self._log_access(secret_uuid, "VIEW", "system", "retrieve", False, "Rate limit exceeded")
                return None

            try:
                with get_db_connection(str(self.db_path)) as conn:
                    cursor = conn.execute(
                        """
                        SELECT * FROM secrets WHERE secret_uuid = ?
                    """,
                        (secret_uuid,),
                    )

                    row = cursor.fetchone()
                    if not row:
                        await self._log_access(secret_uuid, "VIEW", "system", "retrieve", False, "Secret not found")
                        return None

                    # Parse database row
                    secret_record = SecretRecord(
                        secret_uuid=row[0],
                        encrypted_value=row[1],
                        encryption_key_ref=row[2],
                        salt=row[3],
                        nonce=row[4],
                        description=row[5],
                        sensitivity_level=row[6],
                        detected_pattern=row[7],
                        context_hint=row[8],
                        created_at=datetime.fromisoformat(row[9]),
                        last_accessed=datetime.fromisoformat(row[10]) if row[10] else None,
                        access_count=row[11],
                        source_message_id=row[12],
                        auto_decapsulate_for_actions=row[13].split(",") if row[13] else [],
                        manual_access_only=bool(row[14]),
                    )

                    # Update access tracking
                    secret_record.last_accessed = self.time_service.now()
                    secret_record.access_count += 1

                    conn.execute(
                        """
                        UPDATE secrets
                        SET last_accessed = ?, access_count = ?
                        WHERE secret_uuid = ?
                    """,
                        (secret_record.last_accessed.isoformat(), secret_record.access_count, secret_uuid),
                    )
                    conn.commit()

                access_type = "DECRYPT" if decrypt else "VIEW"
                await self._log_access(secret_uuid, access_type, "system", "retrieve", True)

                return secret_record

            except Exception as e:  # pragma: no cover - error path
                logger.error(f"Failed to retrieve secret {secret_uuid}: {type(e).__name__}")
                await self._log_access(secret_uuid, "VIEW", "system", "retrieve", False, str(e))
                return None

    def decrypt_secret_value(self, secret_record: SecretRecord) -> Optional[str]:
        """
        Decrypt the actual secret value.

        Args:
            secret_record: Secret record with encryption data

        Returns:
            Decrypted secret value or None if decryption fails
        """
        try:
            return self.encryption.decrypt_secret(
                secret_record.encrypted_value, secret_record.salt, secret_record.nonce
            )
        except Exception as e:  # pragma: no cover - error path
            logger.error(f"Failed to decrypt secret {secret_record.secret_uuid}: {type(e).__name__}")
            return None

    async def delete_secret(self, secret_uuid: str) -> bool:
        """
        Delete secret from storage.

        Args:
            secret_uuid: UUID of secret to delete

        Returns:
            True if deleted successfully
        """
        async with self._lock:
            try:
                with get_db_connection(str(self.db_path)) as conn:
                    # Check if secret exists first
                    cursor = conn.execute("SELECT secret_uuid FROM secrets WHERE secret_uuid = ?", (secret_uuid,))
                    exists = cursor.fetchone() is not None

                    if not exists:
                        logger.warning(f"Secret {secret_uuid} does not exist")
                        return False

                    # Log deletion BEFORE deleting (so foreign key constraint is satisfied)
                    await self._log_access(secret_uuid, "DELETE", "system", "Secret deletion", True)

                    # Delete access log entries first to avoid foreign key constraint violation
                    conn.execute("DELETE FROM secret_access_log WHERE secret_uuid = ?", (secret_uuid,))

                    # Now delete the secret itself
                    cursor = conn.execute("DELETE FROM secrets WHERE secret_uuid = ?", (secret_uuid,))
                    deleted = cursor.rowcount > 0
                    conn.commit()

                if deleted:
                    logger.info(f"Deleted secret {secret_uuid}")
                return deleted

            except Exception as e:  # pragma: no cover - error path
                logger.error(f"Failed to delete secret {secret_uuid}: {type(e).__name__}")
                # Don't try to log access here - secret may already be deleted
                return False

    async def list_secrets(
        self, sensitivity_filter: Optional[str] = None, pattern_filter: Optional[str] = None
    ) -> List[SecretReference]:
        """
        List stored secrets (metadata only).

        Args:
            sensitivity_filter: Filter by sensitivity level
            pattern_filter: Filter by detected pattern name

        Returns:
            List of SecretReference objects
        """
        try:
            query = "SELECT secret_uuid, description, context_hint, sensitivity_level, detected_pattern, auto_decapsulate_for_actions, created_at, last_accessed FROM secrets WHERE 1=1"
            params = []

            if sensitivity_filter:
                query += " AND sensitivity_level = ?"
                params.append(sensitivity_filter)

            if pattern_filter:
                query += " AND detected_pattern = ?"
                params.append(pattern_filter)

            query += " ORDER BY created_at DESC"

            with get_db_connection(str(self.db_path)) as conn:
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

            secrets = []
            for row in rows:
                # Handle both tuple (SQLite) and dict (PostgreSQL) rows
                if isinstance(row, dict):
                    # PostgreSQL RealDictCursor returns dict-like rows
                    uuid = row["secret_uuid"]
                    description = row["description"]
                    context_hint = row["context_hint"]
                    sensitivity = row["sensitivity_level"]
                    detected_pattern = row["detected_pattern"]
                    auto_decapsulate_actions_str = row["auto_decapsulate_for_actions"]
                    created_at_str = row["created_at"]
                    last_accessed_str = row["last_accessed"]
                else:
                    # SQLite Row objects support index access
                    uuid = row[0]
                    description = row[1]
                    context_hint = row[2]
                    sensitivity = row[3]
                    detected_pattern = row[4]
                    auto_decapsulate_actions_str = row[5]
                    created_at_str = row[6]
                    last_accessed_str = row[7]

                secret_ref = SecretReference(
                    uuid=uuid,
                    description=description,
                    context_hint=context_hint,
                    sensitivity=sensitivity,
                    detected_pattern=detected_pattern,
                    auto_decapsulate_actions=(
                        auto_decapsulate_actions_str.split(",") if auto_decapsulate_actions_str else []
                    ),
                    created_at=(
                        datetime.fromisoformat(created_at_str) if isinstance(created_at_str, str) else created_at_str
                    ),
                    last_accessed=(
                        datetime.fromisoformat(last_accessed_str)
                        if last_accessed_str and isinstance(last_accessed_str, str)
                        else last_accessed_str
                    ),
                )
                secrets.append(secret_ref)

            return secrets

        except Exception as e:  # pragma: no cover - error path
            logger.error(f"Failed to list secrets: {type(e).__name__}")
            return []

    async def list_all_secrets(self) -> List[SecretReference]:
        """
        List all stored secrets (no filters).

        Returns:
            List of SecretReference
        """
        return await self.list_secrets()

    async def _check_rate_limits(self, accessor: str) -> bool:  # pragma: no cover - simple
        """Check if accessor is within rate limits."""
        now = self.time_service.now()

        # Initialize tracking for new accessor
        if accessor not in self._access_counts:
            self._access_counts[accessor] = []

        access_times = self._access_counts[accessor]

        # Remove old access times
        minute_ago = now.timestamp() - 60
        hour_ago = now.timestamp() - 3600

        access_times[:] = [access_time for access_time in access_times if access_time.timestamp() > hour_ago]

        # Check limits
        recent_accesses = [access_time for access_time in access_times if access_time.timestamp() > minute_ago]

        if len(recent_accesses) >= self.max_accesses_per_minute:  # pragma: no cover - rate limit
            return False

        if len(access_times) >= self.max_accesses_per_hour:  # pragma: no cover - rate limit
            return False

        # Record this access
        access_times.append(now)
        return True

    async def _log_access(
        self,
        secret_uuid: str,
        access_type: str,
        accessor: str,
        purpose: str,
        success: bool,
        failure_reason: Optional[str] = None,
    ) -> None:
        """Log secret access for audit trail."""
        try:
            access_log = SecretAccessLog(
                access_id=f"access_{self.time_service.now().timestamp()}_{secret_uuid[:8]}",
                secret_uuid=secret_uuid,
                access_type=cast(Literal["VIEW", "DECRYPT", "UPDATE", "DELETE"], access_type),
                accessor=accessor,
                purpose=purpose,
                timestamp=self.time_service.now(),
                success=success,
                failure_reason=failure_reason,
            )

            with get_db_connection(str(self.db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO secret_access_log (
                        access_id, secret_uuid, access_type, accessor, purpose,
                        timestamp, source_ip, user_agent, action_context,
                        success, failure_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        access_log.access_id,
                        access_log.secret_uuid,
                        access_log.access_type,
                        access_log.accessor,
                        access_log.purpose,
                        access_log.timestamp.isoformat(),
                        access_log.source_ip,
                        access_log.user_agent,
                        access_log.action_context,
                        1 if access_log.success else 0,
                        access_log.failure_reason,
                    ),
                )
                conn.commit()

        except Exception as e:  # pragma: no cover - error path
            logger.error(f"Failed to log secret access: {type(e).__name__}")

    # Implement missing SecretsEncryptionInterface methods by delegating to encryption instance
    def encrypt_secret(self, value: str) -> Tuple[bytes, bytes, bytes]:
        """Delegate to encryption instance."""
        return self.encryption.encrypt_secret(value)

    def decrypt_secret(self, encrypted_value: bytes, salt: bytes, nonce: bytes) -> str:
        """Delegate to encryption instance."""
        return self.encryption.decrypt_secret(encrypted_value, salt, nonce)

    def rotate_master_key(self, new_master_key: Optional[bytes] = None) -> bytes:
        """Delegate to encryption instance."""
        return self.encryption.rotate_master_key(new_master_key)

    def test_encryption(self) -> bool:
        """Test that encryption/decryption works correctly."""
        try:
            test_value = "test_secret_123"
            encrypted_value, salt, nonce = self.encrypt_secret(test_value)
            decrypted_value = self.decrypt_secret(encrypted_value, salt, nonce)
            return decrypted_value == test_value
        except Exception:
            return False

    async def get_access_logs(self, secret_uuid: Optional[str] = None, limit: int = 100) -> List[Any]:
        """Get access logs for auditing."""
        logs = []
        try:
            with get_db_connection(str(self.db_path)) as conn:
                if secret_uuid:
                    cursor = conn.execute(
                        """
                        SELECT * FROM secret_access_log
                        WHERE secret_uuid = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """,
                        (secret_uuid, limit),
                    )
                else:
                    cursor = conn.execute(
                        """
                        SELECT * FROM secret_access_log
                        ORDER BY timestamp DESC
                        LIMIT ?
                    """,
                        (limit,),
                    )

                for row in cursor.fetchall():
                    logs.append(
                        {
                            "access_id": row[0],
                            "secret_uuid": row[1],
                            "access_type": row[2],
                            "accessor": row[3],
                            "purpose": row[4],
                            "timestamp": row[5],
                            "success": bool(row[9]),
                        }
                    )
        except Exception as e:  # pragma: no cover - error path
            logger.error(f"Failed to retrieve access logs: {type(e).__name__}")
        return logs

    async def reencrypt_all(self, new_encryption_key: bytes) -> bool:
        """Re-encrypt all stored secrets with a new key."""
        try:
            # Get all secrets
            with get_db_connection(str(self.db_path)) as conn:
                cursor = conn.execute("SELECT secret_uuid, encrypted_value, salt, nonce FROM secrets")
                secrets = cursor.fetchall()

            if not secrets:
                logger.info("No secrets to re-encrypt")
                return True

            # Decrypt with old key and re-encrypt with new key
            updated_secrets = []
            for secret_uuid, encrypted_value, salt, nonce in secrets:
                try:
                    # Decrypt with current key
                    decrypted_value = self.encryption.decrypt_secret(encrypted_value, salt, nonce)

                    # Create new encryption instance with new key
                    new_encryption = SecretsEncryption(new_encryption_key)

                    # Re-encrypt with new key
                    new_encrypted_value, new_salt, new_nonce = new_encryption.encrypt_secret(decrypted_value)

                    updated_secrets.append((new_encrypted_value, new_salt, new_nonce, secret_uuid))

                except Exception as decrypt_error:
                    logger.error(f"Failed to re-encrypt secret {secret_uuid}: {type(decrypt_error).__name__}")
                    return False

            # Update all secrets in database
            with get_db_connection(str(self.db_path)) as conn:
                conn.executemany(
                    """
                    UPDATE secrets
                    SET encrypted_value = ?, salt = ?, nonce = ?, encryption_key_ref = ?
                    WHERE secret_uuid = ?
                """,
                    [(enc_val, salt, nonce, "master_key_v2", uuid) for enc_val, salt, nonce, uuid in updated_secrets],
                )
                conn.commit()

            self.encryption = SecretsEncryption(new_encryption_key)

            logger.info(f"Successfully re-encrypted {len(updated_secrets)} secrets")
            return True

        except Exception as e:
            logger.error(f"Failed to re-encrypt secrets: {type(e).__name__}")
            return False

    async def update_access_log(self, log_entry: Any) -> None:
        """Record access to a secret in the audit log."""
        await self._log_access(
            log_entry.secret_uuid,
            log_entry.access_type,
            log_entry.accessor,
            log_entry.purpose,
            log_entry.success,
            log_entry.failure_reason,
        )
